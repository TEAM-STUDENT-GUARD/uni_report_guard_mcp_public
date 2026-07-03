"""Temporary stub helpers (Slice 2). Replaced as real pipelines land."""
from __future__ import annotations

from ..schemas import PipelineResult, Status


def stub_result(name: str) -> PipelineResult:
    return PipelineResult(
        status=Status.OK,
        summary=f"[stub] {name} pipeline not yet implemented.",
        limitations=["This is a placeholder result; full logic lands in a later slice."],
        next_actions=["Implement the real pipeline."],
    )
