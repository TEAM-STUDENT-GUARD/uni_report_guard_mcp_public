"""Slice 1 — config defaults, secrets, and feature flags."""

from __future__ import annotations

from report_guard import config
from report_guard.errors import ErrorCode


def test_get_limit_default_when_unset(monkeypatch):
    monkeypatch.delenv("MAX_TOOL_RESPONSE_CHARS", raising=False)
    assert config.get_limit("MAX_TOOL_RESPONSE_CHARS") == 24_000


def test_get_limit_reads_env(monkeypatch):
    monkeypatch.setenv("NAVER_MAX_QUERIES", "3")
    assert config.get_int_limit("NAVER_MAX_QUERIES") == 3


def test_get_limit_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("DEFAULT_TIMEOUT_MS", "not-a-number")
    assert config.get_limit("DEFAULT_TIMEOUT_MS") == 15_000


def test_required_secret_missing_returns_module_error(monkeypatch):
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    result = config.get_required_secret("NAVER_CLIENT_ID")
    assert isinstance(result, type(config.get_required_secret("NAVER_CLIENT_ID")))
    assert getattr(result, "code", None) is ErrorCode.CONFIG_MISSING


def test_required_secret_present(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "abc")
    assert config.get_required_secret("NAVER_CLIENT_ID") == "abc"


def test_feature_flag_truthy(monkeypatch):
    monkeypatch.setenv("SOME_FLAG", "true")
    assert config.get_feature_flag("SOME_FLAG") is True
    monkeypatch.setenv("SOME_FLAG", "0")
    assert config.get_feature_flag("SOME_FLAG") is False


def test_missing_required_secrets(monkeypatch):
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    assert set(config.missing_required_secrets()) == {"NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"}
