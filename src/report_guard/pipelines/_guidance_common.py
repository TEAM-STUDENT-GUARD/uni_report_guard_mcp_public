"""Shared builder for guidance-only pipelines (writing_structure, required_fields)."""
from __future__ import annotations

from ..guidance_provider import load_guidance
from ..errors import ModuleError
from ..schemas import GuidanceResult, PipelineResult, Status

# Korean framing per guidance type. Crucially, this instructs the ASSISTANT (the MCP
# client LLM) to APPLY the rubric to the user's actual document and report concrete
# findings — not to relay the guidance text back to the user.
_KO_SUMMARY: dict[str, str] = {
    "GOOD_WRITING": (
        "Report Guard 서버는 문서를 직접 검사하지 않았습니다. 이제 어시스턴트인 당신이 "
        "아래 기준을 사용자가 제출한 실제 문서에 하나씩 적용해, 문서의 구체적 문장과 문단을 "
        "근거로 구조와 완성도를 직접 평가한 결과를 제시하세요. 기준 목록을 그대로 나열하거나 "
        "사용자에게 되돌려주지 마세요."
    ),
    "TO_HAVE": (
        "Report Guard 서버는 문서를 직접 검사하지 않았습니다. 이제 어시스턴트인 당신이 "
        "아래 항목이 실제 문서에 있는지 하나씩 확인해, 포함된 항목과 빠진 항목을 문서 내용을 "
        "근거로 구체적으로 보고하세요. 항목 목록을 그대로 전달하지 마세요."
    ),
    "CITATION_FORMAT": (
        "Report Guard 서버는 문서를 직접 검사하지 않았습니다. 이제 어시스턴트인 당신이 "
        "아래 표기법 기준으로 실제 문서의 본문 인용과 참고문헌 목록을 직접 점검해, 항목별 "
        "문제와 수정안을 구체적으로 제시하세요. 규칙을 그대로 나열하지 마세요. 논문의 실제 "
        "존재 확인이 필요하면 사용자에게 check_document_citations 실행을 제안만 하고, "
        "사용자가 요청하기 전에는 직접 호출하지 마세요."
    ),
}

# Korean limitations for guidance tools. The rubric body (doc.sections) stays as
# authored; only these short user-facing caveats are localized.
_KO_LIMITATIONS = [
    "항목과 기대치는 과목, 교수자, 과제 안내에 따라 다를 수 있습니다.",
    "이는 공식 제출 요건이 아니라 참고용 가이드입니다.",
]


def build_guidance_result(guidance_id: str, rlang: str = "ko") -> PipelineResult:
    ko = rlang == "ko"
    doc = load_guidance(guidance_id)
    if isinstance(doc, ModuleError):
        return PipelineResult(
            status=Status.INTERNAL_ERROR,
            summary=("가이드 내용을 일시적으로 사용할 수 없습니다." if ko
                     else "Guidance content is temporarily unavailable."),
            limitations=(["가이드 문서를 불러오지 못했습니다."] if ko
                         else ["The guidance document could not be loaded."]),
            next_actions=(["잠시 후 다시 시도하세요."] if ko else ["Retry shortly."]),
            partial_failures=[doc],
            response_language=rlang,
        )

    if ko:
        section_titles = ", ".join(s.title for s in doc.sections) or "가이드"
        summary = _KO_SUMMARY.get(guidance_id, f"{doc.title}: {section_titles}.")
        next_actions = [
            "가이드 원문을 나열하지 말고, 이 기준으로 사용자의 실제 문서를 직접 검사한 "
            "결과(항목별 판정과 문서 근거)를 기대 출력 형식으로 제시하세요.",
        ]
        limitations = list(_KO_LIMITATIONS)
    else:
        section_titles = ", ".join(s.title for s in doc.sections) or "guidance"
        summary = (
            "The server did not inspect the document. Now YOU, the assistant, must apply the "
            "criteria below to the user's actual document and report specific, evidence-based "
            f"findings — do not relay this guidance back to the user. ({doc.title})"
        )
        next_actions = [
            "Apply these criteria to the user's actual document and report per-item findings "
            "with evidence in the expected output format; do not repeat the guidance verbatim."
        ]
        limitations = list(doc.limitations)
    return GuidanceResult(
        status=Status.OK,
        summary=summary,
        findings=[],
        limitations=limitations,
        next_actions=next_actions,
        guidance_id=doc.guidance_id,
        guidance_version=doc.version,
        sections=doc.sections,
        expected_llm_output_format=doc.expected_llm_output_format,
        response_language=rlang,
    )
