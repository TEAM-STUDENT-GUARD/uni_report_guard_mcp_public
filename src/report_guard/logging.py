"""Redaction-first structured logging.

Only an explicit allowlist of field names may be logged (see
`docs/INTER_MODULE_INTERFACES.md` §5.7). Any forbidden field is dropped; remaining
values are passed through `security.redact_sensitive`. Document text, emails,
secrets, raw upstream bodies, and raw headers can never be logged.
"""

from __future__ import annotations

import json
import logging
import sys

from .security import redact_sensitive

_ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "request_id",
        "tool_name",
        "status",
        "error_code",
        "duration_ms",
        "document_length",
        "pipeline_name",
        "provider_name",
        "http_status",
        "retryable",
    }
)

_logger = logging.getLogger("report_guard")
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def _filter_fields(fields: dict[str, object]) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key, value in fields.items():
        if key not in _ALLOWED_FIELDS:
            continue  # forbidden field — silently dropped
        if isinstance(value, str):
            safe[key] = redact_sensitive(value)
        else:
            safe[key] = value
    return safe


def log_event(level: str, event_name: str, fields: dict[str, object] | None = None) -> None:
    """Emit one structured log line containing only allowlisted, redacted fields."""
    payload = {"event": event_name, **_filter_fields(fields or {})}
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _logger.log(getattr(logging, level.upper(), logging.INFO), line)


__all__ = ["log_event"]
