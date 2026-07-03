"""Input sanitization, secret redaction, and SSRF-safe outbound URL policy.

Low-level module: no pipeline imports. This is the single choke point for
outbound-URL safety and for scrubbing sensitive values before they reach logs or
tool output.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit

from . import config
from .errors import ErrorCode, ModuleError, module_error

# --- Outbound allowlist ----------------------------------------------------
# Only these hosts may be contacted. Anything else (and any private/loopback/
# link-local/metadata address) is rejected before a request is made.
_ALLOWLISTS: dict[str, frozenset[str]] = {
    "crossref": frozenset({"api.crossref.org"}),
    "semantic_scholar": frozenset({"api.semanticscholar.org"}),
    "naver_search": frozenset({"openapi.naver.com"}),
    "kci": frozenset({"open.kci.go.kr"}),
    # hanspell talks to the Naver speller endpoint.
    "spellcheck": frozenset({"m.search.naver.com", "search.naver.com"}),
}

_BLOCKED_METADATA_HOSTS: frozenset[str] = frozenset(
    {"metadata.google.internal", "169.254.169.254"}
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Patterns redacted from any string before logging / error surfacing.
_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[redacted-email]"),
    (re.compile(r"(?i)(client[_-]?secret|api[_-]?key|token|password)\s*[=:]\s*\S+"),
     r"\1=[redacted]"),
)


def validate_document_size(document_text: str) -> ModuleError | None:
    """Return a ModuleError if the document exceeds the configured char limit."""
    max_chars = config.get_int_limit("MAX_DOCUMENT_CHARS")
    if len(document_text) > max_chars:
        return module_error(
            ErrorCode.DOCUMENT_TOO_LARGE,
            "Document exceeds the maximum supported length.",
            module="security",
            limit=max_chars,
            actual=len(document_text),
        )
    return None


def sanitize_user_text(text: str) -> str:
    """Normalize control characters without altering meaningful content.

    Strips NULs and most C0 control chars (keeps tab/newline/carriage return) so
    downstream processing and JSON serialization stay well-formed. This does NOT
    rewrite words — spelling/meaning is preserved.
    """
    if not text:
        return ""
    cleaned = text.replace("\x00", "")
    return "".join(
        ch for ch in cleaned if ch in ("\t", "\n", "\r") or ord(ch) >= 0x20
    )


def redact_sensitive(value: object) -> str:
    """Best-effort scrub of emails/secret-like tokens from a string for logging."""
    text = value if isinstance(value, str) else repr(value)
    for pattern, repl in _REDACTION_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def validate_email_for_mailto(user_email: str) -> ModuleError | None:
    """Validate that an email is shaped acceptably for a Crossref `mailto`."""
    email = (user_email or "").strip()
    if not email or not _EMAIL_RE.match(email) or len(email) > 254:
        return module_error(
            ErrorCode.INVALID_INPUT,
            "Provided email is not a valid address for polite-pool requests.",
            module="security",
            field="user_email",
        )
    return None


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_outbound_url(url: str, policy_name: str) -> ModuleError | None:
    """SSRF-safe outbound URL check against a named allowlist policy.

    Enforces https, an allowlisted host, blocks metadata hosts, and resolves the
    host to ensure it does not point at a private/loopback/link-local address.
    """
    allowed_hosts = _ALLOWLISTS.get(policy_name)
    if allowed_hosts is None:
        return module_error(
            ErrorCode.INTERNAL_ERROR,
            "Unknown outbound policy.",
            module="security",
            reason_code="unknown_policy",
        )

    parts = urlsplit(url)
    if parts.scheme != "https":
        return module_error(
            ErrorCode.INVALID_INPUT,
            "Outbound requests must use HTTPS.",
            module="security",
            reason_code="scheme",
        )

    host = (parts.hostname or "").lower()
    if not host or host in _BLOCKED_METADATA_HOSTS:
        return module_error(
            ErrorCode.INVALID_INPUT,
            "Outbound host is not permitted.",
            module="security",
            reason_code="blocked_host",
        )
    if host not in allowed_hosts:
        return module_error(
            ErrorCode.INVALID_INPUT,
            "Outbound host is not on the allowlist.",
            module="security",
            reason_code="not_allowlisted",
        )

    # Resolve and reject private / loopback / link-local / metadata targets.
    try:
        infos = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return module_error(
            ErrorCode.PROVIDER_UNAVAILABLE,
            "Outbound host could not be resolved.",
            module="security",
            reason_code="dns",
        )
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if str(ip) in _BLOCKED_METADATA_HOSTS or _is_blocked_ip(ip):
            return module_error(
                ErrorCode.INVALID_INPUT,
                "Outbound host resolves to a blocked address.",
                module="security",
                reason_code="blocked_ip",
            )
    return None


def allowlisted_hosts(policy_name: str) -> frozenset[str]:
    return _ALLOWLISTS.get(policy_name, frozenset())


__all__ = [
    "validate_document_size",
    "sanitize_user_text",
    "redact_sensitive",
    "validate_email_for_mailto",
    "validate_outbound_url",
    "allowlisted_hosts",
]
