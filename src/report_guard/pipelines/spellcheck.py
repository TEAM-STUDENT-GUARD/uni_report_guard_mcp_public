"""pipelines/spellcheck — spelling check via a free provider (hanspell online v1).

Segments the document into bounded sentence units, sends only those units to the
provider, and returns original→corrected pairs. Discloses external transmission and
flags possible false positives. Provider failure degrades to partial/external_error,
never a crash. Document text is never logged.
"""

from __future__ import annotations

import re

from .. import i18n
from ..config import get_int_limit
from ..references import find_reference_section
from ..providers.spellcheck import get_default_provider
from ..providers.spellcheck.base import SpellcheckCorrection, SpellcheckProvider
from ..schemas import (
    Evidence,
    Finding,
    PipelineResult,
    RequestContext,
    Severity,
    Status,
    TextLocation,
)
from ..security import sanitize_user_text, validate_document_size
from ..text import segmentation

# The Naver speller caps a request at ~500 chars, so pack sentences up to this to
# leave margin for join spaces. One packed request then covers many sentences.
_PACK_MAX_CHARS = 450


class _Chunk:
    """A group of consecutive sentences sent to the provider as one unit."""

    __slots__ = ("text", "sentences", "indices")

    def __init__(self) -> None:
        self.text = ""
        self.sentences: list[str] = []
        self.indices: list[int] = []  # global sentence index of each member


def _pack_sentences(sentences: list, max_chars: int) -> list[_Chunk]:
    """Greedily pack consecutive sentences into <=max_chars chunks."""
    chunks: list[_Chunk] = []
    cur = _Chunk()
    cur_len = 0
    for gi, s in enumerate(sentences):
        st = s.text.strip()
        if not st:
            continue
        sep = 1 if cur.sentences else 0
        if cur.sentences and cur_len + sep + len(st) > max_chars:
            cur.text = " ".join(cur.sentences)
            chunks.append(cur)
            cur = _Chunk()
            cur_len = 0
            sep = 0
        cur.sentences.append(st)
        cur.indices.append(gi)
        cur_len += sep + len(st)
    if cur.sentences:
        cur.text = " ".join(cur.sentences)
        chunks.append(cur)
    return chunks


def _resplit(text: str, language: str) -> list[str]:
    return [s.text.strip() for s in segmentation.split_sentences(text, language) if s.text.strip()]


_LINEBREAK_RE = re.compile(r"(?:<br\s*/?>|[\r\n]+)")
_WS_OR_BR_RE = re.compile(r"(?:<br\s*/?>|\s)+")
# Reference lists (English titles, DOIs, romanized names) are a big false-positive
# source for a Korean speller, so the bibliography is excluded from spell checking.
def _strip_reference_section(text: str) -> tuple[str, bool]:
    section = find_reference_section(text)
    if section is None:
        return text, False
    heading_start, _ = section
    return text[:heading_start].rstrip(), True


def _is_linebreak_noise(original: str, corrected: str) -> bool:
    """True when the only change is line-break/reflow formatting (e.g. the speller
    inserting <br> between header fields), not a real spelling or spacing fix.

    Word-spacing (띄어쓰기) fixes on a single line are kept; only changes that add or
    move line breaks while leaving the text otherwise identical are treated as noise.
    """
    if _WS_OR_BR_RE.sub("", original) != _WS_OR_BR_RE.sub("", corrected):
        return False  # a real character difference — keep it
    return bool(_LINEBREAK_RE.search(original) or _LINEBREAK_RE.search(corrected))


