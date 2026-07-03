"""pipelines/plagiarism — public-web plagiarism-risk signals via Naver Search.

Chunks the document into a bounded number of sentence queries, searches each via
clients/naver_search, scores similarity against result title/snippet, and returns
only above-threshold links as risk signals (never a verdict). Attaches
PLAGIARISM_CHECK guidance and always states public-search limitations. Naver only
ever receives bounded query chunks, never the whole document; no evasion advice.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .. import i18n
from ..config import get_int_limit, get_limit
from ..clients import naver_search
from ..errors import ModuleError
from ..guidance_provider import load_guidance
from ..schemas import (
    Confidence,
    Evidence,
    Finding,
    GuidanceResult,
    LinkResult,
    PipelineResult,
    RequestContext,
    Severity,
    Status,
    TextLocation,
)
from ..security import sanitize_user_text, validate_document_size
from ..similarity import scorer
from ..text import chunker, segmentation

_PUBLIC_LIMITATION = (
    "Public-web checking is not a complete plagiarism judgment. It cannot see "
    "private databases, paid plagiarism DBs, school submission archives, text in "
    "images/PDFs, or unindexed material. A match may be a coincidence or a "
    "correctly-cited quotation."
)
_PUBLIC_LIMITATION_KO = (
    "공개 웹 검색 기반 점검은 완전한 표절 판정이 아닙니다. 비공개 데이터베이스, 유료 "
    "표절 검사 DB, 학교 제출물 보관소, 이미지/PDF 속 텍스트, 검색되지 않는 자료는 "
    "확인할 수 없습니다. 유사한 결과가 나와도 우연이거나 올바르게 인용한 문장일 수 있습니다."
)

# Bounded concurrency for the per-chunk Naver searches — polite to the free API while
# keeping latency low even when max_queries is raised for fuller document coverage.
_MAX_PARALLEL = 4


def _severity_for(score: float) -> Severity:
    if score >= 0.85:
        return Severity.HIGH
    if score >= 0.7:
        return Severity.MEDIUM
    return Severity.LOW


def _confidence_for(score: float) -> Confidence:
    if score >= 0.85:
        return Confidence.MEDIUM
    return Confidence.LOW


def run(args: dict, context: RequestContext) -> PipelineResult:
    document_text = args.get("document_text", "")
    options = args.get("options") or {}
    rlang = i18n.resolve_response_language(context.language_hint, document_text)
    ko = rlang == "ko"

    size_err = validate_document_size(document_text)
    if size_err is not None:
        return PipelineResult(
            status=Status.INVALID_INPUT,
            summary=("문서가 너무 커서 검사할 수 없습니다." if ko
                     else "Document is too large to check."),
            limitations=(["문서 길이를 줄인 뒤 다시 시도하세요."] if ko
                         else ["Reduce the document length and try again."]),
            next_actions=(["더 짧은 일부만 제출하세요."] if ko
                          else ["Submit a shorter excerpt."]),
            partial_failures=[size_err],
            response_language=rlang,
        )

    text = sanitize_user_text(document_text)
    language = segmentation.detect_language(text, context.language_hint)

    chunk_size = int(options.get("sentence_chunk_size", 2))
    max_queries = min(int(options.get("max_queries", get_int_limit("NAVER_MAX_QUERIES"))),
                      get_int_limit("NAVER_MAX_QUERIES"))
    threshold = float(options.get("similarity_threshold", get_limit("NAVER_SIMILARITY_THRESHOLD")))
    display = get_int_limit("NAVER_MAX_DISPLAY")
    max_results = int(options.get("max_results", display))

    chunks = chunker.chunks_from_document(text, chunk_size, max_queries, language)
    if not chunks:
        return PipelineResult(
            status=Status.NO_FINDINGS,
            summary=("검사할 문장을 찾지 못했습니다." if ko
                     else "No checkable sentences were found."),
            limitations=[_PUBLIC_LIMITATION_KO if ko else _PUBLIC_LIMITATION],
            next_actions=[],
            response_language=rlang,
        )

    matches: list[scorer.ScoredMatch] = []
    partial: list[ModuleError] = []
    queries_run = 0
    result_count = 0
    rate_limited = False

    # Search chunks concurrently (bounded) so fuller coverage doesn't raise latency;
    # each call gets a generous read timeout because the calls run in parallel.
    per_call_ms = max(2_500, context.deadline_ms // max(1, min(len(chunks), _MAX_PARALLEL)))

    def _search(chunk):
        return chunk, naver_search.search(
            naver_search.NaverSearchRequest(
                query=chunk.query_text, display=min(display, 100),
                endpoint="webkr", deadline_ms=per_call_ms,
            )
        )

    with ThreadPoolExecutor(max_workers=min(_MAX_PARALLEL, len(chunks))) as ex:
        responses = list(ex.map(_search, chunks))

    for chunk, resp in responses:
        queries_run += 1
        if resp.status is Status.EXTERNAL_ERROR:
            partial.extend(resp.errors)
            rate_limited = rate_limited or resp.rate_limited
            continue
        for item in resp.items:
            result_count += 1
            candidate = f"{scorer.strip_markup(item.title)} {scorer.strip_markup(item.description)}"
            score = scorer.score_match(chunk.query_text, candidate)
            matches.append(
                scorer.ScoredMatch(
                    source_index=chunk.index,
                    candidate_title=scorer.strip_markup(item.title)[:120],
                    candidate_snippet=scorer.strip_markup(item.description)[:200],
                    candidate_url=item.link,
                    score=score,
                    source_text=chunk.query_text[:200],
                )
            )

    suspects = scorer.filter_matches(matches, threshold)[:max_results]

    findings: list[Finding] = []
    links: list[LinkResult] = []
    for i, m in enumerate(suspects):
        sev = _severity_for(m.score)
        conf = _confidence_for(m.score)
        findings.append(
            Finding(
                id=f"pl-{i}",
                category="plagiarism_risk",
                severity=sev,
                confidence=conf,
                title=(f"유사한 공개 텍스트 ({m.score:.2f})" if ko
                       else f"Similar public text ({m.score:.2f})"),
                message=(f"내 문서 구절 «{m.source_text}» 이(가) 공개 웹페이지와 유사합니다: {m.candidate_title}" if ko
                         else f"Your passage «{m.source_text}» resembles a public page: {m.candidate_title}"),
                evidence=[
                    Evidence(
                        kind="external_match",
                        excerpt=m.candidate_snippet[:160],
                        source=m.candidate_url,
                        score=m.score,
                        location=TextLocation(sentence_index=m.source_index),
                    )
                ],
                suggestion=("이 구절이 본인의 글이 아니라면 출처를 밝히거나 인용하거나 "
                            "출처를 표기해 다시 쓰세요." if ko
                            else "If this passage is not yours, cite it, quote it, or rewrite with attribution."),
            )
        )
        links.append(
            LinkResult(title=m.candidate_title or m.candidate_url, url=m.candidate_url,
                       source="naver", confidence=conf)
        )

    # Attach PLAGIARISM_CHECK guidance content (best-effort). The guidance doc is
    # Korean-first, so the user-facing limitation uses the localized constants here
    # (not the doc's limitations) to keep English responses in English.
    guidance_doc = load_guidance("PLAGIARISM_CHECK")
    limitations = [_PUBLIC_LIMITATION_KO] if ko else [_PUBLIC_LIMITATION]
    expected_format = ""
    sections = []
    if not isinstance(guidance_doc, ModuleError):
        expected_format = guidance_doc.expected_llm_output_format
        sections = guidance_doc.sections

    metrics = {
        "query_count": queries_run,
        "result_count": result_count,
        "suspect_match_count": len(suspects),
        "threshold": threshold,
        "naver_rate_limited": rate_limited,
    }

    if partial and not suspects:
        status = Status.PARTIAL if queries_run > len(partial) else Status.EXTERNAL_ERROR
    elif partial:
        status = Status.PARTIAL
    elif not suspects:
        status = Status.NO_FINDINGS
    else:
        status = Status.OK

    if ko:
        if status is Status.NO_FINDINGS:
            summary = (
                "유사도 기준을 넘는 공개 웹 일치 항목을 찾지 못했습니다. 다만 이것이 "
                "독창성을 보장하지는 않습니다."
            )
        elif status is Status.EXTERNAL_ERROR:
            summary = (
                "표절 위험 평가는 완료되지 않았습니다. 검색에 필요한 설정 또는 검증 대상 "
                "정보가 부족하여 공개 웹 검색 기반 유사도 검사를 수행하지 못했습니다. 따라서 "
                "이 결과는 ‘표절 위험 없음’이 아니라 ‘평가 불가’로 해석해야 합니다."
            )
        else:
            summary = f"유사도 기준을 넘는 공개 웹 일치 항목이 {len(suspects)}건 확인되었습니다."
            if partial:
                summary += " 일부 검색은 완료되지 못했습니다."
        _own_search_ko = (
            "[어시스턴트 수행] 웹 검색 도구가 있으면 서버의 네이버 1차 검색에 그치지 말고 "
            "핵심 문장을 직접 재검색해 2차로 확인하세요. 웹 검색 도구가 없으면 2차 확인은 "
            "하지 못했다고 결과에 명시하세요."
        )
        if status is Status.NO_FINDINGS:
            next_actions = [
                "[사용자 안내] 별도로 확인할 유사 구절은 없습니다. 다만 공개 웹 기준이라 "
                "독창성을 보장하지는 않으니, 인용이 필요한 부분은 스스로 점검하세요.",
                _own_search_ko,
            ]
        elif status is Status.EXTERNAL_ERROR:
            next_actions = [
                "검색 설정을 확인하고 잠시 후 다시 시도하거나, 의심 문장을 공개 웹에서 직접 검색해 확인하세요.",
            ]
        else:
            next_actions = [
                "[사용자 안내] 표시된 각 문장을 검토해 출처를 밝히거나 인용 또는 재작성으로 "
                "보완하세요.",
                _own_search_ko,
            ]
    else:
        if status is Status.NO_FINDINGS:
            summary = "No above-threshold public matches found. This is not a guarantee of originality."
        elif status is Status.EXTERNAL_ERROR:
            summary = "The search service was unavailable; plagiarism risk could not be assessed."
        else:
            summary = f"{len(suspects)} public match(es) above the similarity threshold."
            if partial:
                summary += " Some queries failed."
        _own_search_en = (
            "[assistant] If you have a web search tool, don't rely only on the server's "
            "Naver pass — re-search key sentences yourself as a second check. If you have "
            "no web search tool, state explicitly that no second-pass check was done."
        )
        if status is Status.NO_FINDINGS:
            next_actions = [
                "[relay to user] No suspect passages to review. This is not a guarantee of "
                "originality, so still cite sources where needed.",
                _own_search_en,
            ]
        elif status is Status.EXTERNAL_ERROR:
            next_actions = [
                "Check the search configuration and retry, or search suspect sentences on the public web yourself.",
            ]
        else:
            next_actions = [
                "[relay to user] Review each flagged passage and add a citation or rewrite "
                "with attribution.",
                _own_search_en,
            ]

    result = GuidanceResult(
        status=status,
        summary=summary,
        findings=findings,
        metrics=metrics,
        limitations=limitations,
        next_actions=next_actions,
        links=links,
        partial_failures=partial,
        guidance_id="PLAGIARISM_CHECK",
        guidance_version=getattr(guidance_doc, "version", "0")
        if not isinstance(guidance_doc, ModuleError) else "0",
        sections=sections,
        expected_llm_output_format=expected_format,
        response_language=rlang,
    )
    return result


__all__ = ["run"]
