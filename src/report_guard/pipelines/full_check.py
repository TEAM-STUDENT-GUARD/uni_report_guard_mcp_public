"""pipelines/full_check — composes the six feature pipelines into one summary.

Calls only the public `run(args, context)` interface of each feature pipeline (never
their internals). Counts runs first (cheap/deterministic); citation runs only when
`citation_titles` is supplied, otherwise it is recorded in `skipped_pipelines` with
a limitation (inputs are never invented). Any sub-pipeline failure is collected as a
partial failure rather than crashing the whole tool. The composed result is
compressed elsewhere to stay under 24k.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from .. import i18n
from ..errors import ErrorCode, module_error
from ..references import find_reference_section, split_reference_entries
from ..schemas import (
    Finding,
    FullCheckResult,
    LinkResult,
    PipelineResult,
    RequestContext,
    Status,
)
from . import (
    citation,
    citation_format,
    counts,
    plagiarism,
    required_fields,
    spellcheck,
    writing_structure,
)

# Order matters: deterministic/cheap first.
_LOCAL_FIRST = ("counts", "writing_structure", "required_fields", "citation_format")
_EXTERNAL = ("spellcheck", "plagiarism")

_RUNNERS: dict[str, Callable[[dict, RequestContext], PipelineResult]] = {
    "counts": counts.run,
    "spellcheck": spellcheck.run,
    "plagiarism": plagiarism.run,
    "writing_structure": writing_structure.run,
    "required_fields": required_fields.run,
    "citation_format": citation_format.run,
    "citation": citation.run,
}


def _extract_references(document_text: str) -> list[str]:
    """Pull reference-list entries from the document's bibliography section so the
    full check can verify citations even when citation_titles is not passed in.

    Robust to hosts that collapse the document's newlines (the reference heading then
    sits inline rather than on its own line); see `references.find_reference_section`.
    """
    section = find_reference_section(document_text or "")
    if section is None:
        return []
    _, heading_end = section
    return split_reference_entries((document_text or "")[heading_end:])[:30]  # bounded


def _safe_run(name: str, args: dict, context: RequestContext) -> PipelineResult:
    """Run a sub-pipeline, converting any exception into an internal_error result."""
    try:
        return _RUNNERS[name](args, context)
    except Exception:  # noqa: BLE001 — isolate; never leak raw exception text
        return PipelineResult(
            status=Status.INTERNAL_ERROR,
            summary=f"The {name} check failed unexpectedly.",
            partial_failures=[
                module_error(
                    ErrorCode.INTERNAL_ERROR,
                    f"The {name} check could not be completed.",
                    module=f"pipelines/{name}",
                    pipeline=name,
                )
            ],
        )


def _sub_args(name: str, args: dict) -> dict:
    """Project the full-check input down to each sub-pipeline's accepted fields."""
    options = args.get("options") or {}
    if name == "counts":
        return {
            "document_text": args.get("document_text", ""),
            "options": {"include_spaces": options.get("include_spaces", True)},
        }
    if name == "spellcheck":
        sub_opts = {}
        if "max_findings_per_pipeline" in options:
            sub_opts["max_findings"] = options["max_findings_per_pipeline"]
        return {"document_text": args.get("document_text", ""), "options": sub_opts}
    if name == "plagiarism":
        keys = ("sentence_chunk_size", "similarity_threshold", "max_queries", "max_results")
        return {
            "document_text": args.get("document_text", ""),
            "options": {k: options[k] for k in keys if k in options},
        }
    if name == "citation":
        sub_opts = {}
        if "max_results" in options:
            sub_opts["max_results"] = options["max_results"]
        out: dict = {"citation_titles": args.get("citation_titles") or [], "options": sub_opts}
        if args.get("user_email"):
            out["user_email"] = args["user_email"]
        return out
    return {}  # guidance tools take empty input


