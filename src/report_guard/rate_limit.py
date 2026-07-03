"""Per-process invocation guard.

Cheap sliding-window cost limiter that runs BEFORE any external API call so that a
burst of plagiarism/full-check requests cannot exhaust Naver/Crossref quota or
latency budget. Stateless server caveat: this is a soft, per-process guard, not a
distributed quota — it mitigates accidental/abusive repeats on a single instance.
"""

from __future__ import annotations

import threading
import time

from . import config
from .errors import ErrorCode, ModuleError, module_error
from .schemas import RequestContext

# Relative cost per tool — external/search tools cost more than local ones.
_TOOL_COST: dict[str, int] = {
    "count_document_units": 1,
    "get_writing_structure_guidance": 1,
    "get_required_fields_guidance": 1,
    "check_document_citations": 3,
    "check_document_spelling": 3,
    "check_document_plagiarism": 8,
    "run_full_report_check": 12,
}

_lock = threading.Lock()
_events: list[tuple[float, int]] = []  # (timestamp_s, cost)


def estimate_cost(tool_name: str, _input: object | None = None) -> int:
    return _TOOL_COST.get(tool_name, 2)


def check_request(context: RequestContext, cost: int) -> ModuleError | None:
    """Admit or reject a request based on accumulated cost in the recent window."""
    window_ms = config.get_limit("RATE_LIMIT_WINDOW_MS")
    max_cost = config.get_limit("RATE_LIMIT_MAX_COST")
    now = time.monotonic()
    cutoff = now - (window_ms / 1000.0)

    with _lock:
        # Drop expired events, then sum the live window.
        live = [(ts, c) for ts, c in _events if ts >= cutoff]
        _events[:] = live
        current = sum(c for _, c in live)
        if current + cost > max_cost:
            # Local policy limit — not an upstream quota problem.
            return module_error(
                ErrorCode.INVALID_INPUT,
                "Too many requests in a short period. Please retry shortly.",
                module="rate_limit",
                retryable=True,
                limit=int(max_cost),
            )
        _events.append((now, cost))
    return None


def reset() -> None:
    with _lock:
        _events.clear()


__all__ = ["estimate_cost", "check_request", "reset"]