def _remap_corrections(
    corrections: list[SpellcheckCorrection], chunks: list[_Chunk], language: str
) -> list[SpellcheckCorrection]:
    """Map chunk-level (whole-unit) corrections back to per-sentence corrections.

    A Korean chunk comes back as one corrected string for the whole packed unit. We
    re-split it and pair sentences 1:1 with the originals, emitting a finding only for
    sentences that actually changed. If the sentence counts don't line up (the speller
    merged/split), we fall back to one coarse finding for the whole chunk. Word-level
    (English) corrections — whose `original` is a single word, not the chunk — pass
    through unchanged.
    """
    out: list[SpellcheckCorrection] = []
    for corr in corrections:
        ci = corr.location.sentence_index if corr.location else None
        chunk = chunks[ci] if (ci is not None and 0 <= ci < len(chunks)) else None
        if chunk is not None and len(chunk.indices) > 1 and corr.original == chunk.text:
            orig_sents = chunk.sentences
            corr_sents = _resplit(corr.corrected, language)
            if len(corr_sents) == len(orig_sents):
                for os_, cs_, sidx in zip(orig_sents, corr_sents, chunk.indices):
                    if os_.strip() != cs_.strip():
                        out.append(SpellcheckCorrection(
                            original=os_, corrected=cs_,
                            location=TextLocation(sentence_index=sidx),
                            confidence=corr.confidence))
            else:
                out.append(SpellcheckCorrection(
                    original=corr.original, corrected=corr.corrected,
                    location=TextLocation(sentence_index=chunk.indices[0]),
                    confidence=corr.confidence))
        else:
            out.append(corr)
    return out

_EXTERNAL_DISCLOSURE = (
    "Korean text is checked via an external free service (Naver speller); minimal "
    "text units are sent and not stored. English is checked with a local dictionary "
    "(word-level spelling only, no grammar)."
)
_FALSE_POSITIVE_NOTE = (
    "Suggestions may be false positives for proper nouns, domain terms, citations, "
    "or quoted text. Review before applying."
)
_EXTERNAL_DISCLOSURE_KO = (
    "한국어는 외부 무료 서비스(네이버 맞춤법 검사)로 점검하며 최소 단위 텍스트만 전송하고 "
    "저장하지 않습니다. 영어는 로컬 사전으로 단어 철자만 확인합니다(문법 검사 아님)."
)
_FALSE_POSITIVE_NOTE_KO = (
    "고유명사, 전문 용어, 영어 도구명, 논문 제목, 참고문헌이나 인용 표기는 실제 오류가 "
    "아닌데도 제안될 수 있으니 적용 전 확인이 필요합니다."
)


