"""Shared input/output contracts.

Encodes the type shapes from `docs/INTER_MODULE_INTERFACES.md` §2-§8 verbatim so
every pipeline produces the same normalized `PipelineResult`. Public tool argument
and result fields use `snake_case`; MCP wire fields (inputSchema, structuredContent,
isError, readOnlyHint, ...) keep MCP canonical casing and live in tool_registry /
mcp_transport, not here.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .errors import ModuleError


class Status(StrEnum):
    OK = "ok"
    NO_FINDINGS = "no_findings"
    PARTIAL = "partial"
    INVALID_INPUT = "invalid_input"
    EXTERNAL_ERROR = "external_error"
    INTERNAL_ERROR = "internal_error"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Severity ordering used by result_formatter when shedding low-priority detail.
SEVERITY_ORDER: dict[str, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
}
CONFIDENCE_ORDER: dict[str, int] = {
    Confidence.LOW: 0,
    Confidence.MEDIUM: 1,
    Confidence.HIGH: 2,
}


class TextLocation(BaseModel):
    paragraph_index: int | None = None
    sentence_index: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None


class Evidence(BaseModel):
    kind: str  # "text_span" | "citation" | "external_match" | "metric" | "guidance"
    excerpt: str | None = None  # short snippet only — never the full document
    location: TextLocation | None = None
    source: str | None = None
    score: float | None = None


class Finding(BaseModel):
    id: str
    category: str
    severity: Severity
    confidence: Confidence
    title: str
    message: str
    evidence: list[Evidence] = Field(default_factory=list)
    suggestion: str | None = None


class LinkResult(BaseModel):
    title: str
    url: str
    source: str | None = None
    confidence: Confidence | None = None


class PipelineResult(BaseModel):
    """The normalized result every pipeline returns; result_formatter renders it."""

    status: Status
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    metrics: dict[str, object] | None = None
    limitations: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    links: list[LinkResult] = Field(default_factory=list)
    partial_failures: list[ModuleError] = Field(default_factory=list)
    # User-facing language for summary/limitations/next_actions and the labels
    # result_formatter renders. "ko" (default, Korean-first) or "en".
    response_language: str = "ko"


class RequestContext(BaseModel):
    """Created by mcp_transport, threaded down through the orchestrator.

    Carries correlation + deadline only; never personal or document data.
    """

    request_id: str
    tool_name: str
    deadline_ms: int
    received_at: str  # ISO 8601 UTC
    language_hint: str | None = None  # "ko" | "en" | "auto"
    caller: dict[str, object] | None = None


# --- Guidance shapes (§8.1, §4.5/§4.6) ---


class GuidanceSection(BaseModel):
    title: str
    body: str
    checklist: list[str] = Field(default_factory=list)


class GuidanceDocument(BaseModel):
    guidance_id: str  # CITATION_CHECK | CITATION_FORMAT | PLAGIARISM_CHECK | GOOD_WRITING | TO_HAVE
    version: str
    title: str
    sections: list[GuidanceSection] = Field(default_factory=list)
    expected_llm_output_format: str = ""
    limitations: list[str] = Field(default_factory=list)


class GuidanceResult(PipelineResult):
    """PipelineResult plus guidance payload, returned by guidance-only tools."""

    guidance_id: str
    guidance_version: str
    sections: list[GuidanceSection] = Field(default_factory=list)
    expected_llm_output_format: str = ""


# --- Crossref / similarity helper shapes used by pipelines (§4.3, §6.5) ---


class CrossrefWorkSummary(BaseModel):
    title: str
    doi: str | None = None
    publisher: str | None = None
    publication_year: int | None = None
    authors: list[str] = Field(default_factory=list)
    url: str | None = None
    match_score: float | None = None
    cited_by_count: int | None = None


class FullCheckResult(PipelineResult):
    """run_full_report_check output. `sub_results` is for structured consumption;
    the Markdown summary stays compressed."""

    sub_results: dict[str, PipelineResult] | None = None


def empty_result(status: Status, summary: str) -> PipelineResult:
    """Small helper for stubs and early-return paths."""
    return PipelineResult(status=status, summary=summary)


__all__ = [
    "Status",
    "Severity",
    "Confidence",
    "SEVERITY_ORDER",
    "CONFIDENCE_ORDER",
    "TextLocation",
    "Evidence",
    "Finding",
    "LinkResult",
    "PipelineResult",
    "RequestContext",
    "GuidanceSection",
    "GuidanceDocument",
    "GuidanceResult",
    "CrossrefWorkSummary",
    "FullCheckResult",
    "empty_result",
]
