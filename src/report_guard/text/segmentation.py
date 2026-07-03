"""Korean/English-aware text segmentation for deterministic counting.

Pure, local, deterministic. No external calls. Offsets are computed against the
normalized text so paragraph/sentence/word boundaries are stable and reproducible.
Counting conventions are documented inline and surfaced via `calculation_notes`.
"""

from __future__ import annotations

import re
import unicodedata

from ..schemas import TextLocation

# Sentence terminators: ASCII . ! ? and CJK/fullwidth 。！？…
_SENTENCE_END = re.compile(r"[^.!?。！？…]*[.!?。！？…]+|\S[^.!?。！？…]*$", re.UNICODE)
# A word: a run of letters/numbers (Unicode aware), including CJK; hyphens/apostrophes
# inside words are kept.
_WORD = re.compile(r"[\w][\w'\-]*", re.UNICODE)
# Paragraphs split on one or more blank lines.
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")


class TextUnit:
    __slots__ = ("text", "index", "location")

    def __init__(self, text: str, index: int, location: TextLocation):
        self.text = text
        self.index = index
        self.location = location

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"TextUnit(index={self.index}, text={self.text!r})"


def normalize_text(document_text: str) -> str:
    """Normalize line endings and Unicode form; preserve content/length intent.

    - CRLF/CR -> LF
    - Unicode NFC so combining sequences count as single characters consistently.
    """
    text = document_text.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


def detect_language(document_text: str, hint: str | None = None) -> str:
    """Return "ko" | "en" | "mixed" | "unknown". Mixed text never fails."""
    if hint in ("ko", "en"):
        return hint
    hangul = sum(1 for ch in document_text if "가" <= ch <= "힣")
    latin = sum(1 for ch in document_text if ("a" <= ch.lower() <= "z"))
    if hangul == 0 and latin == 0:
        return "unknown"
    if hangul and latin:
        # Both present; call it mixed unless one is negligible.
        ratio = hangul / (hangul + latin)
        if 0.15 < ratio < 0.85:
            return "mixed"
        return "ko" if ratio >= 0.85 else "en"
    return "ko" if hangul else "en"


def split_paragraphs(document_text: str) -> list[TextUnit]:
    text = normalize_text(document_text)
    units: list[TextUnit] = []
    idx = 0
    for raw in _PARAGRAPH_SPLIT.split(text):
        para = raw.strip()
        if not para:
            continue
        start = text.find(para)
        units.append(
            TextUnit(
                para,
                idx,
                TextLocation(paragraph_index=idx, start_offset=start,
                             end_offset=start + len(para) if start >= 0 else None),
            )
        )
        idx += 1
    return units


def split_sentences(document_text: str, language: str | None = None) -> list[TextUnit]:
    text = normalize_text(document_text)
    units: list[TextUnit] = []
    idx = 0
    for match in _SENTENCE_END.finditer(text):
        sentence = match.group().strip()
        if not sentence:
            continue
        units.append(
            TextUnit(
                sentence,
                idx,
                TextLocation(sentence_index=idx, start_offset=match.start(),
                             end_offset=match.end()),
            )
        )
        idx += 1
    return units


def split_words(document_text: str, language: str | None = None) -> list[TextUnit]:
    text = normalize_text(document_text)
    units: list[TextUnit] = []
    for idx, match in enumerate(_WORD.finditer(text)):
        units.append(
            TextUnit(
                match.group(),
                idx,
                TextLocation(start_offset=match.start(), end_offset=match.end()),
            )
        )
    return units


def count_characters(document_text: str, include_spaces: bool = True) -> int:
    """Count characters of the normalized text.

    include_spaces=True  -> counts every character including whitespace.
    include_spaces=False -> excludes all Unicode whitespace.
    """
    text = normalize_text(document_text)
    if include_spaces:
        return len(text)
    return sum(1 for ch in text if not ch.isspace())


__all__ = [
    "TextUnit",
    "normalize_text",
    "detect_language",
    "split_paragraphs",
    "split_sentences",
    "split_words",
    "count_characters",
]
