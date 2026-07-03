"""Sentence chunking for bounded plagiarism queries.

Groups sentences into query chunks bounded by `max_queries`, keeping each query
short enough for the Naver Search API. Never emits the whole document as a single
query. Pure/local; used by pipelines/plagiarism (Slice 7).
"""

from __future__ import annotations

from .segmentation import TextUnit, split_sentences

# Naver query practical upper bound (chars). Keep queries compact.
_MAX_QUERY_CHARS = 230


class QueryChunk:
    __slots__ = ("query_text", "index", "sentence_indexes")

    def __init__(self, query_text: str, index: int, sentence_indexes: list[int]):
        self.query_text = query_text
        self.index = index
        self.sentence_indexes = sentence_indexes


def build_sentence_chunks(
    sentences: list[TextUnit],
    sentence_chunk_size: int,
    max_queries: int,
) -> list[QueryChunk]:
    """Build up to `max_queries` chunks of `sentence_chunk_size` sentences each."""
    size = max(1, sentence_chunk_size)
    chunks: list[QueryChunk] = []
    idx = 0
    for start in range(0, len(sentences), size):
        if idx >= max(1, max_queries):
            break
        group = sentences[start : start + size]
        text = " ".join(u.text for u in group).strip()
        if len(text) > _MAX_QUERY_CHARS:
            text = text[:_MAX_QUERY_CHARS].rstrip()
        if not text:
            continue
        chunks.append(QueryChunk(text, idx, [u.index for u in group]))
        idx += 1
    return chunks


def chunks_from_document(
    document_text: str,
    sentence_chunk_size: int,
    max_queries: int,
    language: str | None = None,
) -> list[QueryChunk]:
    return build_sentence_chunks(
        split_sentences(document_text, language), sentence_chunk_size, max_queries
    )


__all__ = ["QueryChunk", "build_sentence_chunks", "chunks_from_document"]
