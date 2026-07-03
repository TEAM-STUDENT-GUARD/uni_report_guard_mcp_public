"""Response-language policy: Korean-first tool responses, English on request.

Covers the user-facing acceptance cases: counts (ko/en, all four units), citation
skip/partial wording, guidance framing, and that internal error codes
(CONFIG_MISSING/PROVIDER_TIMEOUT) never reach the rendered text.
"""

from __future__ import annotations

from report_guard import i18n, result_formatter
from report_guard.errors import ErrorCode, module_error
from report_guard.pipeline_orchestrator import execute
from report_guard.schemas import PipelineResult, RequestContext, Status

_KO_DOC = (
    "최근 생성형 AI 코드 보조 도구가 빠르게 보급되고 있다. 그러나 생성된 코드는 항상 "
    "정확하지 않다. 따라서 학생은 결과를 검증해야 한다."
)
_EN_DOC = "Generative AI tools are spreading fast. The code is not always correct. Verify it."


def _ctx(tool, lang=None):
    return RequestContext(
        request_id="t", tool_name=tool, deadline_ms=3000, received_at="now",
        language_hint=lang,
    )


def _md(result) -> str:
    return result_formatter.to_mcp_response(result).content[0]["text"]


# --- language resolution ---------------------------------------------------
def test_resolve_language_rules():
    assert i18n.resolve_response_language("ko", _EN_DOC) == "ko"  # explicit wins
    assert i18n.resolve_response_language("en", _KO_DOC) == "en"  # explicit wins
    assert i18n.resolve_response_language("auto", _KO_DOC) == "ko"
    assert i18n.resolve_response_language("auto", _EN_DOC) == "en"
    assert i18n.resolve_response_language(None, "") == "ko"  # Korean-first default


# --- counts: all four units, both languages --------------------------------
def test_count_korean_includes_all_four_units():
    r = execute("counts", {"document_text": _KO_DOC}, _ctx("count_document_units"))
    md = _md(r)
    assert "✅ 검사 완료" in md
    assert "자(공백 포함)," in md and "단어," in md and "문장," in md and "문단" in md
    assert "characters" not in md


def test_count_english_preserved():
    r = execute("counts", {"document_text": _EN_DOC, "language": "en"},
                _ctx("count_document_units", "en"))
    md = _md(r)
    assert "✅ Checked" in md
    assert "characters" in md and "words" in md and "sentences" in md and "paragraphs" in md


# --- citation: skip wording + email env fallback path ----------------------
def test_citation_no_titles_korean_skip():
    r = execute("citation", {"citation_titles": []}, _ctx("check_document_citations", "ko"))
    md = _md(r)
    assert "참고문헌 항목이 없어" in md


def test_citation_partial_says_unconfirmed_not_complete():
    # A PARTIAL crossref result must never read as "verified/complete".
    r = PipelineResult(
        status=Status.PARTIAL,
        summary="참고문헌 2건을 Crossref 기준으로 확인했습니다. 0건은 확실히 일치했고 "
                "2건은 미확인입니다. 외부 조회 지연으로 일부 결과를 얻지 못해 ‘검증 완료’가 "
                "아니라 ‘미확인/부분 결과’로 보아야 합니다.",
        partial_failures=[module_error(ErrorCode.PROVIDER_TIMEOUT, "x",
                                       module="clients/crossref", retryable=True)],
        response_language="ko",
    )
    md = _md(r)
    assert "미확인" in md
    assert "PROVIDER_TIMEOUT" not in md  # internal code hidden


# --- guidance: framed as guidance, not a document inspection ---------------
def test_guidance_is_framed_as_guidance_korean():
    r = execute("writing_structure", {}, _ctx("get_writing_structure_guidance"))
    md = _md(r)
    # Framed as guidance (server did not inspect) AND directs the assistant to apply
    # it to the real document rather than relaying it.
    assert "검사하지 않았습니다" in md
    assert "가이드" in md
    assert "되돌려주지" in md or "그대로" in md


# --- internal error codes never surface ------------------------------------
def test_partial_failures_humanized_no_internal_codes():
    pf = [module_error(ErrorCode.CONFIG_MISSING, "x", module="config") for _ in range(6)]
    for lang in ("ko", "en"):
        r = PipelineResult(status=Status.EXTERNAL_ERROR, summary="s",
                           partial_failures=pf, response_language=lang)
        md = _md(r)
        assert "CONFIG_MISSING" not in md
        assert "config:" not in md
        # 6 identical causes collapse to a single humanized line.
        assert md.count("검색 설정" if lang == "ko" else "search setting") == 1
