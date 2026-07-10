"""Self-hosted SearXNG search provider (default recommended).

SearXNG is a privacy-respecting metasearch engine you run yourself (a container
in this repo's compose stack). It has no API key: it aggregates results from
upstream engines and exposes them via a JSON API. This provider talks to that
JSON API — no HTML scraping.

The JSON format must be enabled in the SearXNG instance's ``settings.yml``
(``search.formats: [html, json]``) or the ``/search`` endpoint returns HTTP 403.
See ``searxng/settings.yml`` in the repo root and the README.
"""

from __future__ import annotations

import logging

import httpx

from remy_api.search.base import (
    SearchConfigError,
    SearchProviderError,
    SearchResult,
    SearchTimeoutError,
)

logger = logging.getLogger(__name__)


class SearxngSearchProvider:
    """Web search via a self-hosted SearXNG instance's JSON API."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        if not base_url:
            raise SearchConfigError("SearXNG search selected but SEARXNG_URL is not set")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _build_query(self, query: str, site: str | None) -> str:
        query = query.strip()
        if site:
            # SearXNG passes ``site:`` through to its upstream engines, which
            # honor it (Google, DuckDuckGo, Brave, etc.).
            return f"{query} site:{site.strip()}"
        return query

    async def search(
        self,
        query: str,
        site: str | None = None,
        max_results: int = 10,
    ) -> list[SearchResult]:
        params = {
            "q": self._build_query(query, site),
            "format": "json",
            "safesearch": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base_url}/search", params=params)
        except httpx.TimeoutException as exc:
            raise SearchTimeoutError(f"SearXNG search timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(f"SearXNG search request failed: {exc}") from exc

        if response.status_code == 403:
            raise SearchProviderError(
                "SearXNG returned HTTP 403 — the JSON format is likely disabled. "
                "Set search.formats: [html, json] in the instance settings.yml."
            )
        if response.status_code >= 400:
            raise SearchProviderError(f"SearXNG search returned HTTP {response.status_code}: {response.text[:200]}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise SearchProviderError("SearXNG search returned non-JSON response") from exc

        raw_results = payload.get("results") or []
        results: list[SearchResult] = []
        for item in raw_results[:max_results]:
            url = item.get("url")
            title = item.get("title")
            if not url or not title:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=item.get("content", "") or "",
                )
            )
        return results
