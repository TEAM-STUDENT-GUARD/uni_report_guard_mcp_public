"""Slice 6 — citation parser, Crossref client (mocked), and pipeline branching."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from report_guard.citation import parser
from report_guard.clients import crossref, kci
from report_guard.errors import ErrorCode
from report_guard.pipelines import citation
from report_guard.schemas import RequestContext, Status


def _ctx():
    return RequestContext(
        request_id="t", tool_name="check_document_citations", deadline_ms=3000,
        received_at="now",
    )


# --- parser ---
def test_parser_normalizes_and_strips_markers():
    qs = parser.normalize_titles(["1. A Study of Things", "[2] Another Work "])
    assert qs[0].normalized_title == "A Study of Things"
    assert qs[1].normalized_title == "Another Work"


def test_parser_rejects_empty():
    err = parser.normalize_titles([])
    assert err.code is ErrorCode.INVALID_INPUT
    err2 = parser.normalize_titles(["   "])
    assert err2.code is ErrorCode.INVALID_INPUT


# --- pipeline: no email anywhere -> still query Crossref anonymously (no mailto) ---
def test_no_email_queries_crossref_anonymously(monkeypatch):
    monkeypatch.delenv("USER_EMAIL", raising=False)
    seen = {"had_mailto": None}

    def handler(request):
        seen["had_mailto"] = "mailto=" in str(request.url)
        return httpx.Response(200, json={"message": {"items": []}})

    _mock_client(monkeypatch, handler)
    r = citation.run({"citation_titles": ["Some Distinctive Paper Title Here"]}, _ctx())
    # Real check runs (metrics present); CITATION_CHECK guidance is attached for
    # LLM follow-up, but it is a hybrid result, not guidance-only.
    assert seen["had_mailto"] is False
    assert r.metrics and r.metrics.get("checked") == 1
    assert getattr(r, "guidance_id", None) == "CITATION_CHECK"


# --- crossref client (mocked transport) ---
def _mock_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)

    class _C(httpx.Client):
        def __init__(self, *a, **k):
            k["transport"] = transport
            super().__init__(*a, **k)

    monkeypatch.setattr(crossref.httpx, "Client", _C)


def test_env_user_email_used_when_arg_missing(monkeypatch):
    # No user_email argument, but USER_EMAIL is set in the environment -> Crossref
    # is queried (polite pool) instead of falling back to guidance mode.
    monkeypatch.setenv("USER_EMAIL", "env-user@example.com")
    seen = {"mailto": None}

    def handler(request):
        url = str(request.url)
        if "semanticscholar" in url:  # S2 pre-check: no match -> Crossref fallback
            return httpx.Response(404, json={"error": "No match"})
        assert "mailto=" in url
        seen["mailto"] = "env-user" in url  # @ is URL-encoded as %40 in the query
        return httpx.Response(200, json={"message": {"items": []}})

    _mock_client(monkeypatch, handler)
    r = citation.run({"citation_titles": ["Some Distinctive Paper Title Here"]}, _ctx())
    assert seen["mailto"] is True
    assert r.metrics and r.metrics.get("checked") == 1  # real check ran (polite pool)


def test_crossref_success(monkeypatch):
    def handler(request):
        if "semanticscholar" in str(request.url):  # no S2 match -> Crossref fallback
            return httpx.Response(404, json={"error": "No match"})
        assert "mailto" in str(request.url)  # email passed to client only
        body = {
            "message": {
                "items": [
                    {
                        "title": ["Attention Is All You Need"],
                        "DOI": "10.5555/x",
                        "publisher": "NeurIPS",
                        "issued": {"date-parts": [[2017]]},
                        "author": [{"given": "A", "family": "Vaswani"}],
                        "URL": "https://doi.org/10.5555/x",
                        "score": 90.0,
                    }
                ]
            }
        }
        return httpx.Response(200, json=body)

    _mock_client(monkeypatch, handler)
    r = citation.run(
        {"citation_titles": ["Attention Is All You Need"], "user_email": "a@b.com"},
        _ctx(),
    )
    assert r.status is Status.OK
    assert r.findings and r.findings[0].confidence.value == "high"
    assert r.links and "doi.org" in r.links[0].url
    assert any("Crossref" in lim or "academic" in lim for lim in r.limitations)


def test_crossref_no_match_not_no_findings(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"message": {"items": []}})

    _mock_client(monkeypatch, handler)
    r = citation.run(
        {"citation_titles": ["Nonexistent Title"], "user_email": "a@b.com"}, _ctx()
    )
    # No candidate must NOT collapse to no_findings.
    assert r.status in (Status.OK, Status.PARTIAL)
    assert r.status is not Status.NO_FINDINGS


def test_reordered_title_is_not_confident_match(monkeypatch):
    # Same words, different order = a DIFFERENT work. Must not be a high-confidence match.
    def handler(request):
        body = {"message": {"items": [
            {"title": ["Is Attention All You Need?"], "DOI": "10.1/x",
             "URL": "https://doi.org/10.1/x", "score": 33.0, "issued": {"date-parts": [[2025]]}},
        ]}}
        return httpx.Response(200, json=body)

    _mock_client(monkeypatch, handler)
    r = citation.run(
        {"citation_titles": ["Attention Is All You Need"], "user_email": "a@b.com"}, _ctx()
    )
    assert r.metrics["confident_matches"] == 0
    f = r.findings[0]
    assert f.confidence.value == "low"
    # Not asserted as a confident match (title is Korean by default, English on request).
    title = f.title.lower()
    assert (
        "verify" in title or "no confident" in title
        or "확인 필요" in f.title or "일치 없음" in f.title
    )


def test_exact_title_is_high_confidence(monkeypatch):
    def handler(request):
        body = {"message": {"items": [
            {"title": ["Attention Is All You Need"], "DOI": "10.1/real",
             "URL": "https://doi.org/10.1/real", "score": 90.0, "issued": {"date-parts": [[2017]]}},
        ]}}
        return httpx.Response(200, json=body)

    _mock_client(monkeypatch, handler)
    r = citation.run(
        {"citation_titles": ["attention is all you need"], "user_email": "a@b.com"}, _ctx()
    )
    assert r.metrics["confident_matches"] == 1
    assert r.findings[0].confidence.value == "high"


def test_crossref_rate_limited_is_partial(monkeypatch):
    def handler(request):
        return httpx.Response(429)

    _mock_client(monkeypatch, handler)
    r = citation.run(
        {"citation_titles": ["X"], "user_email": "a@b.com"}, _ctx()
    )
    assert r.status is Status.PARTIAL
    assert r.partial_failures


def test_email_not_logged(monkeypatch, caplog):
    def handler(request):
        return httpx.Response(200, json={"message": {"items": []}})

    _mock_client(monkeypatch, handler)
    with caplog.at_level(logging.INFO, logger="report_guard"):
        citation.run(
            {"citation_titles": ["X"], "user_email": "private@secret.com"}, _ctx()
        )
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "private@secret.com" not in logged


def test_crossref_no_raw_body_in_error(monkeypatch):
    def handler(request):
        return httpx.Response(500, text="<html>internal stack trace secret</html>")

    _mock_client(monkeypatch, handler)
    resp = crossref.search_work(
        crossref.CrossrefSearchRequest(query_title="x", mailto="a@b.com")
    )
    blob = json.dumps([e.model_dump(mode="json") for e in resp.errors])
    assert "stack trace secret" not in blob


# --- Semantic Scholar: primary route for English titles without a DOI ---
_S2_MATCH = {
    "data": [{
        "paperId": "abc123",
        "title": "Attention Is All You Need",
        "venue": "Neural Information Processing Systems",
        "year": 2017,
        "citationCount": 182292,
        "externalIds": {"ArXiv": "1706.03762"},
        "authors": [{"name": "Ashish Vaswani"}],
    }]
}


def test_english_title_confirmed_via_semantic_scholar(monkeypatch):
    def handler(request):
        if "semanticscholar" in str(request.url):
            return httpx.Response(200, json=_S2_MATCH)
        raise AssertionError("Crossref must not be called when S2 confirms")

    _mock_client(monkeypatch, handler)
    r = citation.run({"citation_titles": ["Attention Is All You Need"]}, _ctx())
    assert r.metrics["confident_matches"] == 1
    assert r.findings[0].title == "Semantic Scholar 확인됨"
    assert r.findings[0].confidence.value == "high"
    assert r.links and "semanticscholar.org" in r.links[0].url


def test_s2_confirmation_cross_checks_doi_via_crossref(monkeypatch):
    seen = {"doi_lookup": False}

    def handler(request):
        url = str(request.url)
        if "semanticscholar" in url:
            body = {"data": [{
                "paperId": "p1", "title": "Deep Residual Learning for Image Recognition",
                "venue": "CVPR", "year": 2016, "citationCount": 231990,
                "externalIds": {"DOI": "10.1109/cvpr.2016.90"},
            }]}
            return httpx.Response(200, json=body)
        # The only Crossref call must be the /works/{doi} registry cross-check.
        assert "10.1109" in url
        seen["doi_lookup"] = True
        body = {"message": {"DOI": "10.1109/cvpr.2016.90",
                            "title": ["Deep Residual Learning for Image Recognition"]}}
        return httpx.Response(200, json=body)

    _mock_client(monkeypatch, handler)
    r = citation.run(
        {"citation_titles": ["Deep Residual Learning for Image Recognition"]}, _ctx()
    )
    assert seen["doi_lookup"] is True
    assert r.metrics["confident_matches"] == 1
    assert "교차 확인" in r.findings[0].title or "Cross-confirmed" in r.findings[0].title


def test_s2_api_key_sent_as_header_only(monkeypatch):
    from report_guard.clients import semantic_scholar

    monkeypatch.setenv("S2_API_KEY", "test-s2-key")
    seen = {"key": None, "url": None}

    def handler(request):
        seen["key"] = request.headers.get("x-api-key")
        seen["url"] = str(request.url)
        return httpx.Response(404, json={"error": "No match"})

    _mock_client(monkeypatch, handler)
    resp = semantic_scholar.match_title("Some Title")
    assert resp.paper is None
    assert seen["key"] == "test-s2-key"
    assert "test-s2-key" not in seen["url"]  # key travels in the header, not the URL


def test_s2_failure_falls_back_to_crossref_silently(monkeypatch):
    def handler(request):
        if "semanticscholar" in str(request.url):
            return httpx.Response(503)
        body = {"message": {"items": [
            {"title": ["Some Distinctive Paper Title Here"], "DOI": "10.1/y",
             "URL": "https://doi.org/10.1/y", "issued": {"date-parts": [[2020]]}}]}}
        return httpx.Response(200, json=body)

    _mock_client(monkeypatch, handler)
    r = citation.run({"citation_titles": ["Some Distinctive Paper Title Here"]}, _ctx())
    assert r.metrics["confident_matches"] == 1  # Crossref fallback confirmed it
    assert r.status is Status.OK  # an S2 miss is silent, not a partial failure


# --- ambiguous exact titles: confirm only a citation-count-dominant record ---
def _dup_items(canon_citations: int, dup_citations: int) -> list[dict]:
    return [
        {"title": ["A Very Distinctive Paper Title Indeed"], "DOI": "10.1/canon",
         "URL": "https://doi.org/10.1/canon", "issued": {"date-parts": [[2017]]},
         "is-referenced-by-count": canon_citations},
        {"title": ["A Very Distinctive Paper Title Indeed"], "DOI": "10.9/dup",
         "URL": "https://doi.org/10.9/dup", "issued": {"date-parts": [[2025]]},
         "is-referenced-by-count": dup_citations},
    ]


def _mock_s2_miss_crossref_items(monkeypatch, items):
    def handler(request):
        if "semanticscholar" in str(request.url):
            return httpx.Response(404, json={"error": "No match"})
        return httpx.Response(200, json={"message": {"items": items}})

    _mock_client(monkeypatch, handler)


def test_duplicate_titles_confirmed_when_one_dominates(monkeypatch):
    _mock_s2_miss_crossref_items(monkeypatch, _dup_items(120000, 40))
    r = citation.run(
        {"citation_titles": ["A Very Distinctive Paper Title Indeed"]}, _ctx()
    )
    assert r.metrics["confident_matches"] == 1
    assert r.links and "10.1/canon" in r.links[0].url


def test_duplicate_titles_stay_ambiguous_without_dominance(monkeypatch):
    _mock_s2_miss_crossref_items(monkeypatch, _dup_items(60, 40))
    r = citation.run(
        {"citation_titles": ["A Very Distinctive Paper Title Indeed"]}, _ctx()
    )
    assert r.metrics["confident_matches"] == 0
    assert "확인 필요" in r.findings[0].title or "Ambiguous" in r.findings[0].title


# --- routing: an English entry carrying a DOI -> Crossref /works/{doi} ---
def test_doi_entry_confirmed_via_doi_lookup(monkeypatch):
    def handler(request):
        # DOI path hits /works/10.1000/xyz, not the title-search endpoint.
        assert "10.1000" in str(request.url)
        body = {"message": {"DOI": "10.1000/xyz", "title": ["A Real Existing Paper"],
                            "URL": "https://doi.org/10.1000/xyz",
                            "issued": {"date-parts": [[2021]]}}}
        return httpx.Response(200, json=body)

    _mock_client(monkeypatch, handler)
    r = citation.run(
        {"citation_titles": ["A Real Existing Paper (2021). https://doi.org/10.1000/xyz"]}, _ctx()
    )
    assert r.metrics["confident_matches"] == 1
    assert r.findings[0].confidence.value == "high"


def test_doi_not_registered_is_unconfirmed_not_confirmed(monkeypatch):
    def handler(request):
        return httpx.Response(404, text="Resource not found.")

    _mock_client(monkeypatch, handler)
    r = citation.run({"citation_titles": ["Paper doi:10.9999/nope"]}, _ctx())
    assert r.metrics["confident_matches"] == 0
    # DOI given but not registered -> a distinct low-confidence finding, not a match.
    assert r.findings[0].confidence.value == "low"
    assert "DOI" in r.findings[0].title


# --- routing: Korean title -> KCI only; no server-side web search fallback.
# When KCI cannot confirm, the item is left "미확인" for the host LLM to verify with
# its own web search (per the project silhouette). The server never calls Naver here.
def test_korean_title_unconfirmed_without_kci_key(monkeypatch):
    monkeypatch.delenv("KCI_API_KEY", raising=False)

    def handler(request):  # Crossref must NOT be the route for a Korean title.
        raise AssertionError("Korean titles must not hit Crossref")

    _mock_client(monkeypatch, handler)
    r = citation.run({"citation_titles": ["한국어 논문 제목"]}, _ctx())
    assert r.metrics["confident_matches"] == 0
    assert r.metrics["candidates"] == 0
    assert r.metrics["unconfirmed"] == 1
    assert r.findings[0].title == "미확인"


# --- KCI routing: Korean journal titles verified via KCI (LLM verifies the rest) ---
_KCI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<MetaData><outputData><result><total>1</total></result>
<record><journalInfo><journal-name>테스트학술지</journal-name><pub-year>2018</pub-year></journalInfo>
<articleInfo article-id="ART001">
<title-group><article-title lang="original">컴퓨터 학습을 통한 디지털 에이징</article-title></title-group>
<author-group><author>홍길동</author></author-group>
<url>https://www.kci.go.kr/x</url></articleInfo></record></outputData></MetaData>"""