def run(
    args: dict,
    context: RequestContext,
    provider: SpellcheckProvider | None = None,
) -> PipelineResult:
    document_text = args.get("document_text", "")
    options = args.get("options") or {}
    max_findings = int(options.get("max_findings", 50))
    rlang = i18n.resolve_response_language(context.language_hint, document_text)
    ko = rlang == "ko"

    size_err = validate_document_size(document_text)
    if size_err is not None:
        return PipelineResult(
            status=Status.INVALID_INPUT,
            summary=("문서가 너무 커서 맞춤법을 검사할 수 없습니다." if ko
                     else "Document is too large to spell-check."),
            limitations=(["문서 길이를 줄인 뒤 다시 시도하세요."] if ko
                         else ["Reduce the document length and try again."]),
            next_actions=(["더 짧은 일부만 제출하세요."] if ko
                          else ["Submit a shorter excerpt."]),
            partial_failures=[size_err],
            response_language=rlang,
        )

    text = sanitize_user_text(document_text)
    # Skip the bibliography: romanized names, English titles, and DOIs there trigger
    # many false positives from the Korean speller.
    text, dropped_refs = _strip_reference_section(text)
    language = segmentation.detect_language(text, context.language_hint)
    sentences = segmentation.split_sentences(text, language)

    # Pack consecutive sentences into ~480-char chunks so each external request covers
    # many sentences instead of one, then bound the number of chunks. The real limit
    # is request latency, not text volume, so this multiplies coverage for free.
    max_units = get_int_limit("SPELLCHECK_MAX_UNITS")
    all_chunks = _pack_sentences(sentences, _PACK_MAX_CHARS)
    truncated = len(all_chunks) > max_units
    chunks = all_chunks[:max_units]
    units = [c.text for c in chunks]

    if not units:
        return PipelineResult(
            status=Status.NO_FINDINGS,
            summary=("검사할 문장을 찾지 못했습니다." if ko
                     else "No checkable sentences were found."),
            limitations=[_EXTERNAL_DISCLOSURE_KO if ko else _EXTERNAL_DISCLOSURE],
            next_actions=[],
            response_language=rlang,
        )

    provider = provider or get_default_provider()
    result = provider.check_text(units, language, context.deadline_ms)

    limitations = (
        [_EXTERNAL_DISCLOSURE_KO, _FALSE_POSITIVE_NOTE_KO] if ko
        else [_EXTERNAL_DISCLOSURE, _FALSE_POSITIVE_NOTE]
    )
    if truncated:
        covered = sum(len(c.text) for c in chunks)
        limitations.append(
            f"분량 제한으로 문서 앞부분(약 {covered}자)까지만 검사했습니다." if ko
            else f"Only the first ~{covered} characters were checked to stay within limits."
        )
    if dropped_refs:
        limitations.append(
            "참고문헌 목록은 오탐이 많아 맞춤법 검사에서 제외했습니다." if ko
            else "The reference list was excluded from spell checking to avoid false positives."
        )

    # Provider failed entirely.
    if result.status is Status.EXTERNAL_ERROR and not result.corrections:
        return PipelineResult(
            status=Status.EXTERNAL_ERROR,
            summary=("맞춤법 검사 서비스에 현재 연결할 수 없습니다." if ko
                     else "The spell-check service is currently unavailable."),
            limitations=limitations,
            next_actions=(["잠시 후 다시 시도하거나 맞춤법을 직접 확인하세요."] if ko
                          else ["Try again shortly, or check spelling manually."]),
            partial_failures=result.errors,
            response_language=rlang,
        )

    # Chunk-level (Korean) corrections are remapped back to per-sentence findings,
    # then line-break/reflow-only suggestions are dropped so the count reflects real
    # spelling/spacing issues rather than <br> formatting noise on header/structure lines.
    remapped = _remap_corrections(result.corrections, chunks, language)
    remapped = [c for c in remapped if not _is_linebreak_noise(c.original, c.corrected)]

    findings: list[Finding] = []
    finding_title = "맞춤법, 문법 또는 형식 관련 제안" if ko else "Possible spelling/grammar issue"
    for idx, corr in enumerate(remapped[:max_findings]):
        findings.append(
            Finding(
                id=f"sp-{idx}",
                category="spelling",
                severity=Severity.LOW,
                confidence=corr.confidence,
                title=finding_title,
                message=corr.original,
                suggestion=corr.corrected,
                evidence=[
                    Evidence(
                        kind="text_span",
                        excerpt=corr.original[:160],
                        location=corr.location or TextLocation(sentence_index=idx),
                    )
                ],
            )
        )

    metrics = {
        "checked_units": len(units),
        "checked_sentences": sum(len(c.indices) for c in chunks),
        "issue_count": len(remapped),
        "provider_name": result.provider_name,
        "provider_timed_out": result.timed_out,
    }

    if result.timed_out and findings:
        status = Status.PARTIAL
        if ko:
            summary = (
                f"검사가 시간 초과로 중단되기 전까지 맞춤법, 문법 또는 줄바꿈/문단 구분 "
                f"관련 제안 {len(findings)}건이 확인되었습니다. 확정된 오류가 아니므로 "
                "문맥에 맞게 검토해야 합니다."
            )
        else:
            summary = f"{len(findings)} possible issue(s) found before the checker timed out."
    elif not findings:
        status = Status.NO_FINDINGS
        summary = "맞춤법 관련 문제가 발견되지 않았습니다." if ko else "No spelling issues detected."
    else:
        status = Status.OK
        total_issues = len(remapped)
        if ko:
            summary = (
                f"맞춤법 자체의 명확한 오류보다는 줄바꿈, 문단 구분 등 형식 관련 제안을 "
                f"포함해 {total_issues}건의 점검 항목이 확인되었습니다. 확정된 "
                "오류가 아니므로 적용 전 문맥 확인이 필요합니다."
            )
            if total_issues > len(findings):
                summary += f" (상위 {len(findings)}건 표시)"
        else:
            summary = f"{total_issues} possible spelling/grammar issue(s) found."
            if total_issues > len(findings):
                summary += f" Showing top {len(findings)}."

    return PipelineResult(
        status=status,
        summary=summary,
        findings=findings,
        metrics=metrics,
        limitations=limitations,
        next_actions=(["각 제안을 문맥에 맞게 검토한 뒤 적용하세요."] if ko
                      else ["Review each suggestion in context before applying."]),
        partial_failures=result.errors if result.timed_out else [],
        response_language=rlang,
    )


__all__ = ["run"]
