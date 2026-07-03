"""Slice 7 — similarity scorer, Naver client (mocked), and plagiarism pipeline."""

from __future__ import annotations

import json
import logging

import httpx

from report_guard.clients import naver_search
from report_guard.pipelines import plagiarism
from report_guard.schemas import RequestContext, Status
from report_guard.similarity import scorer


def _ctx():
    return RequestContext(
        request_id="t", tool_name="check_document_plagiarism", deadline_ms=3000,
        received_at="now",
    )


# --- scorer ---
def test_score_identical_high():
    s = scorer.score_match("the quick brown fox", "the quick brown fox")
    assert s > 0.9


def test_score_unrelated_low():
    s = scorer.score_match("the quick brown fox", "완전히 다른 주제의 문장입니다")
    assert s < 0.3


def test_strip_markup():
    assert scorer.strip_markup("a <b>bold</b> word") == "a bold word"


def test_filter_threshold_and_sort():
    matches = [
        scorer.ScoredMatch(source_index=0, candidate_title="a", candidate_snippet="",
                           candidate_url="u1", score=0.4),
        scorer.ScoredMatch(source_index=1, candidate_title="b", candidate_snippet="",
                           candidate_url="u2", score=0.9),
    ]
    kept = scorer.filter_matches(matches, 0.6)
    assert [m.score for m in kept] == [0.9]


# --- pipeline with mocked Naver ---
def _mock_naver(monkeypatch, handler, env=True):
    if env:
        monkeypatch.setenv("NAVER_CLIENT_ID", "id")
        monkeypatch.setenv("NAVER_CLIENT_SECRET", "secret")
    transport = httpx.MockTransport(handler)

    class _C(httpx.Client):
        def __init__(self, *a, **k):
            k["transport"] = transport
            super().__init__(*a, **k)

    monkeypatch.setattr(naver_search.httpx, "Client", _C)


def test_plagiarism_flags_high_similarity(monkeypatch):
    sentence = "Climate change accelerates polar ice melt significantly."

    captured_queries = []

    def handler(request):
        captured_queries.append(str(request.url))
        body = {"items": [{"title": "Climate change accelerates polar ice melt significantly",
                           "link": "https://example.com/a",
                           "description": "Climate change accelerates polar ice melt significantly."}]}
        return httpx.Response(200, json=body)

    _mock_naver(monkeypatch, handler)
    doc = sentence + "\n\n" + "Another unrelated filler line about cooking pasta at home."
    r = plagiarism.run({"document_text": doc, "options": {"sentence_chunk_size": 1, "max_queries": 4, "similarity_threshold": 0.5}}, _ctx())
    assert r.status is Status.OK
    assert r.findings
    assert r.links and r.links[0].url == "https://example.com/a"
    # The whole document must never be sent as one query.
    assert all("Another unrelated filler" not in q or "Climate change" not in q for q in captured_queries)
    # Public-search limitation always present.
    assert any("private databases" in lim for lim in r.limitations)


def test_plagiarism_no_match_no_findings(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"items": []})

    _mock_naver(monkeypatch, handler)
    r = plagiarism.run({"document_text": "A unique sentence with no web match here."}, _ctx())
    assert r.status is Status.NO_FINDINGS


def test_plagiarism_rate_limited_partial(monkeypatch):
    def handler(request):
        return httpx.Response(429)

    _mock_naver(monkeypatch, handler)
    r = plagiarism.run({"document_text": "One. Two. Three. Four."}, _ctx())
    assert r.status in (Status.PARTIAL, Status.EXTERNAL_ERROR)
    assert r.metrics["naver_rate_limited"] is True


def test_no_evasion_in_next_actions(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"items": []})

    _mock_naver(monkeypatch, handler)
    r = plagiarism.run({"document_text": "Some sentence here."}, _ctx())
    blob = " ".join(r.next_actions).lower()
    assert "evade" not in blob and "avoid detection" not in blob


def test_secret_not_in_output_or_logs(monkeypatch, caplog):
    def handler(request):
        # Credentials are sent as headers; assert they are present on the request
        # but never surface in output/logs.
        assert request.headers.get("X-Naver-Client-Secret") == "supersecret"
        return httpx.Response(200, json={"items": []})

    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "supersecret")
    _mock_naver(monkeypatch, handler, env=False)
    with caplog.at_level(logging.INFO, logger="report_guard"):
        r = plagiarism.run({"document_text": "Check this sentence."}, _ctx())
    logged = " ".join(rec.getMessage() for rec in caplog.records)
    out = json.dumps(r.model_dump(mode="json"), ensure_ascii=False)
    assert "supersecret" not in logged
    assert "supersecret" not in out
