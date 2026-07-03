"""Environment-backed configuration, limits, and feature flags.

`config` is a low-level module: it must not import pipelines. Secrets are read from
the environment only and are never logged or returned in tool output. Missing
required secrets surface as a `CONFIG_MISSING` ModuleError rather than an exception
at import time, so the server can still boot and report the problem per-tool.
"""

from __future__ import annotations

import os
from pathlib import Path

from .errors import ErrorCode, ModuleError, module_error


def load_env_file(path: str | os.PathLike | None = None) -> list[str]:
    """Load a local `.env` into os.environ for keys that are not already set.

    Dependency-free. Real/process or platform-injected environment variables always
    win (we never override an existing value), so this is safe in production where
    PlayMCP/KakaoCloud injects secrets and no `.env` file is present. Returns the
    names of the keys that were loaded (names only — values are never logged).
    """
    if path is not None:
        env_path: Path | None = Path(path)
    else:
        env_path = None
        for base in (Path.cwd(), *Path.cwd().parents):
            candidate = base / ".env"
            if candidate.is_file():
                env_path = candidate
                break
    if env_path is None or not env_path.is_file():
        return []

    loaded: list[str] = []
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded

# Required secrets (see docs/INTER_MODULE_INTERFACES.md §5.5).
REQUIRED_SECRETS: tuple[str, ...] = ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")

# Numeric/string limits with safe defaults applied when the env var is unset.
_LIMIT_DEFAULTS: dict[str, float] = {
    "MAX_DOCUMENT_CHARS": 200_000,
    "MAX_TOOL_RESPONSE_CHARS": 24_000,  # hard PlayMCP ceiling
    # Overall external-call budget. Advisory only (used as HTTP read timeout, not a
    # hard wall-clock), and shared across a tool's calls: citation makes up to N
    # Crossref calls and plagiarism splits this across up to NAVER_MAX_QUERIES Naver
    # calls, so 3s was far too tight from a datacenter (Crossref/Naver timed out).
    "DEFAULT_TIMEOUT_MS": 15_000,
    "NAVER_MAX_QUERIES": 12,  # ~covers a 1000-1500 char report with 2-sentence chunks
    "NAVER_MAX_DISPLAY": 10,  # per query; Naver hard max is 100
    "NAVER_SIMILARITY_THRESHOLD": 0.6,
    "SPELLCHECK_MAX_UNITS": 60,
    "CITATION_MAX_TITLES": 30,
    "RATE_LIMIT_WINDOW_MS": 1_000,
    "RATE_LIMIT_MAX_COST": 50,
}

_STRING_DEFAULTS: dict[str, str] = {
    "DEFAULT_LANGUAGE": "auto",
    "HOST": "0.0.0.0",
    "PORT": "8080",
    "ALLOWED_ORIGINS": "",
    "SPELLCHECK_PROVIDER": "composite",
}

# Feature flags default to False unless the env value is a truthy token.
_TRUTHY = {"1", "true", "yes", "on"}


def get_required_secret(name: str) -> str | ModuleError:
    value = os.environ.get(name)
    if not value:
        return module_error(
            ErrorCode.CONFIG_MISSING,
            f"Required configuration '{name}' is not set.",
            module="config",
            field=name,
        )
    return value


def get_optional_secret(name: str) -> str | None:
    value = os.environ.get(name)
    return value or None


def get_kci_api_key() -> str | None:
    """KCI (Korea Citation Index) Open API key from the environment (never hardcoded).

    Used to verify Korean-journal citations; when unset, the citation pipeline falls
    back to Naver web search for Korean titles. Never logged or returned.
    """
    value = os.environ.get("KCI_API_KEY")
    return value.strip() if value and value.strip() else None


def get_s2_api_key() -> str | None:
    """Semantic Scholar API key from the environment (never hardcoded).

    Optional: lookups work keyless on the shared public pool, but a key gives a
    dedicated rate limit so citation checks stay reliable under load. Never logged
    or returned.
    """
    value = os.environ.get("S2_API_KEY")
    return value.strip() if value and value.strip() else None


def get_user_email() -> str | None:
    """Crossref polite-pool email read from the environment (never hardcoded).

    Pipelines fall back to this when the caller does not pass `user_email`, so the
    host never has to prompt for an email. The value is used only as a Crossref
    `mailto` and is never logged or returned in tool output.
    """
    value = os.environ.get("USER_EMAIL")
    return value.strip() if value and value.strip() else None


def get_limit(name: str) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        if name not in _LIMIT_DEFAULTS:
            raise KeyError(f"Unknown limit '{name}'")
        return _LIMIT_DEFAULTS[name]
    try:
        return float(raw)
    except ValueError:
        # Misconfigured env var falls back to the documented default rather than
        # crashing the process.
        return _LIMIT_DEFAULTS.get(name, 0.0)


def get_int_limit(name: str) -> int:
    return int(get_limit(name))


def get_string(name: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return _STRING_DEFAULTS.get(name, "")
    return raw


def get_feature_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def missing_required_secrets() -> list[str]:
    """Names of required secrets that are unset — for health/diagnostics only."""
    return [name for name in REQUIRED_SECRETS if not os.environ.get(name)]


__all__ = [
    "REQUIRED_SECRETS",
    "load_env_file",
    "get_required_secret",
    "get_optional_secret",
    "get_user_email",
    "get_kci_api_key",
    "get_limit",
    "get_int_limit",
    "get_string",
    "get_feature_flag",
    "missing_required_secrets",
]
