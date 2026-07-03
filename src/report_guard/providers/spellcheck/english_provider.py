"""Offline English word-level spell-check via pyspellchecker (local, no network).

Word-level only (not grammar). For each text unit it finds unknown English words and
suggests the most likely correction, preserving original capitalization. Fully local:
no external transmission, so on its own this provider is openWorldHint-false. (The
shipped default composite still calls Naver for Korean, so the tool stays
openWorldHint-true.)
"""

from __future__ import annotations

import re
from functools import lru_cache

from ...schemas import Confidence, Status, TextLocation
from .base import SpellcheckCorrection, SpellcheckProviderResult

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_PROVIDER = "pyspellchecker"


@lru_cache(maxsize=1)
def _checker():
    from spellchecker import SpellChecker

    return SpellChecker(language="en")


def _match_case(original: str, candidate: str) -> str:
    if original.isupper():
        return candidate.upper()
    if original[:1].isupper():
        return candidate[:1].upper() + candidate[1:]
    return candidate


class EnglishSpellProvider:
    name = _PROVIDER

    def check_text(
        self, units: list[str], language: str, deadline_ms: int
    ) -> SpellcheckProviderResult:
        try:
            sp = _checker()
        except Exception:  # noqa: BLE001 — dictionary load failure degrades cleanly
            from ...errors import ErrorCode, module_error

            return SpellcheckProviderResult(
                status=Status.EXTERNAL_ERROR,
                provider_name=_PROVIDER,
                errors=[
                    module_error(
                        ErrorCode.PROVIDER_UNAVAILABLE,
                        "The English dictionary could not be loaded.",
                        module="providers/spellcheck",
                        provider=_PROVIDER,
                    )
                ],
            )

        corrections: list[SpellcheckCorrection] = []
        for idx, unit in enumerate(units):
            words = _WORD.findall(unit)
            # Only words of length >= 2 and not already known.
            candidates = [w for w in words if len(w) >= 2 and w.lower() not in sp]
            unknown = sp.unknown([w.lower() for w in candidates]) if candidates else set()
            seen: set[str] = set()
            for w in candidates:
                lw = w.lower()
                if lw not in unknown or lw in seen:
                    continue
                seen.add(lw)
                suggestion = sp.correction(lw)
                if not suggestion or suggestion == lw:
                    continue
                corrections.append(
                    SpellcheckCorrection(
                        original=w,
                        corrected=_match_case(w, suggestion),
                        message="Possible English spelling issue.",
                        location=TextLocation(sentence_index=idx),
                        confidence=Confidence.MEDIUM,
                    )
                )

        status = Status.OK if corrections else Status.NO_FINDINGS
        return SpellcheckProviderResult(
            status=status, provider_name=_PROVIDER, corrections=corrections
        )


__all__ = ["EnglishSpellProvider"]
