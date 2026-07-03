"""Citation title normalization for verification queries.

Pure/local. Trims, collapses whitespace, strips common bibliographic noise, and
deduplicates titles for external calls while mapping back to original indexes.
Empty titles are invalid input.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from ..errors import ErrorCode, ModuleError, module_error

_WS = re.compile(r"\s+")
# Leading list markers like "1.", "[1]", "- ".
_LEADING_MARKER = re.compile(r"^\s*(?:\[\d+\]|\(\d+\)|\d+[.)]|[-*•])\s*")


class CitationQuery(BaseModel):
    original_title: str
    normalized_title: str
    index: int


def _normalize(title: str) -> str:
    t = _LEADING_MARKER.sub("", title)
    t = _WS.sub(" ", t).strip()
    # Strip surrounding quotes/brackets.
    t = t.strip("\"'“”‘’[]")
    return t.strip()


def normalize_titles(citation_titles: list[str]) -> list[CitationQuery] | ModuleError:
    if not citation_titles:
        return module_error(
            ErrorCode.INVALID_INPUT,
            "At least one citation title is required.",
            module="citation/parser",
            field="citation_titles",
        )
    queries: list[CitationQuery] = []
    for idx, raw in enumerate(citation_titles):
        normalized = _normalize(raw or "")
        if not normalized:
            return module_error(
                ErrorCode.INVALID_INPUT,
                "Citation titles must not be empty.",
                module="citation/parser",
                field=f"citation_titles[{idx}]",
            )
        queries.append(
            CitationQuery(original_title=raw, normalized_title=normalized, index=idx)
        )
    return queries


def dedupe_for_external(queries: list[CitationQuery]) -> dict[str, list[int]]:
    """Map normalized_title -> list of original indexes (case-insensitive)."""
    groups: dict[str, list[int]] = {}
    for q in queries:
        key = q.normalized_title.casefold()
        groups.setdefault(key, []).append(q.index)
    return groups


__all__ = ["CitationQuery", "normalize_titles", "dedupe_for_external"]
