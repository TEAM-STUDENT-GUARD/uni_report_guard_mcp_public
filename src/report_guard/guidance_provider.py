"""Loads the four static guidance documents into GuidanceDocument objects.

Single shared loader for CITATION_CHECK, CITATION_FORMAT, PLAGIARISM_CHECK,
GOOD_WRITING, TO_HAVE.
Docs are parsed once and cached; a missing/unparseable doc is an internal config
error (ModuleError), never an exception that crashes a tool. Guidance content is
static and is not mutated at runtime.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .errors import ErrorCode, ModuleError, module_error
from .schemas import GuidanceDocument, GuidanceSection

_GUIDANCE_DIR = Path(__file__).parent / "guidance"

_VALID_IDS = {"CITATION_CHECK", "CITATION_FORMAT", "PLAGIARISM_CHECK", "GOOD_WRITING", "TO_HAVE"}

_META_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
_SECTION_RE = re.compile(r"^##\s+(.*?)\s*$", re.MULTILINE)


def _parse_front_meta(text: str) -> dict[str, str]:
    m = _META_RE.search(text)
    meta: dict[str, str] = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    return meta


def _split_sections(text: str) -> tuple[list[GuidanceSection], str, list[str]]:
    """Parse `## Section: ...` blocks; pull out expected-format and limitations."""
    sections: list[GuidanceSection] = []
    expected_format = ""
    limitations: list[str] = []

    matches = list(_SECTION_RE.finditer(text))
    for i, match in enumerate(matches):
        heading = match.group(1)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body_raw = text[start:end].strip()

        # Extract checklist bullets that follow a `checklist:` marker or are plain bullets.
        checklist: list[str] = []
        body_lines: list[str] = []
        in_checklist = False
        for line in body_raw.splitlines():
            stripped = line.strip()
            if stripped.lower() == "checklist:":
                in_checklist = True
                continue
            if stripped.startswith("- "):
                item = stripped[2:].strip()
                if in_checklist or heading.lower().startswith("section"):
                    checklist.append(item)
                else:
                    body_lines.append(item)
            elif stripped:
                body_lines.append(stripped)
        body = " ".join(body_lines).strip()

        lower = heading.lower()
        if lower.startswith("expected llm output") or lower.startswith("expected"):
            expected_format = body or body_raw.strip()
        elif lower.startswith("limitation"):
            limitations = checklist or [
                ln.strip()[2:].strip()
                for ln in body_raw.splitlines()
                if ln.strip().startswith("- ")
            ]
        elif lower.startswith("section"):
            title = heading.split(":", 1)[1].strip() if ":" in heading else heading
            sections.append(GuidanceSection(title=title, body=body, checklist=checklist))
    return sections, expected_format, limitations


@lru_cache(maxsize=8)
def _load_cached(guidance_id: str) -> GuidanceDocument | ModuleError:
    if guidance_id not in _VALID_IDS:
        return module_error(
            ErrorCode.INTERNAL_ERROR,
            "Unknown guidance document requested.",
            module="guidance_provider",
            guidance_id=guidance_id,
        )
    path = _GUIDANCE_DIR / f"{guidance_id}.md"
    if not path.is_file():
        return module_error(
            ErrorCode.INTERNAL_ERROR,
            "A required guidance document is missing.",
            module="guidance_provider",
            guidance_id=guidance_id,
        )
    text = path.read_text(encoding="utf-8")
    meta = _parse_front_meta(text)
    sections, expected_format, limitations = _split_sections(text)

    # Title: first H1 if present, else meta title.
    h1 = re.search(r"^#\s+(.*)$", text, re.MULTILINE)
    title = (h1.group(1).strip() if h1 else meta.get("title", guidance_id))

    return GuidanceDocument(
        guidance_id=guidance_id,
        version=meta.get("version", "0"),
        title=title,
        sections=sections,
        expected_llm_output_format=expected_format,
        limitations=limitations,
    )


def load_guidance(guidance_id: str) -> GuidanceDocument | ModuleError:
    return _load_cached(guidance_id)


__all__ = ["load_guidance"]