# Per-check breakdown so run_full_report_check shows each item's result clearly,
# not just an aggregated finding count. Rendered into the summary, which
# result_formatter always preserves (findings can be shed under the size budget).
_CHECK_LABELS = {
    "counts": ("분량", "Length"),
    "spellcheck": ("맞춤법", "Spelling"),
    "citation": ("참고문헌", "Citations"),
    "plagiarism": ("표절 위험", "Plagiarism risk"),
    "writing_structure": ("글 구조", "Structure"),
    "required_fields": ("필수 항목", "Required fields"),
    "citation_format": ("표기법", "Citation format"),
}
_DISPLAY_ORDER = ("counts", "spellcheck", "citation", "plagiarism",
                  "writing_structure", "required_fields", "citation_format")
_GUIDANCE_CHECKS = {"writing_structure", "required_fields", "citation_format"}


def _marker(status: Status) -> str:
    if status in (Status.OK, Status.NO_FINDINGS):
        return "✅"
    return "⚠️"  # partial / external / internal / invalid


def _check_marker(name: str, res: PipelineResult) -> str:
    if name == "citation":
        # ✅ only when every title was actually confirmed; unconfirmed/candidate
        # items need follow-up, so a green check would misread as "all verified".
        m = res.metrics or {}
        checked = m.get("checked", 0)
        if res.status in (Status.OK, Status.PARTIAL) and checked:
            return "✅" if m.get("confident_matches", 0) == checked else "⚠️"
    return _marker(res.status)


def _char_basis(m: dict, ko: bool) -> str:
    """Space basis suffix for character counts, e.g. "(공백 포함)"; the basis must
    accompany every rendered count so two tools' numbers stay comparable."""
    spaces = m.get("character_count_includes_spaces")
    if spaces is None:
        return ""
    if ko:
        return "(공백 포함)" if spaces else "(공백 제외)"
    return "(incl. spaces)" if spaces else "(excl. spaces)"


def _check_detail(name: str, res: PipelineResult, ko: bool) -> str:
    m = res.metrics or {}
    if name == "counts":
        basis = _char_basis(m, ko)
        return (f"{m.get('character_count', '?')}자{basis} / {m.get('word_count', '?')}단어 / "
                f"{m.get('sentence_count', '?')}문장 / {m.get('paragraph_count', '?')}문단" if ko else
                f"{m.get('character_count', '?')} chars {basis} / {m.get('word_count', '?')} words / "
                f"{m.get('sentence_count', '?')} sentences / {m.get('paragraph_count', '?')} paragraphs")
    if name == "spellcheck":
        if res.status is Status.EXTERNAL_ERROR:
            return "평가 불가" if ko else "unavailable"
        n = m.get("issue_count", 0)
        if not n:
            return "점검 항목 없음" if ko else "no items"
        return (f"점검 {n}건" + (" (부분)" if res.status is Status.PARTIAL else "") if ko
                else f"{n} item(s)" + (" (partial)" if res.status is Status.PARTIAL else ""))
    if name == "plagiarism":
        if res.status is Status.EXTERNAL_ERROR:
            return "평가 불가 (검색 설정/서비스 상태)" if ko else "not assessed (config/service)"
        n = m.get("suspect_match_count", 0)
        if not n:
            return "유사 항목 없음" if ko else "no matches"
        return f"유사 {n}건" if ko else f"{n} similar"
    if name == "citation":
        return (f"{m.get('checked', '?')}건 중 {m.get('confident_matches', 0)}건 확인, "
                f"{m.get('candidates', 0)} 유사 후보, {m.get('unconfirmed', 0)} 미확인" if ko else
                f"{m.get('confident_matches', 0)}/{m.get('checked', '?')} confirmed, "
                f"{m.get('candidates', 0)} candidate, {m.get('unconfirmed', 0)} unconfirmed")
    if name in _GUIDANCE_CHECKS:
        return "가이드 제공" if ko else "guidance provided"
    return ""


# Cap findings shown per tool in the detailed report to protect the size budget.
_MAX_DETAIL_FINDINGS = 25


