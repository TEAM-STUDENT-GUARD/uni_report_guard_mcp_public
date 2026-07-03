"""Slice 1 — privacy/SSRF/validation tests for the security module."""

from __future__ import annotations

from report_guard import security
from report_guard.errors import ErrorCode


def test_redact_sensitive_strips_email_and_secret():
    text = "contact a.student@univ.ac.kr with NAVER_CLIENT_SECRET=abc123def"
    out = security.redact_sensitive(text)
    assert "a.student@univ.ac.kr" not in out
    assert "abc123def" not in out
    assert "[redacted-email]" in out


def test_validate_email_for_mailto_accepts_valid():
    assert security.validate_email_for_mailto("user@example.com") is None


def test_validate_email_for_mailto_rejects_invalid():
    err = security.validate_email_for_mailto("not-an-email")
    assert err is not None and err.code is ErrorCode.INVALID_INPUT


def test_validate_outbound_url_blocks_non_https():
    err = security.validate_outbound_url("http://api.crossref.org/works", "crossref")
    assert err is not None


def test_validate_outbound_url_blocks_non_allowlisted_host():
    err = security.validate_outbound_url("https://evil.example.com/x", "crossref")
    assert err is not None and err.code is ErrorCode.INVALID_INPUT


def test_validate_outbound_url_blocks_metadata_host():
    err = security.validate_outbound_url("https://169.254.169.254/latest", "naver_search")
    assert err is not None


def test_validate_outbound_url_allows_allowlisted_host():
    # api.crossref.org is allowlisted and public; resolution should pass.
    err = security.validate_outbound_url("https://api.crossref.org/works?query=x", "crossref")
    assert err is None


def test_sanitize_user_text_preserves_meaning_strips_nul():
    out = security.sanitize_user_text("hello\x00 world\tline\nbreak")
    assert out == "hello world\tline\nbreak"


def test_validate_document_size_rejects_oversize(monkeypatch):
    monkeypatch.setenv("MAX_DOCUMENT_CHARS", "10")
    err = security.validate_document_size("x" * 11)
    assert err is not None and err.code is ErrorCode.DOCUMENT_TOO_LARGE
