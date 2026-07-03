"""Locate and split a document's bibliography (참고문헌) section.

Shared by full_check (to auto-extract citation titles) and spellcheck (to exclude the
reference list from Korean spell checking). Two heading shapes are handled:

  1. Heading on its own line — the well-formatted case:  "\n참고문헌\n[1] ...".
  2. Heading inline — when the host collapses newlines to spaces the heading is no
     longer line-anchored: "... 활용될 수 있다. 참고문헌 [1] ...". This is only treated
     as a heading when a reference-list marker ([1] / 1. / 1)) immediately follows, so
     ordinary prose like "분량, 참고문헌을 확인해야 한다" never triggers it.
"""

from __future__ import annotations

import re

_REF_KEYWORDS = (
    r"(?:참고\s*문헌|참고\s*자료|인용\s*문헌|references?|bibliography|works\s+cited)"
)

# Heading on its own line.
_REF_HEADING_LINE = re.compile(
    r"(?im)^\s*#{0,6}\s*(?:\d+[.)]\s*)?" + _REF_KEYWORDS + r"\s*:?\s*$"
)
# Inline heading (whitespace-collapsed docs): the keyword must be immediately followed
# by a list marker, so a Korean particle ("참고문헌을") or prose mention cannot match.
_REF_HEADING_INLINE = re.compile(
    r"(?i)" + _REF_KEYWORDS + r"\s*[:\-]?\s*(?=\[\s*\d|\d+[.)]\s)"
)
# Numbered entry markers ([1], [ 2 ] …) survive whitespace collapse, unlike newlines.
_ENTRY_MARKER = re.compile(r"\[\s*\d+\s*\]")


def find_reference_section(text: str) -> tuple[int, int] | None:
    """Return (heading_start, heading_end) for the bibliography, or None.

    A line-anchored heading wins (first occurrence); otherwise the LAST inline heading
    is used, since the real reference list sits at the end of the document.
    """
    text = text or ""
    m = _REF_HEADING_LINE.search(text)
    if m:
        return m.start(), m.end()
    last = None
    for mm in _REF_HEADING_INLINE.finditer(text):
        last = mm
    return (last.start(), last.end()) if last else None


def split_reference_entries(tail: str) -> list[str]:
    """Split the text after the heading into individual reference entries.

    Prefers explicit [n] markers (which survive newline collapse); falls back to
    line-splitting when there are none.
    """
    tail = tail or ""
    if _ENTRY_MARKER.search(tail):
        parts = _ENTRY_MARKER.split(tail)
    else:
        parts = tail.splitlines()
    return [p.strip() for p in parts if p.strip()]


__all__ = ["find_reference_section", "split_reference_entries"]
