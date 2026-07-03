"""Normalized error model shared across modules.

Mirrors `docs/INTER_MODULE_INTERFACES.md` §2.4 verbatim. `ModuleError` is the only
error shape that crosses module boundaries. Messages and details are user-safe:
they must never contain raw document text, secrets, tokens, raw headers, raw stack
traces, or raw external response bodies.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    DOCUMENT_TOO_LARGE = "DOCUMENT_TOO_LARGE"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    EXTERNAL_RATE_LIMITED = "EXTERNAL_RATE_LIMITED"
    EXTERNAL_QUOTA_EXCEEDED = "EXTERNAL_QUOTA_EXCEEDED"
    EXTERNAL_BAD_RESPONSE = "EXTERNAL_BAD_RESPONSE"
    CONFIG_MISSING = "CONFIG_MISSING"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Diagnostic keys allowed inside ModuleError.details. Anything else is dropped so
# that raw upstream bodies / headers / secrets can never leak through details.
_ALLOWED_DETAIL_KEYS: frozenset[str] = frozenset(
    {
        "status_code",
        "http_status",
        "provider",
        "retry_after_ms",
        "field",
        "limit",
        "actual",
        "pipeline",
        "guidance_id",
        "reason_code",
    }
)


class ModuleError(BaseModel):
    """A safe, normalized error that may appear in tool output and logs."""

    code: ErrorCode
    message: str
    retryable: bool = False
    module: str = ""
    details: dict[str, object] = Field(default_factory=dict)

    def safe_details(self) -> dict[str, object]:
        """Return only allowlisted, non-sensitive diagnostic keys."""
        return {k: v for k, v in self.details.items() if k in _ALLOWED_DETAIL_KEYS}


class ReportGuardError(Exception):
    """Internal exception carrying a ModuleError. Pipelines may raise this; the
    orchestrator converts it into a normalized result. It is never surfaced raw.
    """

    def __init__(self, error: ModuleError):
        self.error = error
        super().__init__(error.message)


def module_error(
    code: ErrorCode,
    message: str,
    *,
    module: str = "",
    retryable: bool = False,
    **details: object,
) -> ModuleError:
    """Convenience constructor that drops any non-allowlisted detail key."""
    safe = {k: v for k, v in details.items() if k in _ALLOWED_DETAIL_KEYS}
    return ModuleError(
        code=code, message=message, retryable=retryable, module=module, details=safe
    )


__all__ = ["ErrorCode", "ModuleError", "ReportGuardError", "module_error"]
