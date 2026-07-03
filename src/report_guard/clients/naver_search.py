"""Naver Search API client (isolated outbound boundary).

Issues a single bounded search query. Credentials come from `config` (env only) and
are sent as headers — never logged or returned. Enforces display<=100, start<=1000,
UTF-8 query encoding, SSRF/allowlist validation, timeouts, and normalizes
429/5xx/network failures. Must not import pipelines/transport/orchestrator.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel

from .. import config
from .. import logging as rg_logging
from ..errors import ErrorCode, ModuleError, module_error
from ..retry import with_retries
from ..schemas import Status

_ENDPOINTS = {
    "webkr": "https://openapi.naver.com/v1/search/webkr.json",
    "blog": "https://openapi.naver.com/v1/search/blog.json",
}


class NaverSearchRequest(BaseModel):
    query: str
    display: int = 10
    start: int = 1
    sort: str | None = None
    endpoint: str = "webkr"
    deadline_ms: int = 3000


class NaverSearchItem(BaseModel):
    title: str
    link: str
    description: str
    source: str | None = None
    post_date: str | None = None


class NaverSearchResponse(BaseModel):
    status: Status
    items: list[NaverSearchItem] = []
    errors: list[ModuleError] = []
    http_status: int | None = None
    rate_limited: bool = False


def _err(status, code, message, *, retryable=False, http_status=None) -> NaverSearchResponse:
    return NaverSearchResponse(
        status=status,
        http_status=http_status,
        rate_limited=(code == ErrorCode.EXTERNAL_RATE_LIMITED),
        errors=[
            module_error(
                code, message, module="clients/naver_search",
                retryable=retryable, provider="naver", http_status=http_status,
            )
        ],
    )


def _is_retryable(resp: NaverSearchResponse) -> bool:
    return resp.status is Status.EXTERNAL_ERROR and any(e.retryable for e in resp.errors)


def search(req: NaverSearchRequest) -> NaverSearchResponse:
    """Issue a Naver search, retrying transient failures."""
    return with_retries(lambda: _search_once(req), _is_retryable)


def _search_once(req: NaverSearchRequest) -> NaverSearchResponse:
    base = _ENDPOINTS.get(req.endpoint)
    if base is None:
        return _err(Status.EXTERNAL_ERROR, ErrorCode.INTERNAL_ERROR,
                    "Unsupported search endpoint.")

    client_id = config.get_required_secret("NAVER_CLIENT_ID")
    client_secret = config.get_required_secret("NAVER_CLIENT_SECRET")
    if isinstance(client_id, ModuleError):
        return NaverSearchResponse(status=Status.EXTERNAL_ERROR, errors=[client_id])
    if isinstance(client_secret, ModuleError):
        return NaverSearchResponse(status=Status.EXTERNAL_ERROR, errors=[client_secret])

    display = max(1, min(int(req.display), 100))  # Naver hard max 100
    start = max(1, min(int(req.start), 1000))  # Naver hard max 1000
    params: dict[str, str] = {"query": req.query, "display": str(display), "start": str(start)}
    if req.sort:
        params["sort"] = req.sort

    # SSRF/allowlist validation against the fixed Naver host.
    from ..security import validate_outbound_url

    ssrf = validate_outbound_url(base, "naver_search")
    if ssrf is not None:
        return NaverSearchResponse(status=Status.EXTERNAL_ERROR, errors=[ssrf])

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "User-Agent": "ReportGuard/0.1",
    }
    timeout = httpx.Timeout(connect=1.5, read=req.deadline_ms / 1000.0, write=1.5, pool=1.5)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            # httpx encodes query params as UTF-8 percent-encoding.
            resp = client.get(base, params=params, headers=headers)
    except httpx.TimeoutException:
        return _err(Status.EXTERNAL_ERROR, ErrorCode.PROVIDER_TIMEOUT,
                    "Naver Search request timed out.", retryable=True)
    except httpx.HTTPError:
        return _err(Status.EXTERNAL_ERROR, ErrorCode.PROVIDER_UNAVAILABLE,
                    "Naver Search could not be reached.", retryable=True)

    # Log only non-sensitive fields (never the query text or credentials).
    rg_logging.log_event(
        "info", "naver_call",
        {"provider_name": "naver", "http_status": resp.status_code},
    )

    if resp.status_code == 429:
        return _err(Status.EXTERNAL_ERROR, ErrorCode.EXTERNAL_RATE_LIMITED,
                    "Naver Search rate limited the request.", retryable=True,
                    http_status=429)
    if resp.status_code in (403, 400):
        # 403 often signals quota exhaustion / auth problems.
        return _err(Status.EXTERNAL_ERROR, ErrorCode.EXTERNAL_QUOTA_EXCEEDED,
                    "Naver Search rejected the request (quota or auth).",
                    retryable=False, http_status=resp.status_code)
    if resp.status_code >= 500:
        return _err(Status.EXTERNAL_ERROR, ErrorCode.EXTERNAL_BAD_RESPONSE,
                    "Naver Search returned a server error.", retryable=True,
                    http_status=resp.status_code)
    if resp.status_code != 200:
        return _err(Status.EXTERNAL_ERROR, ErrorCode.EXTERNAL_BAD_RESPONSE,
                    "Naver Search returned an unexpected response.",
                    http_status=resp.status_code)

    try:
        raw_items = resp.json().get("items") or []
    except ValueError:
        return _err(Status.EXTERNAL_ERROR, ErrorCode.EXTERNAL_BAD_RESPONSE,
                    "Naver Search response could not be parsed.",
                    http_status=resp.status_code)

    items = [
        NaverSearchItem(
            title=it.get("title", ""),
            link=it.get("link", ""),
            description=it.get("description", ""),
            post_date=it.get("postdate"),
        )
        for it in raw_items
    ]
    return NaverSearchResponse(status=Status.OK, items=items, http_status=resp.status_code)


__all__ = [
    "NaverSearchRequest",
    "NaverSearchItem",
    "NaverSearchResponse",
    "search",
]
