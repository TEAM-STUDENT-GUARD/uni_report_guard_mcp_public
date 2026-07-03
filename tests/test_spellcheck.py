"""Slice 5 — spell-check pipeline with the mock provider (no network)."""

from __future__ import annotations

import json
import logging

from report_guard.pipelines import spellcheck
from report_guard.providers.spellcheck.mock_provider import MockSpellcheckProvider
from report_guard.schemas import RequestContext, Status


def _ctx():
    return RequestContext(
        request_id="t", tool_name="check_document_spelling", deadline_ms=3000,
        received_at="now",
    )


def _run(text, provider=None, **options):
    args = {"document_text": text}
    if options:
        args["options"] = options
    return spellcheck.run(args, _ctx(), provider=provider or MockSpellcheckProvider())


def test_detects_known_errors():
    r = _run("I recieve teh book.")
    assert r.status is Status.OK
    assert r.findings
    suggestions = " ".join(f.suggestion for f in r.findings)
    assert "receive" in suggestions and "the" in suggestions


def test_clean_text_no_findings():
    r = _run("This sentence is perfectly fine.")
    assert r.status is Status.NO_FINDINGS
    assert not r.findings


def test_korean_correction():
    r = _run("이렇게 하면 안되.")
    assert r.findings
    assert "안 돼" in r.findings[0].suggestion


def test_strip_reference_section_handles_collapsed_heading():
    # When the host collapses newlines, the 참고문헌 heading sits inline. It must still
    # be stripped (so reference titles are not spell-checked), while the 서론's prose
    # mention "참고문헌을" is preserved.
    doc = ("본론에서 참고문헌을 확인한다. 결론. "
           "참고문헌 [1] He, K. (2016). Deep Residual Learning. [2] Vaswani (2017).")
    stripped, dropped = spellcheck._strip_reference_section(doc)
    assert dropped is True
    assert "참고문헌을 확인한다" in stripped
    assert "[1] He" not in stripped and "Vaswani" not in stripped


def test_discloses_external_transmission_and_false_positives():
    r = _run("teh test.")
    blob = " ".join(r.limitations).lower()
    assert "external" in blob
    assert "false positive" in blob or "false positives" in blob


def test_provider_unavailable_is_external_error():
    r = _run("teh test.", provider=MockSpellcheckProvider(fail=True))
    assert r.status is Status.EXTERNAL_ERROR
    assert r.partial_failures


def test_provider_timeout_partial_when_some_results():
    # Timeout with no corrections -> external_error (mock returns no corrections).
    r = _run("teh test.", provider=MockSpellcheckProvider(timeout=True))
    assert r.status is Status.EXTERNAL_ERROR


def test_no_document_text_in_logs(caplog):
    secret = "recieve a wierd secret essay body"
    with caplog.at_level(logging.INFO, logger="report_guard"):
        _run(secret)
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "secret essay body" not in logged


def test_response_under_budget_many_errors():
    from report_guard import result_formatter

    text = " ".join(["teh recieve wierd"] * 200) + "."
    r = _run(text, max_findings=50)
    resp = result_formatter.to_mcp_response(r)
    size = len(resp.content[0]["text"]) + len(
        json.dumps(resp.structuredContent, ensure_ascii=False)
    )
    assert size < 24_000
