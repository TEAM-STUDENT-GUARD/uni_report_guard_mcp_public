"""Semantic Scholar Graph API client — English-paper title match lookup.

Uses the `/graph/v1/paper/search/match` endpoint, which returns the single best
title match for a query. It indexes the CS/AI literature that Crossref covers
poorly (NeurIPS/CVPR proceedings, arXiv preprints), so it is the primary source
for confirming well-known English papers; Crossref remains the fallback.

Free and keyless (shared public rate pool). A 404 from the match endpoint means
"no title match" and is returned as OK with no paper — only transport/5xx/429
failures are errors. Applies SSRF validation, timeouts, and retry on transient
failures. Must not import pipelines/transport.
"""

from __future__ import annotations

import threading
import time

import httpx
from pydantic import BaseModel

from .. import config
from .. import logging as rg_logging
from ..errors import ErrorCode, ModuleError, module_error
from ..retry import with_retries
from ..schemas import Status
from ..security import validate_outbound_url

_BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search/match"
_FIELDS = "title,year,venue,citationCount,externalIds,authors"
_PROVIDER = "semantic_scholar"
_USER_AGENT = "ReportGuard/0.1"


class S2Paper(BaseModel):
    title: str
    year: int | None = None
    venue: str | None = None
    citation_count: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    authors: list[str] = []


class S2MatchResponse(BaseModel):
    status: Status
    paper: S2Paper | None = None
    errors: list[ModuleError] = []
    http_status: int | None = None


def _err(code: ErrorCode, message: str, *, retryable: bool = False,
         http_status: int | None = None) -> S2MatchResponse:
    return S2MatchResponse(
        status=Status.EXTERNAL_ERROR,
        http_status=http_status,
        errors=[module_error(code, message, module="clients/semantic_scholar",
                             retryable=retryable, provider=_PROVIDER,
                             http_status=http_status)],
    )


def _is_retryable(resp: S2MatchResponse) -> bool:
    return resp.status is Status.EXTERNAL_ERROR and any(e.retryable for e in resp.errors)


def _parse_paper(item: dict) -> S2Paper | None:
    title = (item.get("title") or "").strip()
    if not title:
        return None
    ext = item.get("externalIds") or {}
    paper_id = item.get("paperId") or ""
    authors = [a.get("name", "").strip() for a in item.get("authors") or []
               if a.get("name", "").strip()]
    year = item.get("year")
    cited = item.get("citationCount")
    return S2Paper(
        title=title,
        year=year if isinstance(year, int) else None,
        venue=(item.get("venue") or "").strip() or None,
        citation_count=cited if isinstance(cited, int) else None,
        doi=(ext.get("DOI") or "").strip() or None,
        arxiv_id=(str(ext.get("ArXiv") or "")).strip() or None,
        url=f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else None,
        authors=authors[:10],
    )


# The keyless shared pool rejects concurrent bursts with 429, so space request
# starts ~1s apart across threads (the citation pipeline fans out per title).
_MIN_INTERVAL_S = 1.0
_pace_lock = threading.Lock()
_last_start = 0.0


def _pace() -> None:
    global _last_start
    with _pace_lock:
        wait = _last_start + _MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_start = time.monotonic()


def match_title(title: str, deadline_ms: int = 5000) -> S2MatchResponse:
    """Find the best Semantic Scholar title match, retrying transient failures."""
    return with_retries(lambda: _match_title_once(title, deadline_ms), _is_retryable)


def _match_title_once(title: str, deadline_ms: int) -> S2MatchResponse:
    _pace()
    params = {"query": title, "fields": _FIELDS}
    ssrf = validate_outbound_url(str(httpx.URL(_BASE_URL, params=params)), _PROVIDER)
    if ssrf is not None:
        return S2MatchResponse(status=Status.EXTERNAL_ERROR, errors=[ssrf])

    # An API key (optional) moves us off the shared keyless pool onto a dedicated
    # rate limit; the key is sent only in this header and never logged.
    headers = {"User-Agent": _USER_AGENT}
    api_key = config.get_s2_api_key()
    if api_key:
        headers["x-api-key"] = api_key

    timeout = httpx.Timeout(connect=1.5, read=deadline_ms / 1000.0, write=1.5, pool=1.5)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.get(_BASE_URL, params=params, headers=headers)
    except httpx.TimeoutException:
        return _err(ErrorCode.PROVIDER_TIMEOUT, "Semantic Scholar request timed out.",
                    retryable=True)
    except httpx.HTTPError:
        return _err(ErrorCode.PROVIDER_UNAVAILABLE, "Semantic Scholar could not be reached.",
                    retryable=True)

    # Log only non-sensitive fields (never the query text).
    rg_logging.log_event("info", "semantic_scholar_call",
                         {"provider_name": _PROVIDER, "http_status": resp.status_code})

    if resp.status_code == 404:
        # The match endpoint 404s when no paper matches the title — not an error.
        return S2MatchResponse(status=Status.OK, paper=None, http_status=404)
    if resp.status_code == 429:
        return _err(ErrorCode.EXTERNAL_RATE_LIMITED, "Semantic Scholar rate limited the request.",
                    retryable=True, http_status=429)
    if resp.status_code >= 500:
        return _err(ErrorCode.EXTERNAL_BAD_RESPONSE, "Semantic Scholar returned a server error.",
                    retryable=True, http_status=resp.status_code)
    if resp.status_code != 200:
        return _err(ErrorCode.EXTERNAL_BAD_RESPONSE, "Semantic Scholar returned an unexpected response.",
                    http_status=resp.status_code)

    try:
        data = (resp.json().get("data") or [])
    except ValueError:
        return _err(ErrorCode.EXTERNAL_BAD_RESPONSE, "Semantic Scholar response could not be parsed.",
                    http_status=200)

    paper = _parse_paper(data[0]) if data else None
    return S2MatchResponse(status=Status.OK, paper=paper, http_status=200)


__all__ = ["S2Paper", "S2MatchResponse", "match_title"]
