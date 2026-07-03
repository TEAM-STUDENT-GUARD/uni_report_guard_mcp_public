"""Markdown rendering, response compression, and 24k size enforcement.

`result_formatter` must not import any pipeline. It takes a normalized
`PipelineResult` and produces an MCP-compatible response, shedding low-priority
detail until the serialized response fits the configured budget while always
preserving summary, status, limitations, and next_actions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from . import config
from . import i18n
from .schemas import (
    CONFIDENCE_ORDER,
    SEVERITY_ORDER,
    Finding,
    FullCheckResult,
    PipelineResult,
    Status,
)

# Reserve headroom under the hard ceiling for MCP envelope overhead.
_ENVELOPE_HEADROOM = 1_500

_OMITTED_NOTE = {
    "ko": "응답 크기 제한으로 일부 세부 내용은 생략되었습니다.",
    "en": "Some details were omitted to fit the response-size limit.",
}

# guidance_ids whose result is a rubric to apply, not a document inspection.
# CITATION_CHECK and PLAGIARISM_CHECK carry guidance too, but they are REAL checks
# (Crossref/Naver) with the rubric merely attached for follow-up, so they are excluded.
_GUIDANCE_ONLY_IDS = {"GOOD_WRITING", "TO_HAVE", "CITATION_FORMAT"}


@dataclass
class McpToolResponse:
    content: list[dict]
    structuredContent: dict | None
    isError: bool


def _budget() -> int:
    return int(config.get_limit("MAX_TOOL_RESPONSE_CHARS"))


def _finding_priority(f: Finding) -> tuple[int, int]:
    """Higher = keep longer. Sort key for shedding lowest first."""
    return (SEVERITY_ORDER.get(f.severity, 0), CONFIDENCE_ORDER.get(f.confidence, 0))


def format_markdown(result: PipelineResult, budget_chars: int | None = None) -> str:
    """Render a concise, user-facing Markdown summary."""
    budget = budget_chars or _budget()
    lang = getattr(result, "response_language", i18n.DEFAULT_LANGUAGE) or i18n.DEFAULT_LANGUAGE
    # Guidance-only modes return a rubric, not a document inspection. Plagiarism also
    # carries a guidance_id (PLAGIARISM_CHECK) but is a real check, so it is excluded.
    is_guidance = getattr(result, "guidance_id", None) in _GUIDANCE_ONLY_IDS
    lines: list[str] = []
    status_label = i18n.status_label(result.status, lang, guidance=is_guidance)

    lines.append(f"**Report Guard — {status_label}**")
    if result.summary:
        lines.append("")
        lines.append(result.summary.strip())

    # Guidance-only tools carry their actual rubric in `sections`. Render it so the
    # user/LLM sees the concrete rules and checklists, not just "guidance provided".
    sections = getattr(result, "sections", None)
    if is_guidance and sections:
        for s in sections:
            lines.append("")
            lines.append(f"**{s.title}**")
            if getattr(s, "body", ""):
                lines.append(s.body)
            for item in getattr(s, "checklist", None) or []:
                lines.append(f"- {item}")

    # Full checks render each tool's findings/links inside the per-tool detail block
    # already embedded in the summary, so the flat aggregated lists are skipped here
    # to avoid duplication.
    is_full_check = isinstance(result, FullCheckResult)

    if result.findings and not is_full_check:
        lines.append("")
        lines.append(f"**{i18n.header('findings', lang)} ({len(result.findings)})**")
        for f in sorted(result.findings, key=_finding_priority, reverse=True):
            line = f"- [{i18n.severity_label(f.severity, lang)}] {f.title}: {f.message}"
            if f.suggestion:
                line += f" → {f.suggestion}"
            lines.append(line)

    if result.links and not is_full_check:
        lines.append("")
        lines.append(f"**{i18n.header('links', lang)}**")
        for link in result.links:
            lines.append(f"- [{link.title}]({link.url})")

    if result.limitations:
        lines.append("")
        lines.append(f"**{i18n.header('limitations', lang)}**")
        lines.extend(f"- {item}" for item in result.limitations)

    if result.next_actions:
        lines.append("")
        lines.append(f"**{i18n.header('next_steps', lang)}**")
        lines.extend(f"- {item}" for item in result.next_actions)

    if result.partial_failures:
        lines.append("")
        lines.append(f"**{i18n.header('partial', lang)}**")
        lines.extend(f"- {msg}" for msg in i18n.humanize_partial_failures(result.partial_failures, lang))

    text = "\n".join(lines)
    if len(text) > budget:
        text = text[: budget - 1].rstrip() + "…"
    return text


def _serialized_len(result: PipelineResult, markdown: str) -> int:
    structured = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    return len(structured) + len(markdown)


def compress_result(result: PipelineResult, budget_chars: int | None = None) -> PipelineResult:
    """Shed lower-priority detail until the response fits the budget.

    Order: truncate evidence excerpts → drop duplicate links → drop lowest
    severity/confidence findings. Summary, status, limitations, and next_actions
    are always preserved.
    """
    budget = (budget_chars or _budget()) - _ENVELOPE_HEADROOM
    working = result.model_copy(deep=True)

    def fits() -> bool:
        return _serialized_len(working, format_markdown(working)) <= budget

    if fits():
        return working

    # 0) full_check carries verbose `sub_results` for structured consumption. They
    # duplicate the aggregated top-level findings/links, so drop them first when the
    # response is over budget (the compact summary + aggregated findings remain).
    if getattr(working, "sub_results", None):
        working.sub_results = None
        if fits():
            return working

    # 1) Truncate long evidence excerpts.
    for f in working.findings:
        for ev in f.evidence:
            if ev.excerpt and len(ev.excerpt) > 160:
                ev.excerpt = ev.excerpt[:157] + "…"
    if fits():
        return working

    # 2) Drop duplicate links by URL.
    seen: set[str] = set()
    deduped = []
    for link in working.links:
        if link.url in seen:
            continue
        seen.add(link.url)
        deduped.append(link)
    working.links = deduped
    if fits():
        return working

    # 3) Drop lowest-priority findings one at a time.
    working.findings.sort(key=_finding_priority, reverse=True)
    while working.findings and not fits():
        working.findings.pop()

    # 4) Trim links if still over budget.
    while working.links and not fits():
        working.links.pop()

    if not fits():
        lang = getattr(working, "response_language", i18n.DEFAULT_LANGUAGE) or i18n.DEFAULT_LANGUAGE
        working.limitations = list(working.limitations) + [
            _OMITTED_NOTE.get(lang, _OMITTED_NOTE["en"])
        ]
    return working


def to_mcp_response(result: PipelineResult) -> McpToolResponse:
    """Convert a PipelineResult into the MCP tool response boundary shape."""
    compressed = compress_result(result)
    markdown = format_markdown(compressed)
    is_error = compressed.status in (Status.INVALID_INPUT, Status.INTERNAL_ERROR)
    return McpToolResponse(
        content=[{"type": "text", "text": markdown}],
        structuredContent=compressed.model_dump(mode="json"),
        isError=is_error,
    )


__all__ = [
    "McpToolResponse",
    "format_markdown",
    "compress_result",
    "to_mcp_response",
]
