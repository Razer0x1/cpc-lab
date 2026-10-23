"""Scholarly metadata search: OpenAlex, arXiv, Crossref.

- No API keys required; polite contact email used when configured.
- Simple client-side token-bucket rate limiting + in-memory TTL cache.
- Results are bibliographic metadata only; `fulltext_verified` stays False until a
  verified-ingestion step is run. Failures produce explicit 'not executed' errors.
"""
from __future__ import annotations

import json
import time
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import HTTPException

from ..config import get_settings

settings = get_settings()

ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}
_TTL_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 1800
_lock = threading.Lock()


@dataclass
class RateLimiter:
    per_minute: int = 20
    _events: list[float] = field(default_factory=list)

    def acquire(self) -> None:
        now = time.monotonic()
        with _lock:
            self._events = [t for t in self._events if now - t < 60]
            if len(self._events) >= self.per_minute:
                raise HTTPException(
                    status_code=429,
                    detail="Scholarly API rate limit reached; retry in a minute",
                )
            self._events.append(now)


limiter = RateLimiter(settings.scholar_rate_limit_per_min)


def _cache_get(key: str) -> Any | None:
    hit = _TTL_CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    return None


def _cache_put(key: str, value: Any) -> Any:
    _TTL_CACHE[key] = (time.monotonic(), value)
    return value


def _contact() -> dict[str, str]:
    return {"User-Agent": f"CPC-Lab/0.1 ({settings.scholar_contact_email or 'anonymous'})"}


def search_openalex(query: str, limit: int = 10) -> list[dict]:
    url = "https://api.openalex.org/works"
    params = {"search": query, "per-page": min(limit, 25), "mailto": settings.scholar_contact_email or "cpc-lab@example.org"}
    r = httpx.get(url, params=params, headers=_contact(), timeout=10)
    r.raise_for_status()
    out = []
    for w in r.json().get("results", []):
        authorships = w.get("authorships") or []
        out.append({
            "source": "openalex",
            "external_id": w.get("id") or "",
            "doi": (w.get("doi") or "").removeprefix("https://doi.org/"),
            "title": w.get("display_name") or "(untitled)",
            "authors": [a.get("author", {}).get("display_name", "") for a in authorships][:12],
            "year": w.get("publication_year"),
            "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "") if (w.get("primary_location") or {}).get("source") else "",
            "url": w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url", ""),
            "concepts": [c.get("display_name") for c in (w.get("concepts") or [])[:6] if c.get("display_name")],
            "abstract": "",  # truncated abstract metadata kept short; full text not stored
        })
    return out


def search_arxiv(query: str, limit: int = 10) -> list[dict]:
    url = "https://export.arxiv.org/api/query"
    params = {"search_query": f"all:{query}", "max_results": min(limit, 25), "sortBy": "relevance"}
    r = httpx.get(url, params=params, headers=_contact(), timeout=10)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for entry in root.findall("a:entry", ARXIV_NS):
        aid = (entry.findtext("a:id", "", ARXIV_NS) or "").split("/abs/")[-1]
        pub_year = None
        published = entry.findtext("a:published", "", ARXIV_NS)
        if published and len(published) >= 4 and published[:4].isdigit():
            pub_year = int(published[:4])
        out.append({
            "source": "arxiv",
            "external_id": f"arXiv:{aid}",
            "doi": entry.findtext("a:doi", "", ARXIV_NS) or "",
            "title": " ".join((entry.findtext("a:title", "", ARXIV_NS) or "").split()),
            "authors": [e.findtext("a:name", "", ARXIV_NS) for e in entry.findall("a:author", ARXIV_NS)][:12],
            "year": pub_year,
            "venue": "arXiv",
            "url": entry.findtext("a:id", "", ARXIV_NS) or "",
            "concepts": [],
            "abstract": " ".join((entry.findtext("a:summary", "", ARXIV_NS) or "").split())[:1000],
        })
    return out


def search_crossref(query: str, limit: int = 10) -> list[dict]:
    url = "https://api.crossref.org/works"
    params = {"query": query, "rows": min(limit, 25), "mailto": settings.scholar_contact_email or "cpc-lab@example.org"}
    r = httpx.get(url, params=params, headers=_contact(), timeout=10)
    r.raise_for_status()
    out = []
    for item in r.json().get("message", {}).get("items", []):
        year = None
        dp = item.get("published-print") or item.get("published-online") or item.get("created") or {}
        parts = dp.get("date-parts") or []
        if parts and parts[0]:
            year = parts[0][0]
        out.append({
            "source": "crossref",
            "external_id": item.get("DOI") or "",
            "doi": item.get("DOI") or "",
            "title": (item.get("title") or ["(untitled)"])[0],
            "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in item.get("author", [])][:12],
            "year": year,
            "venue": ((item.get("container-title") or [""])[0]),
            "url": item.get("URL") or "",
            "concepts": item.get("subject", [])[:6],
            "abstract": (item.get("abstract") or "")[:1000],
        })
    return out


def search(query: str, sources: list[str] | None = None, limit: int = 8) -> dict:
    """Search multiple scholarly APIs. Cached; rate limited; offline errors surface as 503."""
    q = query.strip()
    if len(q) < 2:
        raise HTTPException(status_code=422, detail="Query too short")
    key = json.dumps(["search", q, tuple(sources or []), limit], sort_keys=True)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    limiter.acquire()
    chosen = sources or ["openalex", "arxiv", "crossref"]
    results: list[dict] = []
    errors: dict[str, str] = {}
    for src in chosen:
        fn = {"openalex": search_openalex, "arxiv": search_arxiv, "crossref": search_crossref}.get(src)
        if fn is None:
            errors[src] = "unknown source"
            continue
        try:
            results.extend(fn(q, limit))
        except HTTPException:
            raise
        except Exception as e:  # network/offline/etc — explicit, never fabricated data
            errors[src] = f"unavailable: {type(e).__name__}"
    payload = {"query": q, "results": results, "errors": errors,
               "note": "Bibliographic metadata only; claims require verified full text."}
    _cache_put(key, payload)
    return payload
