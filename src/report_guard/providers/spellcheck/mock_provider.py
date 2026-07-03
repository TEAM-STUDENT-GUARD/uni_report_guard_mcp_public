"""Deterministic in-memory spell-check provider for tests and offline runs.

Applies a tiny fixed substitution table so tests never touch the network and the
pipeline can be exercised without depending on hanspell availability.
"""

from __future__ import annotations

from ...schemas import Confidence, Status, TextLocation
from .base import SpellcheckCorrection, SpellcheckProviderResult

# Minimal known-wrong -> right map (KO/EN) for deterministic tests.
_FIXES: dict[str, str] = {
    "되요": "돼요",
    "안되": "안 돼",
    "teh": "the",
    "recieve": "receive",
    "wierd": "weird",
}


class MockSpellcheckProvider:
    name = "mock"

    def __init__(self, fail: bool = False, timeout: bool = False):
        self._fail = fail
        self._timeout = timeout

    def check_text(
        self, units: list[str], language: str, deadline_ms: int
    ) -> SpellcheckProviderResult:
        if self._timeout:
            from ...errors import ErrorCode, module_error

            return SpellcheckProviderResult(
                status=Status.EXTERNAL_ERROR,
                provider_name=self.name,
                timed_out=True,
                errors=[
                    module_error(
                        ErrorCode.PROVIDER_TIMEOUT,
                        "Spell-check provider timed out.",
                        module="providers/spellcheck",
                        retryable=True,
                        provider=self.name,
                    )
                ],
            )
        if self._fail:
            from ...errors import ErrorCode, module_error

            return SpellcheckProviderResult(
                status=Status.EXTERNAL_ERROR,
                provider_name=self.name,
                errors=[
                    module_error(
                        ErrorCode.PROVIDER_UNAVAILABLE,
                        "Spell-check provider is unavailable.",
                        module="providers/spellcheck",
                        retryable=True,
                        provider=self.name,
                    )
                ],
            )

        corrections: list[SpellcheckCorrection] = []
        for idx, unit in enumerate(units):
            corrected = unit
            for wrong, right in _FIXES.items():
                if wrong in corrected:
                    corrected = corrected.replace(wrong, right)
            if corrected != unit:
                corrections.append(
                    SpellcheckCorrection(
                        original=unit,
                        corrected=corrected,
                        location=TextLocation(sentence_index=idx),
                        confidence=Confidence.MEDIUM,
                    )
                )
        status = Status.OK if corrections else Status.NO_FINDINGS
        return SpellcheckProviderResult(
            status=status, provider_name=self.name, corrections=corrections
        )


__all__ = ["MockSpellcheckProvider"]