_KCI_EMPTY = ('<?xml version="1.0" encoding="UTF-8"?><MetaData><outputData>'
              '<result><total>0</total></result></outputData></MetaData>')


def _mock_kci(monkeypatch, kci_xml):
    """Patch the KCI upstream (Korean titles route only to KCI now)."""
    monkeypatch.setenv("KCI_API_KEY", "kcikey")

    def dispatch(request):
        return httpx.Response(200, text=kci_xml)

    transport = httpx.MockTransport(dispatch)

    class _C(httpx.Client):
        def __init__(self, *a, **k):
            k["transport"] = transport
            super().__init__(*a, **k)

    monkeypatch.setattr(kci.httpx, "Client", _C)


def test_korean_title_confirmed_via_kci(monkeypatch):
    _mock_kci(monkeypatch, _KCI_XML)
    r = citation.run({"citation_titles": ["컴퓨터 학습을 통한 디지털 에이징"]}, _ctx())
    assert r.metrics["confident_matches"] == 1
    assert r.findings[0].title == "KCI 확인됨"
    assert r.links and "kci.go.kr" in r.links[0].url


def test_korean_title_unconfirmed_when_kci_empty(monkeypatch):
    _mock_kci(monkeypatch, _KCI_EMPTY)
    r = citation.run({"citation_titles": ["컴퓨터 학습을 통한 디지털 에이징"]}, _ctx())
    assert r.metrics["confident_matches"] == 0
    assert r.metrics["candidates"] == 0
    assert r.metrics["unconfirmed"] == 1  # KCI missed → 미확인 (LLM verifies via web search)
