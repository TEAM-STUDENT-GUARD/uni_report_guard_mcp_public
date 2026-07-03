"""Slice 9 — import-discipline tests enforcing the dependency tree (no cycles)."""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src" / "report_guard"


def _imports(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def _imports_anything(module_path: Path, forbidden_substrings: tuple[str, ...]) -> list[str]:
    found = []
    for imp in _imports(module_path):
        for bad in forbidden_substrings:
            if bad in imp:
                found.append(imp)
    return found


def test_clients_do_not_import_pipelines_or_transport():
    for client in (_SRC / "clients").glob("*.py"):
        bad = _imports_anything(
            client, ("pipelines", "pipeline_orchestrator", "mcp_transport", "tool_registry")
        )
        assert not bad, f"{client.name} imports {bad}"


def test_low_level_modules_do_not_import_pipelines():
    for name in ("config", "security", "errors", "schemas", "logging",
                 "rate_limit", "observability"):
        module = _SRC / f"{name}.py"
        bad = _imports_anything(module, ("pipelines", "pipeline_orchestrator", "mcp_transport"))
        assert not bad, f"{name} imports {bad}"


def test_result_formatter_does_not_import_pipelines():
    bad = _imports_anything(_SRC / "result_formatter.py", ("pipelines",))
    assert not bad


def test_feature_pipelines_do_not_import_full_check():
    for pipeline in (_SRC / "pipelines").glob("*.py"):
        if pipeline.name in ("full_check.py", "__init__.py"):
            continue
        bad = _imports_anything(pipeline, ("full_check",))
        assert not bad, f"{pipeline.name} imports {bad}"


def test_no_kakao_in_source_identifiers():
    # Server/tool names must never contain "kakao".
    from report_guard import SERVER_NAME, tool_registry

    assert "kakao" not in SERVER_NAME.lower()
    for t in tool_registry.list_tools():
        assert "kakao" not in t.name.lower()
        assert "kakao" not in t.title.lower()
