"""Spell-check provider selection.

Default v1 provider is the composite (Korean via online Naver speller + English via
the local pyspellchecker dictionary). `SPELLCHECK_PROVIDER` overrides:
  - `composite` (default): Korean + English routing.
  - `naver` / `hanspell`: Korean online speller only.
  - `english`: local English dictionary only (offline).
  - `mock`: deterministic offline provider used in tests.
The pipeline injects a provider for testing; otherwise it asks for the default here.
"""

from __future__ import annotations

from ... import config
from .base import (
    SpellcheckCorrection,
    SpellcheckProvider,
    SpellcheckProviderResult,
)


def get_default_provider() -> SpellcheckProvider:
    name = config.get_string("SPELLCHECK_PROVIDER").lower() or "composite"
    if name == "mock":
        from .mock_provider import MockSpellcheckProvider

        return MockSpellcheckProvider()
    if name in ("naver", "hanspell"):
        from .hanspell_provider import HanspellProvider

        return HanspellProvider()
    if name == "english":
        from .english_provider import EnglishSpellProvider

        return EnglishSpellProvider()
    from .composite_provider import CompositeSpellProvider

    return CompositeSpellProvider()


__all__ = [
    "get_default_provider",
    "SpellcheckProvider",
    "SpellcheckProviderResult",
    "SpellcheckCorrection",
]
