"""Similarity scoring for plagiarism-risk signals.

Pure/local. Produces a 0.0–1.0 indicator (token Jaccard + character bigram blend)
between a source sentence chunk and a candidate title/snippet. Scores are risk
indicators, not proof of plagiarism.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

_TOKEN = re.compile(r"[\w]+", re.UNICODE)
# Strip Naver/HTML highlight tags such as <b>...</b>.
_TAG = re.compile(r"</?b>|<[^>]+>")


def _tokens(text: str) -> set[str]:
    return {t.casefold() for t in _TOKEN.findall(text)}


def _char_bigrams(text: str) -> set[str]:
    cleaned = re.sub(r"\s+", " ", text.casefold()).strip()
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)} if len(cleaned) > 1 else set()


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def strip_markup(text: str) -> str:
    return _TAG.sub("", text or "")


def score_match(source_text: str, candidate_text: str) -> float:
    """Blend token Jaccard (0.6) and char-bigram Jaccard (0.4); range 0.0–1.0."""
    src = strip_markup(source_text)
    cand = strip_markup(candidate_text)
    token = _jaccard(_tokens(src), _tokens(cand))
    bigram = _jaccard(_char_bigrams(src), _char_bigrams(cand))
    return round(0.6 * token + 0.4 * bigram, 4)


class ScoredMatch(BaseModel):
    source_index: int
    candidate_title: str
    candidate_snippet: str
    candidate_url: str
    score: float
    source_text: str = ""  # the document passage that matched (for user context)


def filter_matches(matches: list[ScoredMatch], threshold: float) -> list[ScoredMatch]:
    kept = [m for m in matches if m.score >= threshold]
    kept.sort(key=lambda m: m.score, reverse=True)
    return kept


__all__ = ["score_match", "ScoredMatch", "filter_matches", "strip_markup"]
