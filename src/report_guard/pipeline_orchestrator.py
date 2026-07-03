"""Routes validated tool calls to pipelines and isolates their failures.

Owns the fixed tool→pipeline routing table and the per-call timeout budget. Catches
any pipeline exception and converts it to a normalized error result so a single
failing check can never crash the server. Does not parse MCP protocol details.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable

from . import config, logging as rg_logging, observability
from .errors import ErrorCode, ModuleError, ReportGuardError, module_error
from .schemas import PipelineResult, RequestContext, Status

# Fixed routing table: pipeline key -> module path exposing run(args, context).
_PIPELINE_MODULES: dict[str, str] = {
    "counts": "report_guard.pipelines.counts",
    "spellcheck": "report_guard.pipelines.spellcheck",
    "citation": "report_guard.pipelines.citation",
    "plagiarism": "report_guard.pipelines.plagiarism",
    "writing_structure": "report_guard.pipelines.writing_structure",
    "required_fields": "report_guard.pipelines.required_fields",
    "citation_format": "report_guard.pipelines.citation_format",
    "full_check": "report_guard.pipelines.full_check",
}


def _load_runner(pipeline_key: str) -> Callable[[dict, RequestContext], PipelineResult]:
    module = importlib.import_module(_PIPELINE_MODULES[pipeline_key])
    return module.run


def _error_result(err: ModuleError, status: Status) -> PipelineResult:
    return PipelineResult(
        status=status,
        summary=err.message,
        limitations=[],
        next_actions=["Retry later." if err.retryable else "Check the input and try again."],
        partial_failures=[err],
    )


def execute(
    pipeline_key: str,
    validated_input: dict,
    context: RequestContext,
) -> PipelineResult:
    """Run one pipeline with exception isolation and latency metrics."""
    if pipeline_key not in _PIPELINE_MODULES:
        return _error_result(
            module_error(
                ErrorCode.INTERNAL_ERROR,
                "No pipeline is registered for this tool.",
                module="pipeline_orchestrator",
                pipeline=pipeline_key,
            ),
            Status.INTERNAL_ERROR,
        )

    timer = observability.start_timer("pipeline_ms", {"pipeline_name": pipeline_key})
    try:
        runner = _load_runner(pipeline_key)
        result = runner(validated_input, context)
    except ReportGuardError as exc:
        result = _error_result(exc.error, Status.EXTERNAL_ERROR
                               if exc.error.code.name.startswith("EXTERNAL")
                               else Status.INTERNAL_ERROR)
    except Exception:  # noqa: BLE001 — isolate any unexpected pipeline failure
        # Never surface raw exception text (could contain document fragments).
        err = module_error(
            ErrorCode.INTERNAL_ERROR,
            "An internal error occurred while running this check.",
            module=f"pipelines/{pipeline_key}",
            pipeline=pipeline_key,
        )
        result = _error_result(err, Status.INTERNAL_ERROR)
    finally:
        duration_ms = timer.stop()

    rg_logging.log_event(
        "info",
        "pipeline_complete",
        {
            "request_id": context.request_id,
            "tool_name": context.tool_name,
            "pipeline_name": pipeline_key,
            "status": str(result.status),
            "duration_ms": round(duration_ms, 2),
        },
    )
    observability.record_metric(
        "pipeline_calls", 1, {"pipeline_name": pipeline_key, "status": str(result.status)}
    )
    return result


def default_deadline_ms() -> int:
    return config.get_int_limit("DEFAULT_TIMEOUT_MS")


__all__ = ["execute", "default_deadline_ms"]
