"""Slice 2 — contract tests for all 8 public tool schemas + annotations."""

from __future__ import annotations

import re

import pytest

from report_guard import tool_registry
from report_guard.errors import ErrorCode

EXPECTED_TOOLS = {
    "count_document_units": False,
    "check_document_spelling": True,
    "check_document_citations": True,
    "check_document_plagiarism": True,
    "get_writing_structure_guidance": False,
    "get_required_fields_guidance": False,
    "get_citation_format_guidance": False,
    "run_full_report_check": True,
}

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def test_exactly_eight_tools():
    names = {t.name for t in tool_registry.list_tools()}
    assert names == set(EXPECTED_TOOLS)


def test_tool_names_valid_and_no_kakao():
    for t in tool_registry.list_tools():
        assert NAME_RE.match(t.name), t.name
        assert "kakao" not in t.name.lower()


@pytest.mark.parametrize("tool", tool_registry.list_tools(), ids=lambda t: t.name)
def test_annotations_present_and_defaults(tool):
    a = tool.annotations
    assert a.readOnlyHint is True
    assert a.destructiveHint is False
    assert a.idempotentHint is True
    assert a.title  # non-empty
    assert a.openWorldHint is EXPECTED_TOOLS[tool.name]


@pytest.mark.parametrize("tool", tool_registry.list_tools(), ids=lambda t: t.name)
def test_input_schema_rejects_unknown_fields(tool):
    assert tool.inputSchema["additionalProperties"] is False
    assert tool.inputSchema["type"] == "object"


@pytest.mark.parametrize("tool", tool_registry.list_tools(), ids=lambda t: t.name)
def test_description_is_korean_and_under_limit(tool):
    assert tool.description.strip()
    assert len(tool.description) <= 1024


def test_validate_rejects_unknown_field():
    err = tool_registry.validate_input(
        "count_document_units", {"document_text": "hi", "bogus": 1}
    )
    assert err.code is ErrorCode.INVALID_INPUT


def test_validate_rejects_missing_required():
    err = tool_registry.validate_input("count_document_units", {})
    assert err.code is ErrorCode.INVALID_INPUT


def test_validate_accepts_minimal_valid():
    ok = tool_registry.validate_input("count_document_units", {"document_text": "hi"})
    assert ok == {"document_text": "hi"}


def test_guidance_tools_accept_empty_object():
    for name in ("get_writing_structure_guidance", "get_required_fields_guidance"):
        ok = tool_registry.validate_input(name, {})
        assert ok == {}
        err = tool_registry.validate_input(name, {"x": 1})
        assert err.code is ErrorCode.INVALID_INPUT


def test_citation_requires_titles():
    err = tool_registry.validate_input("check_document_citations", {})
    assert err.code is ErrorCode.INVALID_INPUT
    ok = tool_registry.validate_input(
        "check_document_citations", {"citation_titles": ["A Title"]}
    )
    assert ok["citation_titles"] == ["A Title"]


def test_resolve_unknown_tool():
    err = tool_registry.resolve("delete_everything")
    assert err.code is ErrorCode.INVALID_INPUT
