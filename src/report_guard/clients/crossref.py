"""Crossref REST API client (isolated outbound boundary).

Queries Crossref works by title, optionally in the polite pool via `mailto`.
Applies a fixed base URL, SSRF/allowlist validation, connect/read timeouts, and
normalizes 429/5xx/network failures. Returns only cleaned metadata — never the raw
upstream body. Must not import pipelines/transport/orchestrator.
"""

from __future__ import annotations

import re
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from .. import logging as rg_logging
from ..errors import ErrorCode, ModuleError, module_error
from ..retry import with_retries
from ..schemas import CrossrefWorkSummary, Status
from ..security import validate_outbound_url


def _is_retryable(resp: "CrossrefSearchResponse") -> bool:
    return resp.status is Status.EXTERNAL_ERROR and any(e.retryable for e in resp.errors)

_BASE_URL = "https://api.crossref.org/works"
_USER_AGENT = "ReportGuard/0.1 (mailto-optional; +https://playmcp.example)"


class CrossrefSearchRequest(BaseModel):
    query_title: str
    mailto: str | None = None
    rows: int = 3
    deadline_ms: int = 3000


class CrossrefSearchResponse(BaseModel):
    status: Status
    works: list[CrossrefWorkSummary] = []
    errors: list[ModuleError] = []
    http_status: int | None = None


_DOI_URL_PREFIX = re.compile(r"(?i)^\s*(?:https?://)?(?:dx\.)?doi\.org/")


def _doi_err(code: ErrorCode, message: str, *, retryable: bool = False,
             http_status: int | None = None) -> CrossrefSearchResponse:
    return CrossrefSearchResponse(
        status=Status.EXTERNAL_ERROR,
        http_status=http_status,
        errors=[
            module_error(code, message, module="clients/crossref",
                         retryable=retryable, provider="crossref", http_status=http_status)
        ],
    )


def fetch_by_doi(doi: str, mailto: str | None = None,
                 deadline_ms: int = 3000) -> CrossrefSearchResponse:
    """Resolve a single DOI via Crossref, retrying transient failures."""
    return with_retries(
        lambda: _fetch_by_doi_once(doi, mailto, deadline_ms), _is_retryable
    )


def _fetch_by_doi_once(doi: str, mailto: str | None,
                       deadline_ms: int) -> CrossrefSearchResponse:
    """Resolve a single DOI via Crossref's /works/{doi} endpoint.

    A 404 (DOI not registered in Crossref) is NOT an error — it returns status OK
    with an empty `works` list so the caller can distinguish "DOI does not resolve"
    (likely a citation typo) from an external failure.
    """
    doi = _DOI_URL_PREFIX.sub("", doi or "").strip().rstrip(".,);]")
    if not doi:
        return _doi_err(ErrorCode.INTERNAL_ERROR, "Empty DOI.")
    url = f"{_BASE_URL}/{quote(doi, safe='')}"
    params = {"mailto": mailto} if mailto else {}

    ssrf = validate_outbound_url(str(httpx.URL(url, params=params)), "crossref")
    if ssrf is not None:
        return CrossrefSearchResponse(status=Status.EXTERNAL_ERROR, errors=[ssrf])

    timeout = httpx.Timeout(connect=1.5, read=deadline_ms / 1000.0, write=1.5, pool=1.5)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.get(url, params=params, headers={"User-Agent": _USER_AGENT})
    except httpx.TimeoutException:
        return _doi_err(ErrorCode.PROVIDER_TIMEOUT, "Crossref request timed out.", retryable=True)
    except httpx.HTTPError:
        return _doi_err(ErrorCode.PROVIDER_UNAVAILABLE, "Crossref could not be reached.", retryable=True)

    rg_logging.log_event(
        "info", "crossref_call", {"provider_name": "crossref", "http_status": resp.status_code}
    )

    if resp.status_code == 404:
        return CrossrefSearchResponse(status=Status.OK, works=[], http_status=404)
    if resp.status_code == 429:
        return _doi_err(ErrorCode.EXTERNAL_RATE_LIMITED, "Crossref rate limited the request.",
                        retryable=True, http_status=429)
    if resp.status_code >= 500:
        return _doi_err(ErrorCode.EXTERNAL_BAD_RESPONSE, "Crossref returned a server error.",
                        retryable=True, http_status=resp.status_code)
    if resp.status_code != 200:
        return _doi_err(ErrorCode.EXTERNAL_BAD_RESPONSE, "Crossref returned an unexpected response.",
                        http_status=resp.status_code)

    try:
        message = resp.json().get("message") or {}
    except ValueError:
        return _doi_err(ErrorCode.EXTERNAL_BAD_RESPONSE, "Crossref response could not be parsed.",
                        http_status=resp.status_code)

    works = [_normalize_work(message)] if message.get("DOI") or message.get("title") else []
    return CrossrefSearchResponse(status=Status.OK, works=works, http_status=200)


