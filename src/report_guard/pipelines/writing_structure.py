"""pipelines/writing_structure — returns GOOD_WRITING rubric (guidance only)."""

from __future__ import annotations

from .. import i18n
from ..schemas import PipelineResult, RequestContext
from ._guidance_common import build_guidance_result


def run(args: dict, context: RequestContext) -> PipelineResult:
    return build_guidance_result(
        "GOOD_WRITING", i18n.resolve_response_language(context.language_hint)
    )


__all__ = ["run"]
