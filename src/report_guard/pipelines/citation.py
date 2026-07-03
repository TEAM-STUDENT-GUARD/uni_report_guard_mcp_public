"""pipelines/citation — citation existence verification.

Per-title routing by language (never invents inputs, never returns no_findings on a
miss); the DOI does not override the language route:
  1. Korean title  -> KCI (Korea Citation Index) lookup.
  2. English title -> Crossref DOI lookup if the entry carries a DOI; else Semantic
     Scholar best-title-match (covers NeurIPS/CVPR/arXiv works Crossref misses) with
     a best-effort Crossref DOI-registry cross-check on its match, then Crossref
     title search as the fallback.

Whatever the server cannot confirm is left "미확인" (unconfirmed) — never asserted as
fake — and the host LLM is asked to verify it with its OWN web search as a second pass
(per the project silhouette: "LLM이 직접 검색해서 자체 웹서치 기능 사용"). The pipeline
itself makes no web-search calls; verification against the open web is the LLM's job.

Result wording is kept distinct so the user is never misled:
  - "KCI 확인됨" / "Crossref 확인됨": academic-metadata match (high confidence).
  - "유사 후보(확인 필요)": a close but non-exact record — verify author/year/DOI.
  - "미확인": no match — not proof the source is fake; verify via web search/RISS/DBpia.

An email (explicit `user_email`, else `USER_EMAIL` env) is only a politeness
identifier for Crossref's polite pool; queries run anonymously without one. The user
is never prompted for it and it is never logged.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

from .. import config
from ..citation.parser import CitationQuery, normalize_titles
from ..clients import crossref, kci, semantic_scholar
from ..errors import ModuleError
from ..guidance_provider import load_guidance
from ..schemas import (
    Confidence,
    CrossrefWorkSummary,
    Evidence,
    Finding,
    GuidanceResult,
    LinkResult,
    PipelineResult,
    RequestContext,
    Status,
)
from ..security import validate_email_for_mailto
from ..similarity import scorer

_METADATA_LIMITATION = (
    "English titles are checked against Semantic Scholar (covers conference papers "
    "and arXiv preprints) and Crossref. Both are academic indexes — non-academic web "
    "pages, course handouts, reports, news, and some books may not be found here."
)
_METADATA_LIMITATION_KO = (
    "영어 참고문헌은 Semantic Scholar(학회 논문·arXiv 프리프린트 포함)와 Crossref로 "
    "조회합니다. 둘 다 학술 색인이므로 비학술 웹페이지, 강의 자료, 보고서, 뉴스, "
    "일부 도서는 검색되지 않을 수 있습니다."
)
_KCI_LIMITATION = (
    "Korean titles are checked against KCI (Korea Citation Index), which indexes only "
    "registered Korean scholarly journals. Theses, books, non-registered journals, "
    "conference papers, and web sources may not appear there even if they exist."
)
_KCI_LIMITATION_KO = (
    "한국어 참고문헌은 KCI(한국학술지인용색인)로 조회하며, KCI는 국내 등재(후보) 학술지만 "
    "색인합니다. 학위논문, 단행본, 비등재 학술지, 학회 발표, 웹 자료는 실제로 존재해도 "
    "KCI에 나오지 않을 수 있습니다."
)
_LLM_SEARCH_LIMITATION = (
    "The server does not search the open web. Items not confirmed in "
    "KCI/Semantic Scholar/Crossref are left unconfirmed for the assistant to verify "
    "with its own web search."
)
_LLM_SEARCH_LIMITATION_KO = (
    "서버는 공개 웹을 검색하지 않습니다. KCI·Semantic Scholar·Crossref에서 확정되지 않은 "
    "항목은 미확인으로 두며, 어시스턴트가 자체 웹 검색으로 직접 확인해야 합니다."
)
_MISSING_NOT_INVALID = "A missing match is not proof a citation is invalid."
_MISSING_NOT_INVALID_KO = "일치하는 항목이 없다고 해서 참고문헌이 잘못된 것은 아닙니다."

# A confident title match requires exact normalized-title equality; anything else is
# at best a candidate to verify (shared words in a different order = a DIFFERENT work).
_CANDIDATE_THRESHOLD = 0.72
# Crossref title search can take several seconds per call, so give each lookup a
# generous read-timeout ceiling and run them concurrently (bounded, to stay polite)
# instead of dividing one budget across sequential calls.
_MIN_CALL_MS = 8_000
_MAX_PARALLEL = 4

_NORM_RE = re.compile(r"[^a-z0-9가-힣]+")
_HANGUL_RE = re.compile(r"[가-힣]")
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.I)


def _normalize_title(title: str) -> str:
    return _NORM_RE.sub(" ", title.casefold()).strip()


def _title_similarity(a: str, b: str) -> float:
    """Conservative 0-1 title similarity; 1.0 only on exact normalized equality."""
    na, nb = _normalize_title(a), _normalize_title(b)
    if na and na == nb:
        return 1.0
    token = scorer.score_match(a, b)
    seq = SequenceMatcher(None, na, nb).ratio()
    return min(token, seq)


def _is_specific_title(title: str) -> bool:
    """Distinctive enough that an exact match is meaningful (not "BERT")."""
    norm = _normalize_title(title)
    return len(norm.split()) >= 4 or len(norm) >= 25


def _has_hangul(text: str) -> bool:
    return bool(_HANGUL_RE.search(text))


def _extract_doi(text: str) -> str | None:
    m = _DOI_RE.search(text or "")
    return m.group(0).rstrip(".,);]") if m else None


_URL_RE = re.compile(r"https?://\S+", re.I)
_DOI_TOKEN_RE = re.compile(r"(?i)\b(?:doi|arxiv)\s*:\s*\S+")
_YEAR_PAREN_RE = re.compile(r"\((?:19|20)\d{2}[a-z]?\)\.?\s*")
# Quoted title (IEEE/MLA style: Author, "Title," venue, year).
_QUOTED_RE = re.compile(r"[\"'“”‘’]([^\"'“”‘’]{8,})[\"'“”‘’]")


def _clean_query_title(text: str) -> str:
    """Reduce a full reference string to just the work's title for search.

    Crossref `query.title` is slow (and times out) on long noisy strings like
    "Author, A. (2017). Real Title. Venue. arXiv:...", so we extract the title:
      1. a quoted segment (IEEE/MLA: Author, "Title," …), else
      2. the segment right after an author-year "(YYYY)." prefix (APA), else
      3. the string as-is (bare title), with URLs/DOIs stripped throughout.
    """
    t = _URL_RE.sub(" ", text)
    t = _DOI_TOKEN_RE.sub(" ", t)
    t = _DOI_RE.sub(" ", t)
    qm = _QUOTED_RE.search(t)
    if qm:
        return re.sub(r"\s+", " ", qm.group(1)).strip(" .,")
    m = _YEAR_PAREN_RE.search(t)
    if m:
        t = re.split(r"\.\s", t[m.end():], maxsplit=1)[0]
    t = re.sub(r"\s+", " ", t).strip(" .,")
    return t or text


def _work_detail(w: CrossrefWorkSummary) -> str:
    return ", ".join(
        p for p in [
            w.publisher,
            str(w.publication_year) if w.publication_year else None,
            f"DOI {w.doi}" if w.doi else None,
        ] if p
    )


# When several different Crossref records share the exact title (a famous paper plus
# same-titled reprints/duplicates), the canonical work is almost always the one with
# an overwhelmingly dominant citation count. Only then do we confirm; otherwise the
# title stays ambiguous and the user is asked to verify by author/year/DOI.
_DOMINANT_MIN_CITATIONS = 50
_DOMINANT_RATIO = 10


def _dominant_exact(exacts: list[CrossrefWorkSummary]) -> CrossrefWorkSummary | None:
    ranked = sorted(exacts, key=lambda w: w.cited_by_count or 0, reverse=True)
    top = ranked[0]
    top_count = top.cited_by_count or 0
    second_count = (ranked[1].cited_by_count or 0) if len(ranked) > 1 else 0
    if top_count >= _DOMINANT_MIN_CITATIONS and top_count >= _DOMINANT_RATIO * max(second_count, 1):
        return top
    return None


def _link(w: CrossrefWorkSummary, confidence: Confidence) -> LinkResult | None:
    if not w.url:
        return None
    return LinkResult(title=w.title[:120], url=w.url, source="crossref", confidence=confidence)


# --- Finding builders -------------------------------------------------------

def _f_confirmed(q: CitationQuery, w: CrossrefWorkSummary, ko: bool, *, via_doi: bool) -> Finding:
    detail = _work_detail(w)
    src = "DOI" if via_doi else "Crossref"
    # A confirmed match is an exact title match, so the record title usually equals the
    # query title; only echo it back when it actually differs (avoids printing it twice).
    same = _normalize_title(q.normalized_title) == _normalize_title(w.title)
    matched_ko = "" if same else f": {w.title}"
    matched_en = "" if same else f": {w.title}"
    return Finding(
        id=f"cit-{q.index}",
        category="citation",
        severity="info",
        confidence=Confidence.HIGH,
        title="Crossref 확인됨" if ko else "Confirmed via Crossref",
        message=(
            f"'{q.normalized_title}'을(를) {src} 기준으로 확인했습니다{matched_ko}"
            + (f" ({detail})" if detail else "") + "."
            if ko else
            f"'{q.normalized_title}' confirmed via {src}{matched_en}"
            + (f" ({detail})" if detail else "") + "."
        ),
        evidence=[Evidence(kind="external_match", excerpt=w.title[:160], source="crossref", score=1.0)],
        suggestion=("저자와 발행연도를 최종 확인하세요." if ko else "Confirm author/year."),
    )


def _f_s2_confirmed(q: CitationQuery, p: "semantic_scholar.S2Paper", ko: bool,
                    *, cross_checked: bool) -> Finding:
    detail = ", ".join(part for part in [
        p.venue,
        str(p.year) if p.year else None,
        f"피인용 {p.citation_count:,}회" if ko and p.citation_count else
        (f"{p.citation_count:,} citations" if p.citation_count else None),
        f"DOI {p.doi}" if p.doi else (f"arXiv:{p.arxiv_id}" if p.arxiv_id else None),
    ] if part)
    same = _normalize_title(q.normalized_title) == _normalize_title(p.title)
    matched = "" if same else f": {p.title}"
    if cross_checked:
        confirmed_ko = ("학술 검색 DB(Semantic Scholar)에서 확인하고, DOI를 "
                        "Crossref(공식 DOI 등록처)에서 교차 확인했습니다")
        confirmed_en = "confirmed via Semantic Scholar and cross-checked against Crossref (the DOI registry)"
        title_ko, title_en = "학술 DB 교차 확인됨", "Cross-confirmed (Semantic Scholar + Crossref)"
    else:
        confirmed_ko = "학술 검색 DB(Semantic Scholar)에서 확인했습니다"
        confirmed_en = "confirmed via Semantic Scholar"
        title_ko, title_en = "Semantic Scholar 확인됨", "Confirmed via Semantic Scholar"
    evidence = [Evidence(kind="external_match", excerpt=p.title[:160],
                         source="semantic_scholar", score=1.0)]
    if cross_checked:
        evidence.append(Evidence(kind="external_match", excerpt=(p.doi or "")[:160],
                                 source="crossref", score=1.0))
    return Finding(
        id=f"cit-{q.index}",
        category="citation",
        severity="info",
        confidence=Confidence.HIGH,
        title=title_ko if ko else title_en,
        message=(
            f"'{q.normalized_title}'을(를) {confirmed_ko}{matched}"
            + (f" ({detail})" if detail else "") + "."
            if ko else
            f"'{q.normalized_title}' {confirmed_en}{matched}"
            + (f" ({detail})" if detail else "") + "."),
        evidence=evidence,
        suggestion=("저자와 발행연도를 최종 확인하세요." if ko else "Confirm author/year."),
    )


def _s2_link(p: "semantic_scholar.S2Paper") -> LinkResult | None:
    url = f"https://doi.org/{p.doi}" if p.doi else p.url
    if not url:
        return None
    return LinkResult(title=p.title[:120], url=url, source="semantic_scholar",
                      confidence=Confidence.HIGH)


# Semantic Scholar responds in ~1-3s; keep its budget small so the Crossref
# fallback still fits when S2 is slow or down. The DOI cross-check against
# Crossref's registry is best-effort, so its budget is tighter still.
_S2_CALL_MS = 4_000
_CROSS_CHECK_MS = 3_000


def _s2_lookup(q: CitationQuery, ko: bool, email: str):
    """Try Semantic Scholar's best-title-match first (it indexes NeurIPS/CVPR/arXiv
    papers that Crossref misses). Returns `(result, errors)`: a per-title result
    tuple only on an exact normalized-title match; a None result means 'fall back
    to Crossref'. On an S2 failure (rate limit, timeout) the errors are returned so
    the caller can surface them — a rate-limited S2 must show up as a partial
    failure, not silently downgrade a verifiable paper to "unconfirmed".

    Authority: when the S2 record carries a DOI, cross-check it against Crossref —
    the official DOI registry — so the confirmation rests on the registry, not just
    the aggregator. The cross-check is best-effort: if Crossref is slow or down the
    item is still reported as S2-confirmed (never degraded)."""
    resp = semantic_scholar.match_title(q.normalized_title, deadline_ms=_S2_CALL_MS)
    if resp.status is Status.EXTERNAL_ERROR:
        return None, list(resp.errors)
    if resp.paper is None:
        return None, []
    p = resp.paper
    if (_title_similarity(q.normalized_title, p.title) >= 1.0
            and _is_specific_title(q.normalized_title)):
        cross_checked = False
        if p.doi:
            doi_resp = crossref.fetch_by_doi(p.doi, mailto=email or None,
                                             deadline_ms=_CROSS_CHECK_MS)
            cross_checked = doi_resp.status is Status.OK and bool(doi_resp.works)
        return ((_f_s2_confirmed(q, p, ko, cross_checked=cross_checked),
                 _s2_link(p), [], "s2_confirmed"), [])
    return None, []


def _f_doi_not_found(q: CitationQuery, doi: str, ko: bool) -> Finding:
    return Finding(
        id=f"cit-{q.index}",
        category="citation",
        severity="low",
        confidence=Confidence.LOW,
        title="DOI 미확인" if ko else "DOI not found",
        message=(
            f"표기된 DOI({doi})가 Crossref에 등록되어 있지 않습니다. DOI 표기 오류이거나 "
            "추가 확인이 필요합니다."
            if ko else
            f"The cited DOI ({doi}) is not registered in Crossref. It may be a typo or "
            "needs verification."
        ),
        evidence=[Evidence(kind="citation", excerpt=doi[:160])],
        suggestion=("DOI 표기를 원문과 다시 대조하세요." if ko else "Re-check the DOI against the source."),
    )


def _f_crossref_soft(q: CitationQuery, best: CrossrefWorkSummary | None, sim: float, ko: bool) -> Finding:
    if best is not None and sim >= _CANDIDATE_THRESHOLD:
        detail = _work_detail(best)
        return Finding(
            id=f"cit-{q.index}",
            category="citation",
            severity="low",
            confidence=Confidence.LOW,
            title="유사 후보(확인 필요)" if ko else "Possible candidate (verify)",
            message=(
                f"'{q.normalized_title}'의 정확한 Crossref 일치 항목이 없습니다. 가장 가까운 "
                f"기록은 '{best.title}'" + (f" ({detail})" if detail else "")
                + f"이지만 제목이 다릅니다(유사도 {sim:.2f}). 다른 자료일 수 있습니다."
                if ko else
                f"No exact Crossref match for '{q.normalized_title}'. Closest record is "
                f"'{best.title}'" + (f" ({detail})" if detail else "")
                + f", but the title differs (similarity {sim:.2f})."),
            evidence=[Evidence(kind="external_match", excerpt=best.title[:160], source="crossref",
                               score=round(sim, 3))],
            suggestion=("출처로 인정하기 전에 저자, 발행연도, DOI를 확인하세요." if ko
                        else "Verify author/year/DOI before treating this as the source."),
        )
    return Finding(
        id=f"cit-{q.index}",
        category="citation",
        severity="low",
        confidence=Confidence.LOW,
        title="확실한 Crossref 일치 없음" if ko else "No confident Crossref match",
        message=(
            f"'{q.normalized_title}'에 대한 확실한 Crossref 일치 항목이 없습니다. 이것이 "
            "참고문헌이 잘못되었다는 뜻은 아니며, 여기에 색인되지 않은 학회 논문, 프리프린트, "
            "도서, 웹 자료일 수 있습니다."
            if ko else
            f"No confident Crossref match for '{q.normalized_title}'. This does not mean "
            "the citation is invalid — it may be a conference paper, preprint, book, or "
            "web source not indexed here."),
        evidence=[Evidence(kind="citation", excerpt=q.normalized_title[:160])],
        suggestion=("출판사 페이지, DOI 또는 공개 웹 검색으로 확인하세요." if ko
                    else "Verify via the publisher page, DOI, or public web search."),
    )


def _f_ambiguous_title(q: CitationQuery, count: int, ko: bool) -> Finding:
    return Finding(
        id=f"cit-{q.index}",
        category="citation",
        severity="low",
        confidence=Confidence.LOW,
        title="제목 중복 — 확인 필요" if ko else "Ambiguous title (verify)",
        message=(
            f"'{q.normalized_title}'과(와) 제목이 동일한 Crossref 기록이 {count}건 있어 "
            "어느 것이 맞는지 제목만으로는 확정할 수 없습니다. 저자와 발행연도, DOI로 직접 "
            "확인하세요."
            if ko else
            f"{count} different Crossref records share the exact title "
            f"'{q.normalized_title}', so the title alone cannot identify the right one. "
            "Verify with author, year, and DOI."),
        evidence=[Evidence(kind="citation", excerpt=q.normalized_title[:160])],
        suggestion=("저자, 발행연도, DOI로 정확한 문헌을 확인하세요." if ko
                    else "Confirm the exact work by author, year, and DOI."),
    )


def _f_unverifiable(q: CitationQuery, ko: bool) -> Finding:
    return Finding(
        id=f"cit-{q.index}",
        category="citation",
        severity="low",
        confidence=Confidence.LOW,
        title="확인 불가" if ko else "Could not verify",
        message=(f"조회에 실패해 확인하지 못했습니다: {q.normalized_title}" if ko
                 else f"Lookup failed for: {q.normalized_title}"),
        evidence=[Evidence(kind="citation", excerpt=q.normalized_title[:160])],
    )


def _f_korean_unconfirmed(q: CitationQuery, ko: bool) -> Finding:
    return Finding(
        id=f"cit-{q.index}",
        category="citation",
        severity="low",
        confidence=Confidence.LOW,
        title="미확인" if ko else "Unconfirmed",
        message=(
            f"'{q.normalized_title}'은(는) KCI(한국학술지인용색인)에서 일치하는 항목을 찾지 "
            "못했습니다. 존재하지 않는다는 뜻은 아니며, KCI가 색인하지 않는 학위논문·단행본·"
            "비등재지일 수 있습니다. 웹 검색이나 RISS·DBpia에서 추가 확인이 필요합니다."
            if ko else
            f"'{q.normalized_title}' had no match in KCI (Korea Citation Index). This is "
            "not proof it does not exist — it may be a thesis, book, or non-indexed "
            "journal. Verify via web search or RISS/DBpia."),
        evidence=[Evidence(kind="citation", excerpt=q.normalized_title[:160])],
        suggestion=("웹 검색이나 RISS·DBpia에서 실제 존재를 확인하세요." if ko
                    else "Confirm existence via web search or RISS/DBpia."),
    )


def _f_kci_confirmed(q: CitationQuery, a: "kci.KciArticle", ko: bool) -> Finding:
    detail = ", ".join(p for p in [a.journal, str(a.publication_year) if a.publication_year else None,
                                   f"DOI {a.doi}" if a.doi else None] if p)
    # Confirmed = exact title match, so a.title usually equals the query; only echo it
    # back when it differs so the message doesn't print the same title twice.
    same = _normalize_title(q.normalized_title) == _normalize_title(a.title)
    matched = "" if same else f": {a.title}"
    return Finding(
        id=f"cit-{q.index}",
        category="citation",
        severity="info",
        confidence=Confidence.HIGH,
        title="KCI 확인됨" if ko else "Confirmed via KCI",
        message=(
            f"'{q.normalized_title}'을(를) KCI(한국학술지인용색인)에서 확인했습니다{matched}"
            + (f" ({detail})" if detail else "") + "."
            if ko else
            f"'{q.normalized_title}' confirmed via KCI (Korea Citation Index){matched}"
            + (f" ({detail})" if detail else "") + "."),
        evidence=[Evidence(kind="external_match", excerpt=a.title[:160], source="kci", score=1.0)],
        suggestion=("저자와 발행연도를 최종 확인하세요." if ko else "Confirm author/year."),
    )


def _f_kci_candidate(q: CitationQuery, a: "kci.KciArticle", sim: float, ko: bool) -> Finding:
    detail = ", ".join(p for p in [a.journal, str(a.publication_year) if a.publication_year else None] if p)
    return Finding(
        id=f"cit-{q.index}",
        category="citation",
        severity="low",
        confidence=Confidence.LOW,
        title="KCI 유사 후보(확인 필요)" if ko else "Possible KCI candidate (verify)",
        message=(
            f"'{q.normalized_title}'의 정확한 KCI 일치 항목은 없지만, 가장 가까운 KCI 기록은 "
            f"'{a.title}'" + (f" ({detail})" if detail else "") + f"입니다(유사도 {sim:.2f}). "
            "저자, 발행연도로 확인하세요."
            if ko else
            f"No exact KCI match for '{q.normalized_title}'. Closest KCI record is '{a.title}'"
            + (f" ({detail})" if detail else "") + f" (similarity {sim:.2f}); verify author/year."),
        evidence=[Evidence(kind="external_match", excerpt=a.title[:160], source="kci", score=round(sim, 3))],
        suggestion=("KCI에서 저자, 발행연도로 정확한 문헌을 확인하세요." if ko
                    else "Confirm the exact record on KCI by author/year."),
    )


def _kci_link(a: "kci.KciArticle") -> LinkResult | None:
    if not a.url:
        return None
    return LinkResult(title=a.title[:120], url=a.url, source="kci", confidence=Confidence.HIGH)


def _kci_sim(query: str, a: "kci.KciArticle") -> float:
    return max(_title_similarity(query, a.title),
              _title_similarity(query, a.title_english or ""))


def _kci_lookup(q: CitationQuery, ko: bool, deadline_ms: int):
    """Look up a Korean title in KCI. Returns a per-title result tuple on a KCI match,
    or None to signal 'no confident KCI match' (no key / no result / error)."""
    api_key = (config.get_kci_api_key() or "").strip()
    if not api_key:
        return None
    resp = kci.search_by_title(q.normalized_title, api_key, deadline_ms=deadline_ms)
    if resp.status is Status.EXTERNAL_ERROR or not resp.articles:
        return None  # no confident KCI match; the LLM verifies via its own web search
    ranked = sorted(((_kci_sim(q.normalized_title, a), a) for a in resp.articles),
                    key=lambda pair: pair[0], reverse=True)
    best_sim, best = ranked[0]
    exact_count = sum(1 for s, _ in ranked if s >= 1.0)
    if best_sim >= 1.0 and _is_specific_title(q.normalized_title) and exact_count == 1:
        return _f_kci_confirmed(q, best, ko), _kci_link(best), [], "kci_confirmed"
    if best_sim >= _CANDIDATE_THRESHOLD:
        return _f_kci_candidate(q, best, best_sim, ko), _kci_link(best), [], "candidate"
    return None  # no useful KCI match


# --- Per-title verification -------------------------------------------------

def _verify_one(q: CitationQuery, email: str, max_results: int, ko: bool, deadline_ms: int):
    """Return (finding, link|None, partial_errors, outcome).

    Language routing (DOI does not override it): Korean -> KCI, English -> Crossref.
    Anything not confirmed here is left "미확인" for the host LLM to verify with its own
    web search; the pipeline never calls a web-search API itself.
    """
    mailto = email or None

    # DOI comes from the raw reference; the search query uses just the extracted title
    # so Crossref gets a clean, fast query (and title similarity is meaningful).
    doi = _extract_doi(q.original_title) or _extract_doi(q.normalized_title)
    q.normalized_title = _clean_query_title(q.normalized_title)

    if _has_hangul(q.normalized_title):
        # Korean → KCI only (DOI-independent); no confident match → 미확인 (LLM verifies).
        result = _kci_lookup(q, ko, deadline_ms)
        if result is not None:
            return result
        return _f_korean_unconfirmed(q, ko), None, [], "unconfirmed"

    # English → Crossref DOI lookup if the entry carries one (authoritative), else
    # Semantic Scholar best-title-match first (covers NeurIPS/CVPR/arXiv papers that
    # Crossref indexes poorly), then Crossref title search as the fallback.
    if doi:
        resp = crossref.fetch_by_doi(doi, mailto=mailto, deadline_ms=deadline_ms)
        if resp.status is Status.EXTERNAL_ERROR:
            return _f_unverifiable(q, ko), None, list(resp.errors), "error"
        if resp.works:
            w = resp.works[0]
            return _f_confirmed(q, w, ko, via_doi=True), _link(w, Confidence.HIGH), [], "crossref_confirmed"
        return _f_doi_not_found(q, doi, ko), None, [], "unconfirmed"

    # S2 errors ride along to the non-confirmed outcomes below: when S2 was down or
    # rate-limited, "unconfirmed" may just mean "could not look it up", and the
    # summary must say so instead of presenting a silently degraded result.
    s2_result, s2_errors = _s2_lookup(q, ko, email)
    if s2_result is not None:
        return s2_result

    resp = crossref.search_work(
        crossref.CrossrefSearchRequest(
            query_title=q.normalized_title, mailto=mailto,
            rows=max(max_results, 5), deadline_ms=deadline_ms,
        )
    )
    if resp.status is Status.EXTERNAL_ERROR:
        return _f_unverifiable(q, ko), None, s2_errors + list(resp.errors), "error"

    ranked = sorted(
        ((_title_similarity(q.normalized_title, w.title), w) for w in resp.works),
        key=lambda pair: pair[0], reverse=True,
    )
    best_sim, best = ranked[0] if ranked else (0.0, None)
    exact_count = sum(1 for s, _ in ranked if s >= 1.0)

    if best is not None and best_sim >= 1.0 and _is_specific_title(q.normalized_title):
        if exact_count >= 2:
            # Several different works share this exact title (e.g. a well-known paper
            # plus same-titled duplicates/predatory entries). Confirm only when one
            # record's citation count is overwhelmingly dominant (the canonical work);
            # otherwise the title alone cannot pick the right one.
            dominant = _dominant_exact([w for s, w in ranked if s >= 1.0])
            if dominant is not None:
                return (_f_confirmed(q, dominant, ko, via_doi=False),
                        _link(dominant, Confidence.HIGH), [], "crossref_confirmed")
            return _f_ambiguous_title(q, exact_count, ko), None, s2_errors, "unconfirmed"
        return _f_confirmed(q, best, ko, via_doi=False), _link(best, Confidence.HIGH), [], "crossref_confirmed"

    link = _link(best, Confidence.LOW) if best is not None else None
    return _f_crossref_soft(q, best, best_sim, ko), link, s2_errors, "candidate" if link else "unconfirmed"


def run(args: dict, context: RequestContext) -> PipelineResult:
    raw_titles = args.get("citation_titles") or []
    # Citation titles are usually in the cited work's language; follow the explicit
    # hint, Korean-first by default (never detect from the titles themselves).
    rlang = "en" if context.language_hint == "en" else "ko"
    ko = rlang == "ko"

    if not raw_titles:
        return PipelineResult(
            status=Status.NO_FINDINGS,
            summary=("참고문헌 항목이 없어 참고문헌 검증을 수행하지 않았습니다." if ko
                     else "No citation titles were provided, so citation verification was skipped."),
            next_actions=(["검증할 참고문헌 제목을 제공하세요."] if ko
                          else ["Provide one or more citation titles to verify."]),
            response_language=rlang,
        )

    titles_or_err = normalize_titles(raw_titles)
    if isinstance(titles_or_err, ModuleError):
        return PipelineResult(
            status=Status.INVALID_INPUT,
            summary=("참고문헌 제목이 올바르지 않습니다." if ko else "Invalid citation titles."),
            next_actions=(["비어 있지 않은 참고문헌 제목을 하나 이상 제공하세요."] if ko
                          else ["Provide one or more non-empty citation titles."]),
            partial_failures=[titles_or_err],
            response_language=rlang,
        )

    options = args.get("options") or {}
    max_results = int(options.get("max_results", 3))
    # Works without an email; an email only upgrades Crossref to the polite pool.
    email = (args.get("user_email") or config.get_user_email() or "").strip()
    if email and validate_email_for_mailto(email) is not None:
        email = ""

    findings: list[Finding] = []
    links: list[LinkResult] = []
    partial: list[ModuleError] = []
    confirmed = 0
    candidates = 0

    # Run lookups concurrently: each KCI/Crossref call can take several seconds, so
    # sequential calls would blow the budget. Each call gets a generous read-timeout
    # ceiling; bounded workers keep us polite to the free APIs.
    per_call_ms = max(_MIN_CALL_MS, context.deadline_ms)
    workers = min(_MAX_PARALLEL, len(titles_or_err))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(
            lambda q: _verify_one(q, email, max_results, ko, per_call_ms),
            titles_or_err,
        ))

    for finding, link, perr, outcome in results:
        findings.append(finding)
        if link:
            links.append(link)
        partial.extend(perr)
        if outcome in ("crossref_confirmed", "kci_confirmed", "s2_confirmed"):
            confirmed += 1
        elif outcome == "candidate":
            candidates += 1

    total = len(titles_or_err)
    unconfirmed = total - confirmed - candidates
    status = Status.PARTIAL if partial else Status.OK

    if ko:
        parts = [f"참고문헌 {total}건을 확인했습니다."]
        if confirmed:
            parts.append(f"{confirmed}건은 학술 DB(한국어는 KCI, 영어는 Semantic Scholar·Crossref)에서 확인했습니다.")
        if candidates:
            parts.append(f"{candidates}건은 제목이 유사한 후보만 찾았을 뿐 존재가 확정된 것은 아닙니다.")
        if unconfirmed:
            parts.append(f"{unconfirmed}건은 미확인입니다.")
        if partial:
            parts.append("외부 조회 지연 등으로 일부 결과를 얻지 못해 ‘검증 완료’가 아니라 ‘미확인/부분 결과’로 보아야 합니다.")
        summary = " ".join(parts)
        limitations = [_METADATA_LIMITATION_KO, _KCI_LIMITATION_KO,
                       _LLM_SEARCH_LIMITATION_KO, _MISSING_NOT_INVALID_KO]
        next_actions = [
            "[어시스턴트 수행] 웹 검색 도구가 있으면 학술 DB에서 확정되지 않은 참고문헌을 "
            "직접 검색해 확인하세요(미확인·유사 후보 우선). 웹 검색 도구가 없으면 해당 항목은 "
            "검증하지 못했다고 결과에 명시하세요.",
            "[사용자 안내] 미확인·유사 후보 항목은 웹 검색이나 KCI·RISS·DBpia·출판사 페이지에서 "
            "직접 확인하세요.",
            "[사용자 안내] 인용 표기법은 get_citation_format_guidance 가이드로 점검하세요.",
        ]
    else:
        parts = [f"Checked {total} citation(s)."]
        if confirmed:
            parts.append(f"{confirmed} confirmed in an academic index (KCI for Korean, Semantic Scholar/Crossref for English).")
        if candidates:
            parts.append(f"{candidates} had only a similar-title candidate (existence not confirmed).")
        if unconfirmed:
            parts.append(f"{unconfirmed} unconfirmed.")
        if partial:
            parts.append("Some lookups failed, so treat this as partial, not verified.")
        summary = " ".join(parts)
        limitations = [_METADATA_LIMITATION, _KCI_LIMITATION,
                       _LLM_SEARCH_LIMITATION, _MISSING_NOT_INVALID]
        next_actions = [
            "[assistant] If you have a web search tool, verify the citations the academic "
            "indexes could not confirm (unconfirmed/candidate first). If you have no web "
            "search tool, state explicitly that those items remain unverified.",
            "[relay to user] Manually confirm unconfirmed or candidate citations via web "
            "search or KCI/RISS/DBpia/publisher page.",
            "[relay to user] Check citation formatting with the get_citation_format_guidance tool.",
        ]

    # Attach CITATION_CHECK guidance so the host LLM can follow up on the automated
    # results — especially unconfirmed / web-signal-only items — by verifying them
    # against authoritative sources (best-effort; the automated findings stand alone).
    guidance_doc = load_guidance("CITATION_CHECK")
    sections = []
    expected_format = ""
    guidance_version = "0"
    if not isinstance(guidance_doc, ModuleError):
        sections = guidance_doc.sections
        expected_format = guidance_doc.expected_llm_output_format
        guidance_version = guidance_doc.version

    return GuidanceResult(
        status=status,
        summary=summary,
        findings=findings,
        metrics={"checked": total, "confident_matches": confirmed,
                 "candidates": candidates, "unconfirmed": unconfirmed},
        limitations=limitations,
        next_actions=next_actions,
        links=links,
        partial_failures=partial,
        response_language=rlang,
        guidance_id="CITATION_CHECK",
        guidance_version=guidance_version,
        sections=sections,
        expected_llm_output_format=expected_format,
    )


__all__ = ["run"]
