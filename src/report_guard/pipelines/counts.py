"""pipelines/counts — deterministic local document statistics.

Returns character/word/sentence/paragraph counts. A count is -1 only when it cannot
be computed, with the reason recorded in `calculation_notes`. No external calls.
"""

from __future__ import annotations

from .. import i18n
from ..schemas import PipelineResult, RequestContext, Status
from ..security import sanitize_user_text, validate_document_size
from ..text import segmentation


def run(args: dict, context: RequestContext) -> PipelineResult:
    document_text = args.get("document_text", "")
    options = args.get("options") or {}
    include_spaces = bool(options.get("include_spaces", True))
    rlang = i18n.resolve_response_language(context.language_hint, document_text)

    size_err = validate_document_size(document_text)
    if size_err is not None:
        return PipelineResult(
            status=Status.INVALID_INPUT,
            summary=("문서가 너무 커서 분량을 계산할 수 없습니다." if rlang == "ko"
                     else "Document is too large to count."),
            limitations=(["문서 길이를 줄인 뒤 다시 시도하세요."] if rlang == "ko"
                         else ["Reduce the document length and try again."]),
            next_actions=(["더 짧은 일부만 제출하세요."] if rlang == "ko"
                          else ["Submit a shorter excerpt."]),
            partial_failures=[size_err],
            response_language=rlang,
        )

    text = sanitize_user_text(document_text)
    notes: list[str] = []

    language = segmentation.detect_language(text, context.language_hint)

    try:
        character_count = segmentation.count_characters(text, include_spaces)
    except Exception:  # noqa: BLE001
        character_count = -1
        notes.append("character_count could not be computed.")

    try:
        word_count = len(segmentation.split_words(text, language))
    except Exception:  # noqa: BLE001
        word_count = -1
        notes.append("word_count could not be computed.")

    try:
        sentence_count = len(segmentation.split_sentences(text, language))
    except Exception:  # noqa: BLE001
        sentence_count = -1
        notes.append("sentence_count could not be computed.")

    try:
        paragraph_count = len(segmentation.split_paragraphs(text))
    except Exception:  # noqa: BLE001
        paragraph_count = -1
        notes.append("paragraph_count could not be computed.")

    notes.append(
        "characters " + ("include" if include_spaces else "exclude") + " whitespace"
    )
    notes.append("sentences split on . ! ? 。 ！ ？ …")
    notes.append("paragraphs split on blank lines")
    if language in ("mixed", "unknown"):
        notes.append(f"detected language: {language}")

    metrics = {
        "character_count": character_count,
        "word_count": word_count,
        "sentence_count": sentence_count,
        "paragraph_count": paragraph_count,
        "character_count_includes_spaces": include_spaces,
        "calculation_notes": notes,
        "language": language,
    }

    uncomputable = any(
        c == -1 for c in (character_count, word_count, sentence_count, paragraph_count)
    )
    status = Status.PARTIAL if uncomputable else Status.OK
    # The space basis lives in the summary because format_markdown does not render
    # metrics: without it the client LLM has been observed guessing (wrongly) which
    # basis was used when relaying the count to the user.
    if rlang == "ko":
        basis = "공백 포함" if include_spaces else "공백 제외"
        summary = (
            f"문서에는 총 {character_count}자({basis}), {word_count}단어, "
            f"{sentence_count}문장, {paragraph_count}문단이 포함되어 있습니다."
        )
        limitations = (
            ["일부 항목은 계산할 수 없었습니다. 자세한 내용은 calculation_notes를 참고하세요."]
            if uncomputable else []
        )
    else:
        basis = "including spaces" if include_spaces else "excluding spaces"
        summary = (
            f"{character_count} characters ({basis}), {word_count} words, "
            f"{sentence_count} sentences, {paragraph_count} paragraphs."
        )
        limitations = (
            ["Some counts could not be computed; see calculation_notes."]
            if uncomputable else []
        )

    return PipelineResult(
        status=status,
        summary=summary,
        metrics=metrics,
        limitations=limitations,
        next_actions=[],
        response_language=rlang,
    )


__all__ = ["run"]
