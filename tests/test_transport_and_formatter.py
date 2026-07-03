"""Slice 2 — transport boundary, orchestrator routing, and formatter size budget."""

from __future__ import annotations

import asyncio

import mcp.types as mcp_types

from report_guard import result_formatter, tool_registry
from report_guard.mcp_transport import build_server
from report_guard.pipeline_orchestrator import execute
from report_guard.schemas import (
    Confidence,
    Evidence,
    Finding,
    LinkResult,
    PipelineResult,
    RequestContext,
    Severity,
    Status,
)


def _ctx(tool="count_document_units"):
    return RequestContext(
        request_id="t", tool_name=tool, deadline_ms=3000, received_at="now"
    )


def test_transport_lists_all_tools_without_pipeline_imports():
    server = build_server()
    handler = server.request_handlers[mcp_types.ListToolsRequest]
    req = mcp_types.ListToolsRequest(method="tools/list")
    result = asyncio.run(handler(req))
    tools = result.root.tools
    assert len(tools) == 8
    assert {t.name for t in tools} == {t.name for t in tool_registry.list_tools()}
    # Each MCP tool carries the required annotations.
    for t in tools:
        assert t.annotations is not None
        assert t.annotations.readOnlyHint is True
        assert t.annotations.idempotentHint is True


def test_call_tool_stub_returns_structured_result():
    server = build_server()
    handler = server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(
            name="count_document_units", arguments={"document_text": "hi"}
        ),
    )
    result = asyncio.run(handler(req)).root
    assert result.isError is False
    assert result.structuredContent["status"] in {s.value for s in Status}
    assert result.content[0].text.startswith("**Report Guard")


def test_call_tool_unknown_field_is_invalid_input():
    server = build_server()
    handler = server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(
            name="count_document_units", arguments={"document_text": "hi", "x": 1}
        ),
    )
    result = asyncio.run(handler(req)).root
    assert result.isError is True
    assert result.structuredContent["status"] == "invalid_input"


def test_orchestrator_isolates_pipeline_exception(monkeypatch):
    import report_guard.pipelines.counts as counts

    def boom(args, context):
        raise RuntimeError("document body leak should never appear")

    monkeypatch.setattr(counts, "run", boom)
    result = execute("counts", {"document_text": "secret"}, _ctx())
    assert result.status is Status.INTERNAL_ERROR
    # The raw exception text must not surface.
    assert "leak" not in result.summary


def test_formatter_compresses_oversized_result():
    findings = [
        Finding(
            id=str(i),
            category="plagiarism_risk",
            severity=Severity.LOW,
            confidence=Confidence.LOW,
            title=f"match {i}",
            message="x" * 500,
            evidence=[Evidence(kind="external_match", excerpt="y" * 1000)],
        )
        for i in range(500)
    ]
    big = PipelineResult(
        status=Status.OK,
        summary="big result",
        findings=findings,
        limitations=["public web only"],
        next_actions=["review"],
        links=[LinkResult(title=f"l{i}", url=f"https://x/{i}") for i in range(300)],
    )
    response = result_formatter.to_mcp_response(big)
    import json

    size = len(response.content[0]["text"]) + len(
        json.dumps(response.structuredContent, ensure_ascii=False)
    )
    assert size < 24_000
    # Status, summary, limitations, next_actions preserved.
    assert response.structuredContent["status"] == "ok"
    assert response.structuredContent["limitations"]
    assert response.structuredContent["next_actions"]
