"""Starlette app exposing the Streamable HTTP MCP endpoint + health check.

Wires a stateless `StreamableHTTPSessionManager` over the low-level MCP server,
enables DNS-rebinding/Origin protection, and exposes `/health`. Stateless is the
default per the architecture docs: no session state is retained between calls.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from . import SERVER_NAME, SERVER_VERSION, config
from .mcp_transport import build_server


def _security_settings():
    from mcp.server.transport_security import TransportSecuritySettings

    raw = config.get_string("ALLOWED_ORIGINS").strip()
    allowed_origins = [o.strip() for o in raw.split(",") if o.strip()]
    # When origins are configured, enable rebinding protection; otherwise keep it
    # permissive for local dev/Inspector but still construct the settings object.
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(allowed_origins),
        allowed_origins=allowed_origins or ["*"],
        allowed_hosts=["*"],
    )


def build_app():
    mcp_server = build_server()

    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        json_response=False,
        stateless=True,
        security_settings=_security_settings(),
    )

    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "server": SERVER_NAME,
                "version": SERVER_VERSION,
                "missing_required_secrets": config.missing_required_secrets(),
            }
        )

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    starlette_app = Starlette(
        debug=False,
        lifespan=lifespan,
        routes=[
            Route("/health", health, methods=["GET"]),
            Mount("/mcp", app=handle_mcp),
        ],
    )

    # Serve "/mcp" and "/mcp/" identically. Starlette's Mount would otherwise 307 a
    # bare "/mcp" to "/mcp/", and behind the PlayMCP proxy that redirect can carry an
    # http:// Location (HTTPS downgrade) and breaks MCP clients that don't re-POST.
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        await starlette_app(scope, receive, send)

    return app


def main() -> None:
    # Load a local .env (if present) before reading any config, so local runs pick up
    # USER_EMAIL / NAVER_CLIENT_ID / NAVER_CLIENT_SECRET without manual exports. In
    # production no .env is shipped, so platform-injected env vars are used as-is.
    loaded = config.load_env_file()
    if loaded:
        from . import logging as rg_logging
        rg_logging.log_event("info", "env_file_loaded", {"keys": sorted(loaded)})

    app = build_app()
    host = config.get_string("HOST")
    port = int(os.environ.get("PORT", config.get_string("PORT")))
    # Trust the PlayMCP/KakaoCloud (envoy) proxy's X-Forwarded-Proto so the app
    # knows requests are https. Without this, the /mcp -> /mcp/ slash redirect is
    # emitted as an http:// Location, downgrading https and breaking MCP clients.
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()


__all__ = ["build_app", "main"]
