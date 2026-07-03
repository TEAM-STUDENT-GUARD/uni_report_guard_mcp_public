"""Online Korean/English spell-check via the free, no-auth Naver speller.

This is the v1 default provider, so `check_document_spelling` ships
`openWorldHint: true` and the pipeline discloses external transmission.

It calls the Naver speller endpoint directly with httpx instead of depending on the
unmaintained `py-hanspell` package (whose legacy setup.py no longer installs). That
also lets the adapter own its outbound safety end-to-end. The adapter:
  - pre-flight validates every Naver host against the SSRF allowlist,
  - sends only the supplied text units (never the whole document at once) as UTF-8,
  - enforces a connect/read timeout and an overall wall-clock deadline,
  - normalizes every failure to PROVIDER_UNAVAILABLE/PROVIDER_TIMEOUT and never
    leaks the raw upstream payload,
  - degrades to a partial/external_error result instead of crashing when the
    unofficial endpoint changes or is unavailable.
"""

from __future__ import annotations

import html
import json
import re
import time

import httpx

from ...errors import ErrorCode, module_error
from ...retry import with_retries
from ...schemas import Confidence, Status, TextLocation
from ...security import validate_outbound_url
from .base import SpellcheckCorrection, SpellcheckProviderResult

_PASSPORT_URL = "https://search.naver.com/search.naver"
_SPELL_URL = "https://m.search.naver.com/p/csearch/ocontent/util/SpellerProxy"
_PROVIDER = "naver_speller"

# Naver limits a single speller request to ~500 characters.
_MAX_UNIT_CHARS = 480
_PASSPORT_RE = re.compile(r"passportKey=([^&\"']+)")

# Cache the scraped passportKey briefly so a batch of units reuses one handshake.
_passport_cache: dict[str, object] = {"key": None, "fetched_at": 0.0}
_PASSPORT_TTL_S = 300.0


def _provider_error(code: ErrorCode, message: str, reason_code: str) -> SpellcheckProviderResult:
    return SpellcheckProviderResult(
        status=Status.EXTERNAL_ERROR,
        provider_name=_PROVIDER,
        errors=[
            module_error(
                code, message, module="providers/spellcheck",
                retryable=True, provider=_PROVIDER, reason_code=reason_code,
            )
        ],
    )


def _fetch_passport_key(client: httpx.Client) -> str | None:
    now = time.monotonic()
    cached = _passport_cache.get("key")
    if cached and now - float(_passport_cache.get("fetched_at", 0.0)) < _PASSPORT_TTL_S:
        return str(cached)
    resp = client.get(
        _PASSPORT_URL,
        params={"where": "nexearch", "sm": "top_hty", "ie": "utf8", "query": "맞춤법검사기"},
        headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko"},
    )
    if resp.status_code != 200:
        return None
    match = _PASSPORT_RE.search(resp.text)
    if not match:
        return None
    key = match.group(1)
    _passport_cache["key"] = key
    _passport_cache["fetched_at"] = now
    return key