def _normalize_work(item: dict) -> CrossrefWorkSummary:
    titles = item.get("title") or []
    title = titles[0] if titles else "(untitled)"
    authors = []
    for a in item.get("author", []) or []:
        name = " ".join(p for p in [a.get("given"), a.get("family")] if p).strip()
        if name:
            authors.append(name)
    year = None
    issued = (item.get("issued") or {}).get("date-parts") or []
    if issued and issued[0]:
        year = issued[0][0]
    score = item.get("score")
    cited_by = item.get("is-referenced-by-count")
    return CrossrefWorkSummary(
        title=title,
        doi=item.get("DOI"),
        publisher=item.get("publisher"),
        publication_year=year if isinstance(year, int) else None,
        authors=authors[:10],
        url=item.get("URL"),
        match_score=float(score) if isinstance(score, (int, float)) else None,
        cited_by_count=int(cited_by) if isinstance(cited_by, int) else None,
    )


def search_work(req: CrossrefSearchRequest) -> CrossrefSearchResponse:
    """Query Crossref works by title, retrying transient failures."""
    return with_retries(lambda: _search_work_once(req), _is_retryable)


def _search_work_once(req: CrossrefSearchRequest) -> CrossrefSearchResponse:
    rows = max(1, min(req.rows, 5))
    # `query.title` ranks exact-title matches far better than `query.bibliographic`
    # for well-known papers (e.g. ResNet/U-Net surface as the top hit). `select`
    # trims the response to the fields we normalize, which measurably cuts Crossref
    # latency; `is-referenced-by-count` disambiguates same-titled records.
    params = {
        "query.title": req.query_title,
        "rows": str(rows),
        "select": "DOI,title,author,issued,publisher,URL,score,is-referenced-by-count",
    }
    if req.mailto:
        params["mailto"] = req.mailto  # polite pool; mailto used here only

    # Build URL for SSRF validation (host allowlist + scheme + no metadata IPs).
    url = str(httpx.URL(_BASE_URL, params=params))
    ssrf = validate_outbound_url(url, "crossref")
    if ssrf is not None:
        return CrossrefSearchResponse(status=Status.EXTERNAL_ERROR, errors=[ssrf])

    timeout = httpx.Timeout(connect=1.5, read=req.deadline_ms / 1000.0, write=1.5, pool=1.5)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.get(
                _BASE_URL, params=params, headers={"User-Agent": _USER_AGENT}
            )
    except httpx.TimeoutException:
        return CrossrefSearchResponse(
            status=Status.EXTERNAL_ERROR,
            errors=[
                module_error(
                    ErrorCode.PROVIDER_TIMEOUT,
                    "Crossref request timed out.",
                    module="clients/crossref",
                    retryable=True,
                    provider="crossref",
                )
            ],
        )
    except httpx.HTTPError:
        return CrossrefSearchResponse(
            status=Status.EXTERNAL_ERROR,
            errors=[
                module_error(
                    ErrorCode.PROVIDER_UNAVAILABLE,
                    "Crossref could not be reached.",
                    module="clients/crossref",
                    retryable=True,
                    provider="crossref",
                )
            ],
        )

    rg_logging.log_event(
        "info",
        "crossref_call",
        {"provider_name": "crossref", "http_status": resp.status_code},
    )

    if resp.status_code == 429:
        return CrossrefSearchResponse(
            status=Status.EXTERNAL_ERROR,
            http_status=429,
            errors=[
                module_error(
                    ErrorCode.EXTERNAL_RATE_LIMITED,
                    "Crossref rate limited the request.",
                    module="clients/crossref",
                    retryable=True,
                    provider="crossref",
                    http_status=429,
                )
            ],
        )
    if resp.status_code >= 500:
        return CrossrefSearchResponse(
            status=Status.EXTERNAL_ERROR,
            http_status=resp.status_code,
            errors=[
                module_error(
                    ErrorCode.EXTERNAL_BAD_RESPONSE,
                    "Crossref returned a server error.",
                    module="clients/crossref",
                    retryable=True,
                    provider="crossref",
                    http_status=resp.status_code,
                )
            ],
        )
    if resp.status_code != 200:
        return CrossrefSearchResponse(
            status=Status.EXTERNAL_ERROR,
            http_status=resp.status_code,
            errors=[
                module_error(
                    ErrorCode.EXTERNAL_BAD_RESPONSE,
                    "Crossref returned an unexpected response.",
                    module="clients/crossref",
                    provider="crossref",
                    http_status=resp.status_code,
                )
            ],
        )

    try:
        items = (resp.json().get("message") or {}).get("items") or []
    except ValueError:
        return CrossrefSearchResponse(
            status=Status.EXTERNAL_ERROR,
            http_status=resp.status_code,
            errors=[
                module_error(
                    ErrorCode.EXTERNAL_BAD_RESPONSE,
                    "Crossref response could not be parsed.",
                    module="clients/crossref",
                    provider="crossref",
                )
            ],
        )

    works = [_normalize_work(it) for it in items[:rows]]
    return CrossrefSearchResponse(
        status=Status.OK, works=works, http_status=resp.status_code
    )


__all__ = ["CrossrefSearchRequest", "CrossrefSearchResponse", "search_work", "fetch_by_doi"]
