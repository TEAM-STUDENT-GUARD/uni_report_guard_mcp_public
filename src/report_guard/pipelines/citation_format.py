"""pipelines/citation_format — returns CITATION_FORMAT rubric (guidance only).

Provides the correct citation/표기법 rules for the host LLM to apply to the user's
document. Does not inspect the document and makes no external calls.
"""

from __future__ import annotations

from .. import i18n
from ..schemas import PipelineResult, RequestContext
from ._guidance_common import build_guidance_result


def run(args: dict, context: RequestContext) -> PipelineResult:
    return build_guidance_result(
        "CITATION_FORMAT", i18n.resolve_response_language(context.language_hint)
    )


__all__ = ["run"]