def _parse_jsonp(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except ValueError:
        return None


def _corrected_from_payload(payload: dict) -> str | None:
    result = (payload.get("message") or {}).get("result") or {}
    # `notag_html` is the corrected text without highlight markup, but it may still
    # carry HTML entities (e.g. &quot;, &amp;), so decode them to plain characters.
    corrected = result.get("notag_html")
    return html.unescape(corrected) if isinstance(corrected, str) else None


class HanspellProvider:
    """Naver speller adapter (kept class name for the provider registry)."""

    name = _PROVIDER

    def check_text(
        self, units: list[str], language: str, deadline_ms: int
    ) -> SpellcheckProviderResult:
        # Retry only on a total failure (no corrections at all); a partial/timed-out
        # result already has some corrections and must not be re-run.
        def _retryable(r: SpellcheckProviderResult) -> bool:
            return r.status is Status.EXTERNAL_ERROR and not r.corrections

        return with_retries(
            lambda: self._check_text_once(units, language, deadline_ms), _retryable
        )

    def _check_text_once(
        self, units: list[str], language: str, deadline_ms: int
    ) -> SpellcheckProviderResult:
        # SSRF/allowlist pre-flight on both Naver hosts (scheme + host + no metadata).
        for url in (_PASSPORT_URL, _SPELL_URL):
            ssrf = validate_outbound_url(url, "spellcheck")
            if ssrf is not None:
                return SpellcheckProviderResult(
                    status=Status.EXTERNAL_ERROR, provider_name=_PROVIDER, errors=[ssrf]
                )

        deadline_s = max(0.4, deadline_ms / 1000.0)
        started = time.monotonic()
        read_timeout = max(0.5, deadline_s / max(1, len(units) + 1))
        timeout = httpx.Timeout(connect=1.5, read=read_timeout, write=1.5, pool=1.5)

        corrections: list[SpellcheckCorrection] = []
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                passport = _fetch_passport_key(client)
                if not passport:
                    return _provider_error(
                        ErrorCode.PROVIDER_UNAVAILABLE,
                        "The spell-check service handshake failed.",
                        "passport",
                    )

                for idx, unit in enumerate(units):
                    if time.monotonic() - started > deadline_s:
                        return SpellcheckProviderResult(
                            status=Status.PARTIAL if corrections else Status.EXTERNAL_ERROR,
                            provider_name=_PROVIDER,
                            corrections=corrections,
                            timed_out=True,
                            errors=[
                                module_error(
                                    ErrorCode.PROVIDER_TIMEOUT,
                                    "The spell-check service timed out.",
                                    module="providers/spellcheck",
                                    retryable=True,
                                    provider=_PROVIDER,
                                )
                            ],
                        )

                    text = unit[:_MAX_UNIT_CHARS]
                    resp = client.get(
                        _SPELL_URL,
                        params={
                            "passportKey": passport,
                            "where": "nexearch",
                            "color_blindness": "0",
                            "q": text,
                            "_callback": "cb",
                        },
                        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://search.naver.com/"},
                    )
                    if resp.status_code != 200:
                        # Stale passport or endpoint change — drop cache and stop.
                        _passport_cache["key"] = None
                        return SpellcheckProviderResult(
                            status=Status.PARTIAL if corrections else Status.EXTERNAL_ERROR,
                            provider_name=_PROVIDER,
                            corrections=corrections,
                            errors=[
                                module_error(
                                    ErrorCode.EXTERNAL_BAD_RESPONSE,
                                    "The spell-check service returned an unexpected response.",
                                    module="providers/spellcheck",
                                    retryable=True,
                                    provider=_PROVIDER,
                                    http_status=resp.status_code,
                                )
                            ],
                        )

                    payload = _parse_jsonp(resp.text)
                    if payload is None:
                        continue
                    corrected = _corrected_from_payload(payload)
                    if corrected and corrected != text:
                        corrections.append(
                            SpellcheckCorrection(
                                original=text,
                                corrected=corrected,
                                location=TextLocation(sentence_index=idx),
                                confidence=Confidence.MEDIUM,
                            )
                        )
        except httpx.TimeoutException:
            return SpellcheckProviderResult(
                status=Status.PARTIAL if corrections else Status.EXTERNAL_ERROR,
                provider_name=_PROVIDER,
                corrections=corrections,
                timed_out=True,
                errors=[
                    module_error(
                        ErrorCode.PROVIDER_TIMEOUT,
                        "The spell-check service timed out.",
                        module="providers/spellcheck",
                        retryable=True,
                        provider=_PROVIDER,
                    )
                ],
            )
        except httpx.HTTPError:
            return _provider_error(
                ErrorCode.PROVIDER_UNAVAILABLE,
                "The spell-check service could not be reached.",
                "http_error",
            )
        except Exception:  # noqa: BLE001 — never leak raw provider internals
            return _provider_error(
                ErrorCode.PROVIDER_UNAVAILABLE,
                "The spell-check service is temporarily unavailable.",
                "provider_exception",
            )

        status = Status.OK if corrections else Status.NO_FINDINGS
        return SpellcheckProviderResult(
            status=status, provider_name=_PROVIDER, corrections=corrections
        )


__all__ = ["HanspellProvider"]
