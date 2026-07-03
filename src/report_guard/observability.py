"""Lightweight in-process metrics: latency, counts, error classes.

No document body, email, or secret ever enters a metric name or tag. Tags are
restricted to the same non-sensitive vocabulary as logging.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

_ALLOWED_TAG_KEYS: frozenset[str] = frozenset(
    {"tool_name", "pipeline_name", "provider_name", "status", "error_code", "http_status"}
)


@dataclass
class _Metrics:
    counters: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    timings_ms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))


_METRICS = _Metrics()


def _safe_tags(tags: dict[str, object] | None) -> dict[str, object]:
    if not tags:
        return {}
    return {k: v for k, v in tags.items() if k in _ALLOWED_TAG_KEYS}


def _key(name: str, tags: dict[str, object]) -> str:
    if not tags:
        return name
    suffix = ",".join(f"{k}={tags[k]}" for k in sorted(tags))
    return f"{name}{{{suffix}}}"


def record_metric(metric_name: str, value: float, tags: dict[str, object] | None = None) -> None:
    _METRICS.counters[_key(metric_name, _safe_tags(tags))] += value


class TimerHandle:
    def __init__(self, name: str, tags: dict[str, object]):
        self._name = name
        self._tags = tags
        self._start = time.perf_counter()

    def stop(self) -> float:
        elapsed_ms = (time.perf_counter() - self._start) * 1000.0
        _METRICS.timings_ms[_key(self._name, self._tags)].append(elapsed_ms)
        return elapsed_ms

    def __enter__(self) -> "TimerHandle":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()


def start_timer(name: str, tags: dict[str, object] | None = None) -> TimerHandle:
    return TimerHandle(name, _safe_tags(tags))


def snapshot() -> dict[str, object]:
    """Read-only view for health/diagnostics — never contains sensitive data."""
    return {
        "counters": dict(_METRICS.counters),
        "timing_counts": {k: len(v) for k, v in _METRICS.timings_ms.items()},
    }


def reset() -> None:
    _METRICS.counters.clear()
    _METRICS.timings_ms.clear()


__all__ = ["record_metric", "start_timer", "TimerHandle", "snapshot", "reset"]
