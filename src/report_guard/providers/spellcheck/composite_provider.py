"""Composite spell-check provider routing each text unit by script.

- Units containing Hangul -> Naver online speller (Korean).
- Otherwise units containing Latin letters -> local English dictionary.

This gives Korean + English coverage in one tool. Original unit indexes are
preserved when remapping sub-provider corrections. The Korean leg is the only
external call, so the tool keeps `openWorldHint: true`; a pure-English document
makes no external request.
"""

from __future__ import annotations

from ...schemas import Status
from .base import SpellcheckProviderResult
from .english_provider import EnglishSpellProvider
from .hanspell_provider import HanspellProvider

_PROVIDER = "naver_speller+pyspellchecker"


def _has_hangul(text: str) -> bool:
    return any("가" <= ch <= "힣" or "ㄱ" <= ch <= "ㅎ" for ch in text)


def _has_latin(text: str) -> bool:
    return any("a" <= ch.lower() <= "z" for ch in text)


class CompositeSpellProvider:
    name = _PROVIDER

    def __init__(self, korean=None, english=None):
        self._korean = korean or HanspellProvider()
        self._english = english or EnglishSpellProvider()

    def check_text(
        self, units: list[str], language: str, deadline_ms: int
    ) -> SpellcheckProviderResult:
        korean_units: list[str] = []
        korean_idx: list[int] = []
        english_units: list[str] = []
        english_idx: list[int] = []

        for i, unit in enumerate(units):
            if _has_hangul(unit):
                korean_units.append(unit)
                korean_idx.append(i)
            elif _has_latin(unit):
                english_units.append(unit)
                english_idx.append(i)

        corrections = []
        errors = []
        timed_out = False
        korean_failed = False

        if korean_units:
            kr = self._korean.check_text(korean_units, "ko", deadline_ms)
            for c in kr.corrections:
                pos = c.location.sentence_index if c.location else None
                if pos is not None and 0 <= pos < len(korean_idx):
                    c.location.sentence_index = korean_idx[pos]
                corrections.append(c)
            errors.extend(kr.errors)
            timed_out = timed_out or kr.timed_out
            korean_failed = kr.status is Status.EXTERNAL_ERROR and not kr.corrections

        if english_units:
            en = self._english.check_text(english_units, "en", deadline_ms)
            for c in en.corrections:
                pos = c.location.sentence_index if c.location else None
                if pos is not None and 0 <= pos < len(english_idx):
                    c.location.sentence_index = english_idx[pos]
                corrections.append(c)
            errors.extend(en.errors)

        # Order corrections by their (remapped) sentence index for stable output.
        corrections.sort(
            key=lambda c: (c.location.sentence_index if c.location and
                           c.location.sentence_index is not None else 0)
        )

        if errors and corrections:
            status = Status.PARTIAL
        elif korean_failed:
            status = Status.EXTERNAL_ERROR
        elif corrections:
            status = Status.OK
        else:
            status = Status.NO_FINDINGS

        return SpellcheckProviderResult(
            status=status,
            provider_name=_PROVIDER,
            corrections=corrections,
            errors=errors,
            timed_out=timed_out,
        )


__all__ = ["CompositeSpellProvider"]
