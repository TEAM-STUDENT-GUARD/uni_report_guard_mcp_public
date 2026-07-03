"""Slice 8 — full_check composition, citation-skip, partial failure, size budget."""

from __future__ import annotations

import json

import pytest

from report_guard import result_formatter
from report_guard.pipelines import full_check
from report_guard.schemas import PipelineResult, RequestContext, Status


def _ctx():
    return RequestContext(
        request_id="t", tool_name="run_full_report_check", deadline_ms=3000,
        received_at="now",
    )


@pytest.fixture(autouse=True)
def _force_mock_spell(monkeypatch):
    # Keep spellcheck offline/deterministic during composition tests.
    monkeypatch.setenv("SPELLCHECK_PROVIDER", "mock")


def test_skips_citation_without_titles():
    r = full_check.run({"document_text": "Hello world. This is fine."}, _ctx())
    assert "citation" in r.metrics["skipped_pipelines"]
    assert "citation" not in r.sub_results
    assert any("Citation check was skipped" in lim for lim in r.limitations)


def test_runs_citation_with_titles():
    r = full_check.run(
        {"document_text": "Hello world.", "citation_titles": ["Some Paper"]}, _ctx()
    )
    assert "citation" in r.sub_results
    assert "citation" not in r.metrics["skipped_pipelines"]


def test_auto_extracts_references_from_own_line_heading():
    doc = ("결론.\n\n참고문헌\n[1] He, K. (2016). Deep Residual Learning.\n"
           "[2] Vaswani (2017). Attention Is All You Need.")
    assert full_check._extract_references(doc) == [
        "He, K. (2016). Deep Residual Learning.",
        "Vaswani (2017). Attention Is All You Need.",
    ]


def test_auto_extracts_references_from_collapsed_document():
    # Hosts often collapse newlines, leaving the 참고문헌 heading inline. The 서론 also
    # mentions "참고문헌을" in prose, which must NOT be mistaken for the heading.
    doc = ("서론 맞춤법, 인용, 분량, 참고문헌을 확인해야 한다. 결론. "
           "참고문헌 [1] He, K. (2016). Deep Residual Learning. "
           "[2] Vaswani (2017). Attention Is All You Need. [3] 박숙자. (2024). 대학 글쓰기.")
    refs = full_check._extract_references(doc)
    assert len(refs) == 3
    assert refs[0].startswith("He, K.")
    assert refs[2].startswith("박숙자")


def test_collapsed_references_are_not_skipped():
    doc = ("결론. 참고문헌 [1] He, K. (2016). Deep Residual Learning. "
           "[2] Vaswani (2017). Attention Is All You Need.")
    r = full_check.run({"document_text": doc}, _ctx())
    assert "citation" in r.sub_results
    assert "citation" not in r.metrics["skipped_pipelines"]


def test_prose_mention_of_references_is_not_a_section():
    doc = "이 보고서는 참고문헌을 반드시 확인해야 한다. 각주 [3]도 있다."
    assert full_check._extract_references(doc) == []


def test_counts_runs_and_aggregates():
    r = full_check.run({"document_text": "teh recieve test. Second sentence here."}, _ctx())
    assert "counts" in r.sub_results
    assert r.sub_results["counts"].status is Status.OK
    # Spelling findings aggregate into the top-level findings.
    assert r.metrics["total_findings"] == len(r.findings)


def test_partial_when_subpipeline_raises(monkeypatch):
    import report_guard.pipelines.plagiarism as pl

    def boom(args, context):
        raise RuntimeError("document body should not leak here")

    monkeypatch.setattr(pl, "run", boom)
    # full_check imports the module reference; patch the dict runner too.
    monkeypatch.setitem(full_check._RUNNERS, "plagiarism", boom)

    r = full_check.run({"document_text": "Hello world. Another sentence."}, _ctx())
    assert r.status is Status.PARTIAL
    # Other pipelines still produced results.
    assert r.sub_results["counts"].status is Status.OK
    blob = json.dumps(r.model_dump(mode="json"), ensure_ascii=False)
    assert "should not leak" not in blob


def test_invalid_input_without_document():
    r = full_check.run({}, _ctx())
    # tool_registry would normally reject this, but the pipeline guards too.
    assert r.status is Status.INVALID_INPUT


def test_full_check_under_budget_large_doc():
    big_doc = ("This is a sentence with teh recieve wierd errors. " * 400)
    r = full_check.run({"document_text": big_doc}, _ctx())
    resp = result_formatter.to_mcp_response(r)
    size = len(resp.content[0]["text"]) + len(
        json.dumps(resp.structuredContent, ensure_ascii=False)
    )
    assert size < 24_000
    # Status, summary, limitations, next_actions preserved after compression.
    assert resp.structuredContent["summary"]
    assert resp.structuredContent["limitations"]
    assert resp.structuredContent["next_actions"]


def test_full_check_routes_through_public_run_only():
    # Each runner must be a feature pipeline's public `run` entrypoint.
    from report_guard.pipelines import (
        citation,
        citation_format,
        counts,
        plagiarism,
        required_fields,
        spellcheck,
        writing_structure,
    )

    expected = {
        "counts": counts.run,
        "spellcheck": spellcheck.run,
        "plagiarism": plagiarism.run,
        "writing_structure": writing_structure.run,
        "required_fields": required_fields.run,
        "citation_format": citation_format.run,
        "citation": citation.run,
    }
    assert full_check._RUNNERS == expected
