"""Small retry helper for external HTTP calls.

Retries a call up to a fixed number of attempts when its normalized result is a
*retryable* failure (timeout, provider unavailable, 5xx, a transient rate limit).
Non-retryable outcomes — success, 404/not-found, missing config, quota exceeded,
invalid input — return immediately. A short linear backoff separates attempts.

Clients normalize failures to a result object carrying `status` + `errors`, and each
`ModuleError` already flags `retryable`, so callers pass a small predicate that reads
those fields.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

MAX_ATTEMPTS = 2  # initial attempt + 1 retry
_BASE_DELAY_S = 0.3


def with_retries(
    attempt: Callable[[], T],
    is_retryable: Callable[[T], bool],
    *,
    max_attempts: int = MAX_ATTEMPTS,
    base_delay_s: float = _BASE_DELAY_S,
) -> T:
    """Run `attempt()`, retrying while `is_retryable(result)` up to `max_attempts`."""
    result = attempt()
    tries = 1
    while tries < max_attempts and is_retryable(result):
        time.sleep(base_delay_s * tries)  # linear backoff (0.3s, 0.6s, …)
        result = attempt()
        tries += 1
    return result


__all__ = ["with_retries", "MAX_ATTEMPTS"]