def _detailed_report(sub_results: dict, skipped: list[str], ko: bool) -> str:
    """Render each tool's real result in its own section, as if it were run
    individually: counts/spelling/citation/plagiarism findings and the guidance
    rubrics. Kept in the summary so it survives response-size compression."""
    blocks: list[str] = []
    for name in _DISPLAY_ORDER:
        label = _CHECK_LABELS[name][0 if ko else 1]
        if name in sub_results:
            res = sub_results[name]
            head = f"**{_check_marker(name, res)} {label}** — {_check_detail(name, res, ko)}"
            body: list[str] = []
            if name in _GUIDANCE_CHECKS:
                for s in getattr(res, "sections", None) or []:
                    body.append(f"- {s.title}")
                    for item in (s.checklist or [])[:5]:
                        body.append(f"  - {item}")
            elif name != "counts":
                shown = res.findings[:_MAX_DETAIL_FINDINGS]
                for f in shown:
                    if name == "spellcheck":
                        body.append(f"- {f.message} → {f.suggestion}")
                    else:
                        body.append(f"- {f.title}: {f.message}")
                extra = len(res.findings) - len(shown)
                if extra > 0:
                    body.append(f"- … 외 {extra}건" if ko else f"- … and {extra} more")
                for lk in (res.links or [])[:5]:
                    body.append(f"- 🔗 [{lk.title}]({lk.url})")
            blocks.append("\n".join([head] + body))
        elif name in skipped:
            if name == "citation":
                detail = "건너뜀 (참고문헌 제목 없음)" if ko else "skipped (no titles)"
            else:
                detail = "건너뜀" if ko else "skipped"
            blocks.append(f"**⏭️ {label}** — {detail}")
    return "\n\n".join(blocks)


