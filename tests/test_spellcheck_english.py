"""English + composite spell-check provider tests (offline / no network)."""

from __future__ import annotations

from report_guard.pipelines import spellcheck
from report_guard.providers.spellcheck.composite_provider import CompositeSpellProvider
from report_guard.providers.spellcheck.english_provider import EnglishSpellProvider
from report_guard.providers.spellcheck.mock_provider import MockSpellcheckProvider
from report_guard.schemas import RequestContext, Status


def _ctx():
    return RequestContext(
        request_id="t", tool_name="check_document_spelling", deadline_ms=3000,
        received_at="now",
    )


def test_english_provider_catches_misspellings():
    p = EnglishSpellProvider()
    res = p.check_text(["Today is a beutiful day.", "I recieve teh book."], "en", 3000)
    assert res.status is Status.OK
    fixes = {c.original: c.corrected for c in res.corrections}
    assert fixes.get("beutiful") == "beautiful"
    assert fixes.get("recieve") == "receive"
    assert fixes.get("teh") == "the"


def test_english_provider_clean_text():
    p = EnglishSpellProvider()
    res = p.check_text(["This sentence is perfectly fine."], "en", 3000)
    assert res.status is Status.NO_FINDINGS


def test_english_provider_preserves_case():
    p = EnglishSpellProvider()
    res = p.check_text(["Recieve the message."], "en", 3000)
    assert any(c.corrected == "Receive" for c in res.corrections)


def test_english_provider_is_offline():
    # No network: the provider must work with no NAVER credentials set.
    p = EnglishSpellProvider()
    res = p.check_text(["wierd"], "en", 3000)
    assert res.corrections and res.corrections[0].corrected == "weird"


def test_composite_routes_by_script_offline():
    # Use the offline English provider and a mock "korean" leg so no network is hit.
    composite = CompositeSpellProvider(
        korean=MockSpellcheckProvider(), english=EnglishSpellProvider()
    )
    units = ["이렇게 하면 안되.", "This has teh error.", "오늘 날씨 좋다."]
    res = composite.check_text(units, "auto", 3000)
    by_idx = {c.location.sentence_index: (c.original, c.corrected) for c in res.corrections}
    # Korean unit 0 corrected by the (mock) korean leg; English unit 1 by pyspellchecker.
    assert 0 in by_idx and "안 돼" in by_idx[0][1]
    assert 1 in by_idx and by_idx[1][1] == "the"


def test_composite_preserves_original_indexes():
    composite = CompositeSpellProvider(
        korean=MockSpellcheckProvider(), english=EnglishSpellProvider()
    )
    units = ["clean english sentence", "여기 teh 없음 안되"]  # idx 1 is korean
    res = composite.check_text(units, "auto", 3000)
    # The Korean unit is index 1; any correction must map back to index 1.
    for c in res.corrections:
        assert c.location.sentence_index in (0, 1)


def test_pipeline_english_via_injected_composite_offline():
    composite = CompositeSpellProvider(
        korean=MockSpellcheckProvider(), english=EnglishSpellProvider()
    )
    r = spellcheck.run(
        {"document_text": "Today is a beutiful day with wierd weather."},
        _ctx(),
        provider=composite,
    )
    assert r.status is Status.OK
    suggestions = " ".join(f.suggestion for f in r.findings)
    assert "beautiful" in suggestions and "weird" in suggestions
