"""Slice 3 — counts pipeline + segmentation fixtures."""

from __future__ import annotations

from report_guard.pipelines import counts
from report_guard.schemas import RequestContext, Status
from report_guard.text import chunker, segmentation


def _ctx(language=None):
    return RequestContext(
        request_id="t", tool_name="count_document_units", deadline_ms=3000,
        received_at="now", language_hint=language,
    )


def _run(text, **options):
    args = {"document_text": text}
    if options:
        args["options"] = options
    return counts.run(args, _ctx())


def test_basic_english_counts():
    r = _run("Hello world. This is a test!\n\nSecond paragraph here.")
    m = r.metrics
    assert r.status is Status.OK
    assert m["word_count"] == 9
    assert m["sentence_count"] == 3
    assert m["paragraph_count"] == 2


def test_include_spaces_toggle():
    text = "a b c"
    with_spaces = _run(text, include_spaces=True).metrics["character_count"]
    without = _run(text, include_spaces=False).metrics["character_count"]
    assert with_spaces == 5
    assert without == 3


def test_korean_counts():
    r = _run("안녕하세요. 반갑습니다!")
    m = r.metrics
    assert m["sentence_count"] == 2
    assert m["character_count"] > 0
    assert m["language"] == "ko"


def test_mixed_language_does_not_fail():
    r = _run("This is 한국어 mixed 문장 test sentence example.")
    assert r.status is Status.OK
    assert r.metrics["language"] in ("mixed", "ko", "en")


def test_empty_paragraph_handling():
    r = _run("Only one line with no double newline.")
    assert r.metrics["paragraph_count"] == 1


def test_oversize_document_invalid(monkeypatch):
    monkeypatch.setenv("MAX_DOCUMENT_CHARS", "5")
    r = _run("way too long to count")
    assert r.status is Status.INVALID_INPUT


def test_detect_language_unknown():
    assert segmentation.detect_language("123 456 789") == "unknown"


def test_chunker_bounds_queries():
    sentences = segmentation.split_sentences("A. B. C. D. E. F.")
    chunks = chunker.build_sentence_chunks(sentences, sentence_chunk_size=2, max_queries=2)
    assert len(chunks) == 2
    assert chunks[0].sentence_indexes == [0, 1]


def test_chunker_never_whole_document():
    long_sentence = "word " * 100 + "."
    sentences = segmentation.split_sentences(long_sentence)
    chunks = chunker.build_sentence_chunks(sentences, sentence_chunk_size=5, max_queries=4)
    assert all(len(c.query_text) <= 230 for c in chunks)