def run(args: dict, context: RequestContext) -> FullCheckResult:
    document_text = args.get("document_text", "")
    rlang = i18n.resolve_response_language(context.language_hint, document_text)
    ko = rlang == "ko"
    if not document_text:
        return FullCheckResult(
            status=Status.INVALID_INPUT,
            summary=("전체 리포트 검사에는 문서가 필요합니다." if ko
                     else "A document is required for a full report check."),
            metrics={
                "completed_pipelines": [],
                "skipped_pipelines": [],
                "timed_out_pipelines": [],
                "total_findings": 0,
            },
            next_actions=(["document_text를 제공하세요."] if ko else ["Provide document_text."]),
            response_language=rlang,
        )

    sub_results: dict[str, PipelineResult] = {}
    completed: list[str] = []
    skipped: list[str] = []
    timed_out: list[str] = []
    partial_failures = []

    run_order = list(_LOCAL_FIRST) + list(_EXTERNAL)

    # Citations: use explicit titles, else auto-extract the document's reference list
    # so the full check actually verifies citations instead of skipping them.
    citation_titles = args.get("citation_titles") or _extract_references(document_text)
    if citation_titles:
        args = {**args, "citation_titles": citation_titles}
    has_titles = bool(citation_titles)
    if has_titles:
        run_order.append("citation")
    else:
        skipped.append("citation")

    # Local pipelines are cheap and deterministic — run them inline. The external
    # ones (spellcheck / plagiarism / citation) each spend seconds on network I/O,
    # so run them concurrently: total time ≈ the slowest check, not the sum.
    local_names = [n for n in run_order if n in _LOCAL_FIRST]
    external_names = [n for n in run_order if n not in _LOCAL_FIRST]
    for name in local_names:
        sub_results[name] = _safe_run(name, _sub_args(name, args), context)
    if external_names:
        with ThreadPoolExecutor(max_workers=len(external_names)) as ex:
            futures = {
                n: ex.submit(_safe_run, n, _sub_args(n, args), context)
                for n in external_names
            }
            for n, fut in futures.items():
                sub_results[n] = fut.result()

    for name in run_order:
        result = sub_results[name]
        if result.status in (Status.EXTERNAL_ERROR, Status.INTERNAL_ERROR):
            partial_failures.extend(result.partial_failures or [])
            if any(
                getattr(e.code, "name", "") in ("PROVIDER_TIMEOUT",)
                for e in (result.partial_failures or [])
            ):
                timed_out.append(name)
            else:
                completed.append(name)  # ran, but degraded — still counted as attempted
        else:
            completed.append(name)
            if result.status is Status.PARTIAL:
                partial_failures.extend(result.partial_failures or [])

    # Aggregate top findings + links across pipelines.
    all_findings: list[Finding] = []
    all_links: list[LinkResult] = []
    all_limitations: list[str] = []
    for name, res in sub_results.items():
        all_findings.extend(res.findings)
        all_links.extend(res.links)
        all_limitations.extend(res.limitations)

    if not has_titles:
        all_limitations.append(
            "참고문헌 항목이 없어 참고문헌 검증을 건너뛰었습니다." if ko
            else "Citation check was skipped because no citation_titles were provided."
        )

    # De-duplicate limitations preserving order.
    seen: set[str] = set()
    limitations = [x for x in all_limitations if not (x in seen or seen.add(x))]

    any_degraded = bool(partial_failures) or bool(timed_out)
    all_invalid = all(
        r.status is Status.INVALID_INPUT for r in sub_results.values()
    ) and bool(sub_results)
    if all_invalid:
        status = Status.INVALID_INPUT
    elif any_degraded:
        status = Status.PARTIAL
    else:
        status = Status.OK

    counts_metrics = (sub_results.get("counts") and sub_results["counts"].metrics) or {}
    if ko:
        summary_bits = []
        if counts_metrics:
            summary_bits.append(
                f"{counts_metrics.get('character_count', '?')}자"
                f"{_char_basis(counts_metrics, ko=True)} / "
                f"{counts_metrics.get('word_count', '?')}단어"
            )
        summary_bits.append(f"발견 {len(all_findings)}건")
        if skipped:
            summary_bits.append(f"건너뜀: {', '.join(skipped)}")
        if timed_out:
            summary_bits.append(f"시간 초과: {', '.join(timed_out)}")
        summary = "전체 리포트 검토 — " + "; ".join(summary_bits) + "."
        if status is Status.PARTIAL:
            summary += (
                " 일부 항목은 부분 결과 또는 평가 불가 상태이므로, 전체 검사 성공이나 "
                "표절 위험 없음으로 해석하면 안 됩니다."
            )
        next_actions = [
            "우선순위에 따라 발견 사항을 검토하고 솔직하게 개선하세요.",
            "글 구조 및 필수 항목 가이드를 문서에 적용해 점검하세요.",
        ]
    else:
        summary_bits = []
        if counts_metrics:
            summary_bits.append(
                f"{counts_metrics.get('character_count', '?')} chars "
                f"{_char_basis(counts_metrics, ko=False)} / "
                f"{counts_metrics.get('word_count', '?')} words"
            )
        summary_bits.append(f"{len(all_findings)} finding(s)")
        if skipped:
            summary_bits.append(f"skipped: {', '.join(skipped)}")
        if timed_out:
            summary_bits.append(f"timed out: {', '.join(timed_out)}")
        summary = "Full report check — " + "; ".join(summary_bits) + "."
        next_actions = [
            "Review findings by priority and apply honest improvements.",
            "Apply the writing-structure and required-fields guidance to your document.",
        ]

    # Append a detailed per-tool report so the full check reads like running each
    # tool individually. It lives in the summary, which result_formatter always
    # preserves (the aggregated flat findings are not re-rendered for full checks).
    detail = _detailed_report(sub_results, skipped, ko)
    if detail:
        header = "항목별 상세 결과" if ko else "Per-check details"
        summary = summary + "\n\n" + header + "\n\n" + detail

    return FullCheckResult(
        status=status,
        summary=summary,
        findings=all_findings,
        metrics={
            "completed_pipelines": completed,
            "skipped_pipelines": skipped,
            "timed_out_pipelines": timed_out,
            "total_findings": len(all_findings),
        },
        limitations=limitations,
        next_actions=next_actions,
        links=all_links,
        partial_failures=partial_failures,
        sub_results=sub_results,
        response_language=rlang,
    )


__all__ = ["run"]
