"""Slice 4 — guidance provider + the two guidance-only pipelines."""

from __future__ import annotations

import json

from report_guard import guidance_provider, result_formatter
from report_guard.errors import ErrorCode
from report_guard.pipelines import citation_format, required_fields, writing_structure
from report_guard.schemas import GuidanceDocument, RequestContext, Status


def _ctx(tool):
    return RequestContext(request_id="t", tool_name=tool, deadline_ms=3000, received_at="now")


def test_all_guidance_docs_load():
    for gid in ("CITATION_CHECK", "CITATION_FORMAT", "PLAGIARISM_CHECK", "GOOD_WRITING", "TO_HAVE"):
        doc = guidance_provider.load_guidance(gid)
        assert isinstance(doc, GuidanceDocument)
        assert doc.guidance_id == gid
        assert doc.version and doc.version != "0"
        assert doc.sections
        assert doc.expected_llm_output_format
        assert doc.limitations


def test_unknown_guidance_is_internal_error():
    err = guidance_provider.load_guidance("DOES_NOT_EXIST")
    assert getattr(err, "code", None) is ErrorCode.INTERNAL_ERROR


def test_writing_structure_pipeline():
    r = writing_structure.run({}, _ctx("get_writing_structure_guidance"))
    assert r.status is Status.OK
    assert r.guidance_id == "GOOD_WRITING"
    assert r.sections
    assert any("thesis" in s.body.lower() or s.checklist for s in r.sections)


def test_citation_format_pipeline():
    r = citation_format.run({}, _ctx("get_citation_format_guidance"))
    assert r.status is Status.OK
    assert r.guidance_id == "CITATION_FORMAT"
    assert r.sections
    blob = json.dumps(r.model_dump(mode="json"), ensure_ascii=False)
    # It is guidance about formatting, and points existence checks elsewhere.
    assert "표기" in blob or "APA" in blob
    assert "check_document_citations" in blob


def test_required_fields_pipeline_has_privacy_note():
    r = required_fields.run({}, _ctx("get_required_fields_guidance"))
    assert r.status is Status.OK
    assert r.guidance_id == "TO_HAVE"
    blob = json.dumps(r.model_dump(mode="json"), ensure_ascii=False)
    # Privacy minimization must be present and sensitive IDs discouraged.
    assert "최소" in blob  # data minimization
    assert "주민등록번호" in blob  # resident registration number discouraged


def test_guidance_result_under_budget():
    for pipeline in (writing_structure, required_fields):
        r = pipeline.run({}, _ctx("x"))
        resp = result_formatter.to_mcp_response(r)
        size = len(resp.content[0]["text"]) + len(
            json.dumps(resp.structuredContent, ensure_ascii=False)
        )
        assert size < 24_000


def test_guidance_result_is_pipeline_result_shaped():
    # GuidanceResult must satisfy PipelineResult so full_check can embed it.
    r = writing_structure.run({}, _ctx("x"))
    data = r.model_dump(mode="json")
    for key in ("status", "summary", "findings", "limitations", "next_actions", "links"):
        assert key in data
