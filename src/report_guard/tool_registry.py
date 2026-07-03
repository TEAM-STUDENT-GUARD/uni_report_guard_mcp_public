"""Tool metadata, JSON-Schema input contracts, annotations, and input validation.

`tool_registry` owns the 7 public tool definitions. It depends only on tool
definitions + schema validators (jsonschema) and shared `schemas`/`errors`. It must
not own business logic or call clients.

Annotation matrix (docs/INTER_MODULE_INTERFACES.md §5.2):
  - all tools: readOnlyHint=true, destructiveHint=false, idempotentHint=true
  - openWorldHint: true for spelling (hanspell online), citation, plagiarism,
    full-check; false for counts and the three guidance tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as _JsonSchemaValidationError

from .errors import ErrorCode, ModuleError, module_error

# --- Reusable schema fragments ---------------------------------------------
_LANGUAGE = {"type": "string", "enum": ["ko", "en", "auto"]}

# The verbatim instruction matters: user tests caught a client LLM re-typing the
# document into this field (inserted spaces, added a file header), which shifted
# the character count by ~1% versus the same document sent to another tool.
_DOCUMENT_TEXT = {
    "type": "string",
    "minLength": 1,
    "description": "검사할 문서 원문. 공백·줄바꿈을 고치거나 재포맷하지 말고 그대로 전달하세요.",
}


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    schema: dict = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


# --- Input schemas (docs §4) ------------------------------------------------
_COUNT_INPUT = _obj(
    {
        "document_text": _DOCUMENT_TEXT,
        "language": _LANGUAGE,
        "options": _obj({"include_spaces": {"type": "boolean"}}),
    },
    required=["document_text"],
)

_SPELLING_INPUT = _obj(
    {
        "document_text": _DOCUMENT_TEXT,
        "language": _LANGUAGE,
        "options": _obj({"max_findings": {"type": "integer", "minimum": 1}}),
    },
    required=["document_text"],
)

_CITATION_INPUT = _obj(
    {
        "citation_titles": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
        },
        "user_email": {"type": "string"},
        "options": _obj({"max_results": {"type": "integer", "minimum": 1}}),
    },
    required=["citation_titles"],
)

_PLAGIARISM_INPUT = _obj(
    {
        "document_text": _DOCUMENT_TEXT,
        "language": _LANGUAGE,
        "options": _obj(
            {
                "sentence_chunk_size": {"type": "integer", "minimum": 1},
                "similarity_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                "max_queries": {"type": "integer", "minimum": 1},
                "max_results": {"type": "integer", "minimum": 1},
            }
        ),
    },
    required=["document_text"],
)

_EMPTY_INPUT = _obj({})

_FULL_CHECK_INPUT = _obj(
    {
        "document_text": _DOCUMENT_TEXT,
        "citation_titles": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "user_email": {"type": "string"},
        "language": _LANGUAGE,
        "options": _obj(
            {
                "include_spaces": {"type": "boolean"},
                "sentence_chunk_size": {"type": "integer", "minimum": 1},
                "similarity_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                "max_queries": {"type": "integer", "minimum": 1},
                "max_results": {"type": "integer", "minimum": 1},
                "max_findings_per_pipeline": {"type": "integer", "minimum": 1},
            }
        ),
    },
    required=["document_text"],
)


@dataclass(frozen=True)
class ToolAnnotations:
    title: str
    readOnlyHint: bool = True
    destructiveHint: bool = False
    openWorldHint: bool = False
    idempotentHint: bool = True

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "readOnlyHint": self.readOnlyHint,
            "destructiveHint": self.destructiveHint,
            "openWorldHint": self.openWorldHint,
            "idempotentHint": self.idempotentHint,
        }


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    title: str
    description: str
    inputSchema: dict
    annotations: ToolAnnotations
    pipeline: str  # orchestrator routing key
    outputSchema: dict | None = field(default=None)


def _d(name: str, title: str, description: str, schema: dict, pipeline: str,
       *, open_world: bool) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        title=title,
        description=description,
        inputSchema=schema,
        annotations=ToolAnnotations(title=title, openWorldHint=open_world),
        pipeline=pipeline,
    )


# --- The 7 public tools -----------------------------------------------------
_TOOLS: list[ToolDefinition] = [
    _d(
        "count_document_units",
        "Document unit counter",
        "리포트 제출 전 과제 분량 조건을 확인할 때 사용합니다. "
        "문서의 글자 수, 단어 수, 문장 수, 문단 수를 계산하고, "
        "공백 포함 여부와 기본 분량 지표를 함께 보여줍니다.",
        _COUNT_INPUT,
        "counts",
        open_world=False,
    ),
    _d(
        "check_document_spelling",
        "Spelling checker",
        "리포트 제출 전 맞춤법, 문법, 띄어쓰기, 어색한 표현을 점검할 때 사용합니다. "
        "문서에서 수정이 필요한 문장을 찾아 고친 문장과 함께 보여줍니다. "
        "사람 이름, 전공 용어, 고유명사는 잘못 지적될 수 있으므로 최종 수정 전 직접 확인하세요.",
        _SPELLING_INPUT,
        "spellcheck",
        open_world=True,
    ),
    _d(
        "check_document_citations",
        "Citation checker",
        "리포트 제출 전 참고문헌이 올바르게 적혔는지 확인할 때 사용합니다. "
        "한국어 논문은 KCI, 해외 논문은 Semantic Scholar와 Crossref를 활용해 "
        "제목, 저자, 연도, DOI 등이 실제 논문 정보와 맞는지 점검합니다.",
        _CITATION_INPUT,
        "citation",
        open_world=True,
    ),
    _d(
        "check_document_plagiarism",
        "Plagiarism risk checker",        
        "리포트 제출 전 표절 위험 신호를 사전에 점검할 때 사용합니다. "
        "문서의 일부 문장과 비슷한 내용이 공개 웹에 있는지 검색해 관련 페이지 링크를 보여 주고, "
        "표절 여부를 확정하지는 않으며 직접 확인이 필요한 부분을 안내합니다.",
        _PLAGIARISM_INPUT,
        "plagiarism",
        open_world=True,
    ),
    _d(
        "get_writing_structure_guidance",
        "Writing structure guidance",
        "리포트 제출 전 문서의 짜임새를 점검할 때 사용합니다. "
        "서론-본론-결론, 실험 보고서, 조사 보고서 등 보고서 유형별 구조 기준과 "
        "확인해야 할 항목을 안내합니다. 문서 내용은 서버로 전송하지 않습니다.",
        _EMPTY_INPUT,
        "writing_structure",
        open_world=False,
    ),
    _d(
        "get_required_fields_guidance",
        "Required fields guidance",
        "리포트 제출 전 제목, 이름, 과목명, 제출일 등 기본 기재 항목을 확인할 때 사용합니다. "
        "표지나 첫 페이지에 빠진 항목이 없는지 점검 목록으로 안내하고, "
        "불필요한 개인정보를 적지 않도록 함께 확인합니다. 문서 내용은 서버로 전송하지 않습니다.",
        _EMPTY_INPUT,
        "required_fields",
        open_world=False,
    ),
    _d(
        "get_citation_format_guidance",
        "Citation format guidance",
        "리포트 제출 전 본문 인용과 참고문헌 표기 방식이 맞는지 확인할 때 사용합니다. "
        "APA, IEEE, 국내 양식 등 주요 인용 형식의 기본 기준을 안내하고, "
        "본문 인용과 참고문헌 목록이 서로 대응되는지 점검하는 방법을 알려줍니다. ",
        _EMPTY_INPUT,
        "citation_format",
        open_world=False,
    ),
    _d(
        "run_full_report_check",
        "Full report check",
        "리포트 제출 전 문서 전체를 한 번에 종합 점검할 때 사용합니다. "
        "분량, 맞춤법, 표절 위험 신호, 참고문헌, 문서 구조, 필수 항목, 인용 표기를 "
        "항목별로 확인하고 보완이 필요한 부분을 정리해 줍니다. ",
        _FULL_CHECK_INPUT,
        "full_check",
        open_world=True,
    ),
]

_BY_NAME: dict[str, ToolDefinition] = {t.name: t for t in _TOOLS}


def list_tools() -> list[ToolDefinition]:
    return list(_TOOLS)


def resolve(tool_name: str) -> ToolDefinition | ModuleError:
    tool = _BY_NAME.get(tool_name)
    if tool is None:
        return module_error(
            ErrorCode.INVALID_INPUT,
            f"Unknown tool '{tool_name}'.",
            module="tool_registry",
        )
    return tool


def validate_input(tool_name: str, arguments: dict | None) -> dict | ModuleError:
    """Validate arguments against the tool's JSON Schema (rejects unknown fields)."""
    tool = resolve(tool_name)
    if isinstance(tool, ModuleError):
        return tool
    args = arguments or {}
    validator = Draft202012Validator(tool.inputSchema)
    errors = sorted(validator.iter_errors(args), key=lambda e: list(e.path))
    if errors:
        first: _JsonSchemaValidationError = errors[0]
        field_path = ".".join(str(p) for p in first.path) or "(root)"
        return module_error(
            ErrorCode.INVALID_INPUT,
            f"Invalid input at '{field_path}': {first.message}",
            module="tool_registry",
            field=field_path,
        )
    return args


__all__ = [
    "ToolAnnotations",
    "ToolDefinition",
    "list_tools",
    "resolve",
    "validate_input",
]
