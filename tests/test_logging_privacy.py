"""Slice 1 — logging field whitelist + redaction, and ModuleError detail scrubbing."""

from __future__ import annotations

import json
import logging

from report_guard import logging as rg_logging
from report_guard.errors import ErrorCode, module_error


def _capture(caplog):
    return [r.getMessage() for r in caplog.records]


def test_log_event_drops_forbidden_fields(caplog):
    with caplog.at_level(logging.INFO, logger="report_guard"):
        rg_logging.log_event(
            "info",
            "tool_call",
            {
                "tool_name": "count_document_units",
                "status": "ok",
                "document_text": "SECRET ESSAY BODY",  # forbidden
                "user_email": "a@b.com",  # forbidden
                "NAVER_CLIENT_SECRET": "shh",  # forbidden
            },
        )
    line = _capture(caplog)[-1]
    payload = json.loads(line)
    assert payload["tool_name"] == "count_document_units"
    assert "document_text" not in line
    assert "SECRET ESSAY BODY" not in line
    assert "a@b.com" not in line
    assert "shh" not in line


def test_log_event_redacts_allowed_field_values(caplog):
    with caplog.at_level(logging.INFO, logger="report_guard"):
        # request_id is allowed but should still be redaction-scrubbed.
        rg_logging.log_event("info", "evt", {"request_id": "id-user@x.com-1"})
    line = _capture(caplog)[-1]
    assert "user@x.com" not in line


def test_module_error_drops_non_allowlisted_details():
    err = module_error(
        ErrorCode.EXTERNAL_BAD_RESPONSE,
        "Upstream failed.",
        module="clients/naver_search",
        http_status=500,
        raw_body="<html>secret tokens</html>",  # not allowlisted
    )
    safe = err.safe_details()
    assert safe == {"http_status": 500}
    assert "raw_body" not in safe
