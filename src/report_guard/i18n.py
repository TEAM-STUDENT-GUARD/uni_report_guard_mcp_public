"""Response-language resolution and user-facing label catalogs (ko/en).

Report Guard returns Korean-first responses: Korean by default, English only when
the caller asks for it (`language: "en"`) or an English document is detected under
`auto`. Pipelines author their `summary`/`limitations`/`next_actions` in the
resolved language and tag the `PipelineResult.response_language`; `result_formatter`
reads that tag to pick status labels and section headers. Internal error codes are
never shown to users — `humanize_partial_failures` maps them to one plain-language
line per cause, in the response language.
"""

from __future__ import annotations

from .errors import ErrorCode
from .schemas import Status
from .text import segmentation

DEFAULT_LANGUAGE = "ko"


def resolve_response_language(language_hint: str | None, document_text: str = "") -> str:
    """Return the response language ("ko" | "en").

    - "ko"/"en" hints are honored verbatim.
    - "auto"/None/"" detect the document's primary language (Korean-first): an
      English document yields "en"; Korean, mixed, or empty/unknown yields "ko".
    """
    if language_hint == "ko":
        return "ko"
    if language_hint == "en":
        return "en"
    detected = segmentation.detect_language(document_text or "", None)
    return "en" if detected == "en" else "ko"


STATUS_LABELS: dict[str, dict[Status, str]] = {
    "ko": {
        Status.OK: "✅ 검사 완료",
        Status.NO_FINDINGS: "✅ 발견된 문제 없음",
        Status.PARTIAL: "⚠️ 부분 결과",
        Status.INVALID_INPUT: "⛔ 입력 오류",
        Status.EXTERNAL_ERROR: "⚠️ 외부 서비스 오류",
        Status.INTERNAL_ERROR: "⛔ 내부 오류",
    },
    "en": {
        Status.OK: "✅ Checked",
        Status.NO_FINDINGS: "✅ No issues found",
        Status.PARTIAL: "⚠️ Partial result",
        Status.INVALID_INPUT: "⛔ Invalid input",
        Status.EXTERNAL_ERROR: "⚠️ External service error",
        Status.INTERNAL_ERROR: "⛔ Internal error",
    },
}

# Intuitive severity labels (raw "LOW/medium" pairs are not user-friendly).
SEVERITY_LABELS: dict[str, dict[str, str]] = {
    "ko": {"info": "참고", "low": "경미", "medium": "주의", "high": "중요"},
    "en": {"info": "info", "low": "minor", "medium": "notice", "high": "important"},
}


def severity_label(severity, lang: str) -> str:
    table = SEVERITY_LABELS.get(lang, SEVERITY_LABELS[DEFAULT_LANGUAGE])
    return table.get(str(getattr(severity, "value", severity)), str(severity))


# The limitations header carries an explicit relay instruction: user tests showed
# the client LLM treating this section as optional context and dropping caveats
# (e.g. "참고용 가이드입니다") from its answer to the user.
HEADERS: dict[str, dict[str, str]] = {
    "ko": {
        "findings": "발견 사항",
        "links": "관련 링크",
        "limitations": "유의사항 (사용자에게 결과와 함께 전달)",
        "next_steps": "다음 단계",
        "partial": "일부 확인하지 못한 항목",
    },
    "en": {
        "findings": "Findings",
        "links": "Links",
        "limitations": "Limitations (relay to the user with the results)",
        "next_steps": "Next steps",
        "partial": "Partial failures",
    },
}

# Plain-language summaries for internal error codes. Raw codes (CONFIG_MISSING,
# PROVIDER_TIMEOUT, …) are never surfaced; repeats collapse to one line per cause.
_PARTIAL_FAILURE_MESSAGES: dict[str, dict[str, str]] = {
    "ko": {
        ErrorCode.CONFIG_MISSING.value:
            "검색 설정 또는 검증 대상 정보가 부족해 해당 검사를 완료하지 못했습니다.",
        ErrorCode.PROVIDER_TIMEOUT.value:
            "외부 조회가 지연되어 일부 결과를 확인하지 못했습니다(미확인/부분 결과).",
        ErrorCode.PROVIDER_UNAVAILABLE.value:
            "외부 서비스에 일시적으로 연결하지 못해 일부 검사를 완료하지 못했습니다.",
        ErrorCode.EXTERNAL_BAD_RESPONSE.value:
            "외부 서비스 응답을 해석하지 못해 일부 검사를 완료하지 못했습니다.",
        ErrorCode.EXTERNAL_RATE_LIMITED.value:
            "짧은 시간에 외부 검색 요청이 몰려 일부 조회가 일시적으로 제한되었습니다. 잠시 후 다시 시도하면 됩니다.",
        ErrorCode.EXTERNAL_QUOTA_EXCEEDED.value:
            "외부 서비스의 사용 한도를 초과해 일부 검사를 완료하지 못했습니다.",
    },
    "en": {
        ErrorCode.CONFIG_MISSING.value:
            "A required search setting or input was missing, so this check could not be completed.",
        ErrorCode.PROVIDER_TIMEOUT.value:
            "An external lookup timed out, so some results are unconfirmed (partial result).",
        ErrorCode.PROVIDER_UNAVAILABLE.value:
            "An external service was temporarily unavailable, so some checks could not be completed.",
        ErrorCode.EXTERNAL_BAD_RESPONSE.value:
            "An external service response could not be parsed, so some checks could not be completed.",
        ErrorCode.EXTERNAL_RATE_LIMITED.value:
            "External search requests were briefly throttled, so some lookups were limited. Try again shortly.",
        ErrorCode.EXTERNAL_QUOTA_EXCEEDED.value:
            "An external service usage quota was exceeded, so some checks could not be completed.",
    },
}
_PARTIAL_FAILURE_DEFAULT: dict[str, str] = {
    "ko": "일부 외부 검사를 완료하지 못했습니다.",
    "en": "Some external checks could not be completed.",
}


_GUIDANCE_LABEL = {"ko": "✅ 가이드 제공", "en": "✅ Guidance provided"}


def status_label(status: Status, lang: str, *, guidance: bool = False) -> str:
    if guidance and status in (Status.OK, Status.NO_FINDINGS):
        return _GUIDANCE_LABEL.get(lang, _GUIDANCE_LABEL["en"])
    table = STATUS_LABELS.get(lang, STATUS_LABELS[DEFAULT_LANGUAGE])
    return table.get(status, str(status))


def header(key: str, lang: str) -> str:
    table = HEADERS.get(lang, HEADERS[DEFAULT_LANGUAGE])
    return table.get(key, key)


def humanize_partial_failures(errors, lang: str) -> list[str]:
    """Collapse internal error codes into deduplicated, plain-language lines."""
    table = _PARTIAL_FAILURE_MESSAGES.get(lang, _PARTIAL_FAILURE_MESSAGES[DEFAULT_LANGUAGE])
    default = _PARTIAL_FAILURE_DEFAULT.get(lang, _PARTIAL_FAILURE_DEFAULT[DEFAULT_LANGUAGE])
    messages: list[str] = []
    seen: set[str] = set()
    for err in errors:
        code = getattr(err.code, "value", str(err.code))
        text = table.get(code, default)
        if text in seen:
            continue
        seen.add(text)
        messages.append(text)
    return messages


__all__ = [
    "DEFAULT_LANGUAGE",
    "resolve_response_language",
    "status_label",
    "header",
    "humanize_partial_failures",
]
