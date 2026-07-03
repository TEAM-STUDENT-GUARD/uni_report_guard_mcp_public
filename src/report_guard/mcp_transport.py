"""MCP lifecycle + JSON-RPC envelope handling (Streamable HTTP).

Builds the low-level `mcp` Server, exposes tools/list and tools/call, and converts
normalized `PipelineResult`s into MCP `CallToolResult`s. It does NOT perform
tool-specific business validation beyond schema validation, and it distinguishes
JSON-RPC protocol errors (unknown tool / malformed request — raised) from tool
execution errors (returned as `isError: true` results).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import mcp.types as mcp_types
from mcp.server.lowlevel import Server

from . import SERVER_NAME, SERVER_VERSION
from . import logging as rg_logging
from . import pipeline_orchestrator, rate_limit, result_formatter, tool_registry
from .errors import ModuleError
from .schemas import PipelineResult, RequestContext, Status


def _to_mcp_tool(defn: tool_registry.ToolDefinition) -> mcp_types.Tool:
    return mcp_types.Tool(
        name=defn.name,
        title=defn.title,
        description=defn.description,
        inputSchema=defn.inputSchema,
        annotations=mcp_types.ToolAnnotations(**defn.annotations.as_dict()),
    )


def _new_context(tool_name: str, arguments: dict) -> RequestContext:
    return RequestContext(
        request_id=uuid.uuid4().hex,
        tool_name=tool_name,
        deadline_ms=pipeline_orchestrator.default_deadline_ms(),
        received_at=datetime.now(timezone.utc).isoformat(),
        language_hint=(arguments or {}).get("language"),
    )


def _error_call_result(err: ModuleError) -> mcp_types.CallToolResult:
    result = PipelineResult(
        status=Status.INVALID_INPUT,
        summary=err.message,
        next_actions=["Check the input fields and try again."],
        partial_failures=[err],
    )
    response = result_formatter.to_mcp_response(result)
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=response.content[0]["text"])],
        structuredContent=response.structuredContent,
        isError=True,
    )


def build_server() -> Server:
    server: Server = Server(name=SERVER_NAME, version=SERVER_VERSION)

    @server.list_tools()
    async def _list_tools() -> list[mcp_types.Tool]:
        return [_to_mcp_tool(d) for d in tool_registry.list_tools()]

    # validate_input=False: we run our own normalized validation so invalid input
    # comes back as a structured invalid_input tool result, not an SDK error string.
    @server.call_tool(validate_input=False)
    async def _call_tool(name: str, arguments: dict | None) -> mcp_types.CallToolResult:
        defn = tool_registry.resolve(name)
        if isinstance(defn, ModuleError):
            # Unknown tool is a protocol-level error.
            raise ValueError(f"Unknown tool: {name}")

        validated = tool_registry.validate_input(name, arguments or {})
        if isinstance(validated, ModuleError):
            return _error_call_result(validated)

        context = _new_context(name, validated)

        # Quota/abuse guard runs before any pipeline (and thus before external calls).
        cost = rate_limit.estimate_cost(name, validated)
        limited = rate_limit.check_request(context, cost)
        if limited is not None:
            return _error_call_result(limited)

        result = pipeline_orchestrator.execute(defn.pipeline, validated, context)

        rg_logging.log_event(
            "info",
            "tool_call",
            {
                "request_id": context.request_id,
                "tool_name": name,
                "status": str(result.status),
                "document_length": len(validated.get("document_text", ""))
                if isinstance(validated.get("document_text"), str)
                else 0,
            },
        )

        response = result_formatter.to_mcp_response(result)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=response.content[0]["text"])],
            structuredContent=response.structuredContent,
            isError=response.isError,
        )

    return server


__all__ = ["build_server"]
