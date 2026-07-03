"""Spell-check provider interface + normalized result types.

A provider takes bounded text units and returns original→corrected pairs. Adapters
own all conversion from provider-specific output and must never leak raw provider
payloads. External-call adapters additionally apply timeout/UTF-8/allowlist/SSRF
and degrade to a no-result/partial state instead of crashing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ...errors import ModuleError
from ...schemas import Confidence, Status, TextLocation


class SpellcheckCorrection(BaseModel):
    original: str
    corrected: str
    message: str | None = None
    location: TextLocation | None = None
    confidence: Confidence = Confidence.MEDIUM


class SpellcheckProviderResult(BaseModel):
    status: Status
    provider_name: str
    corrections: list[SpellcheckCorrection] = Field(default_factory=list)
    errors: list[ModuleError] = Field(default_factory=list)
    timed_out: bool = False


@runtime_checkable
class SpellcheckProvider(Protocol):
    name: str

    def check_text(
        self, units: list[str], language: str, deadline_ms: int
    ) -> SpellcheckProviderResult:
        ...


__all__ = [
    "SpellcheckCorrection",
    "SpellcheckProviderResult",
    "SpellcheckProvider",
]
