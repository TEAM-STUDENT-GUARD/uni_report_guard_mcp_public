"""KCI (Korea Citation Index) Open API client — Korean-journal citation lookup.

Queries KCI's `articleSearch` endpoint by title and returns normalized article
metadata (title, journal, year, DOI, URL, authors). The auth key comes from config
(env only, never logged). Applies SSRF validation, connect/read timeouts, normalizes
failures, and retries transient errors. Must not import pipelines/transport.

Endpoint (per the KCI Open API guide):
  GET https://open.kci.go.kr/po/openapi/openApiSearch.kci
      ?apiCode=articleSearch&key=<KEY>&title=<TITLE>&displayCount=<N>
Response is XML: MetaData/outputData/record[]/{journalInfo, articleInfo}.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import httpx
from pydantic import BaseModel

from .. import logging as rg_logging
from ..errors import ErrorCode, ModuleError, module_error
from ..retry import with_retries
from ..schemas import Status
from ..security import validate_outbound_url

_BASE_URL = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"
_PROVIDER = "kci"


class KciArticle(BaseModel):
    title: str
    title_english: str | None = None
    journal: str | None = None
    publication_year: int | None = None
    doi: str | None = None
    url: str | None = None
    authors: list[str] = []


class KciSearchResponse(BaseModel):
    status: Status
    articles: list[KciArticle] = []
    errors: list[ModuleError] = []
    http_status: int | None = None


def _err(code: ErrorCode, message: str, *, retryable: bool = False,
         http_status: int | None = None) -> KciSearchResponse:
    return KciSearchResponse(
        status=Status.EXTERNAL_ERROR,
        http_status=http_status,
        errors=[module_error(code, message, module="clients/kci", retryable=retryable,
                             provider=_PROVIDER, http_status=http_status)],
    )


def _is_retryable(resp: KciSearchResponse) -> bool:
    return resp.status is Status.EXTERNAL_ERROR and any(e.retryable for e in resp.errors)


def _text(el) -> str | None:
    return el.text.strip() if el is not None and el.text and el.text.strip() else None


# KCI returns DOIs as resolver URLs (e.g. "http://dx.doi.org/10.24173/..."); strip the
# prefix to a bare DOI so it displays consistently with Crossref.
_DOI_URL_RE = re.compile(r"(?i)^\s*(?:https?://)?(?:dx\.)?doi\.org/")


def _normalize_doi(raw: str | None) -> str | None:
    if not raw:
        return None
    doi = _DOI_URL_RE.sub("", raw.strip())
    return doi or None


def _parse(xml_text: str) -> list[KciArticle] | None:
    """Parse the KCI XML into articles; None signals an unparseable/error body."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    out: list[KciArticle] = []
    for rec in root.findall(".//record"):
        ai = rec.find("articleInfo")
        if ai is None:
            continue
        titles = {t.get("lang"): (t.text or "").strip()
                  for t in ai.findall("./title-group/article-title")}
        title = titles.get("original") or titles.get("english") or titles.get("foreign") or ""
        if not title:
            continue
        ji = rec.find("journalInfo")
        year = None
        py = _text(ji.find("pub-year")) if ji is not None else None
        if py and py.isdigit():
            year = int(py)
        authors = [a.text.strip() for a in ai.findall("./author-group/author")
                   if a.text and a.text.strip()]
        out.append(KciArticle(
            title=title,
            title_english=titles.get("english") or None,
            journal=_text(ji.find("journal-name")) if ji is not None else None,
            publication_year=year,
            doi=_normalize_doi(_text(ai.find("doi"))),
            url=_text(ai.find("url")),
            authors=authors[:10],
        ))
    return out


def search_by_title(title: str, api_key: str, deadline_ms: int = 3000,
                    display_count: int = 10) -> KciSearchResponse:
    """Search KCI articles by title, retrying transient failures."""
    return with_retries(
        lambda: _search_by_title_once(title, api_key, deadline_ms, display_count),
        _is_retryable,
    )


def _search_by_title_once(title: str, api_key: str, deadline_ms: int,
                          display_count: int) -> KciSearchResponse:
    params = {
        "apiCode": "articleSearch",
        "key": api_key,
        "title": title,
        "displayCount": str(max(1, min(display_count, 100))),
    }
    ssrf = validate_outbound_url(str(httpx.URL(_BASE_URL, params=params)), "kci")
    if ssrf is not None:
        return KciSearchResponse(status=Status.EXTERNAL_ERROR, errors=[ssrf])

    timeout = httpx.Timeout(connect=1.5, read=deadline_ms / 1000.0, write=1.5, pool=1.5)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.get(_BASE_URL, params=params, headers={"User-Agent": "ReportGuard/0.1"})
    except httpx.TimeoutException:
        return _err(ErrorCode.PROVIDER_TIMEOUT, "KCI request timed out.", retryable=True)
    except httpx.HTTPError:
        return _err(ErrorCode.PROVIDER_UNAVAILABLE, "KCI could not be reached.", retryable=True)

    # Log only non-sensitive fields (never the key or the query text).
    rg_logging.log_event("info", "kci_call", {"provider_name": _PROVIDER, "http_status": resp.status_code})

    if resp.status_code == 429:
        return _err(ErrorCode.EXTERNAL_RATE_LIMITED, "KCI rate limited the request.",
                    retryable=True, http_status=429)
    if resp.status_code >= 500:
        return _err(ErrorCode.EXTERNAL_BAD_RESPONSE, "KCI returned a server error.",
                    retryable=True, http_status=resp.status_code)
    if resp.status_code != 200:
        return _err(ErrorCode.EXTERNAL_BAD_RESPONSE, "KCI returned an unexpected response.",
                    http_status=resp.status_code)

    articles = _parse(resp.text)
    if articles is None:
        # A non-XML body usually means an API error (e.g. invalid/expired key).
        return _err(ErrorCode.EXTERNAL_BAD_RESPONSE, "KCI response could not be parsed.",
                    http_status=200)
    return KciSearchResponse(status=Status.OK, articles=articles, http_status=200)


__all__ = ["KciArticle", "KciSearchResponse", "search_by_title"]
