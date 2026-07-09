"""Brave Search API provider (default).

Structured search API — no HTML scraping (the legacy DuckDuckGo scraping path
is retired, PRD §7.3 / Appendix A.9).
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

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider:
    """Web search via the Brave Search API."""

    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        if not api_key:
            raise SearchConfigError("Brave search selected but SEARCH_API_KEY is not set")
        self._api_key = api_key
        self._timeout = timeout

    def _build_query(self, query: str, site: str | None) -> str:
        query = query.strip()
        if site:
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
            "count": max(1, min(max_results, 20)),
            "result_filter": "web",
        }
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(_BRAVE_ENDPOINT, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise SearchTimeoutError(f"Brave search timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(f"Brave search request failed: {exc}") from exc

        if response.status_code == 401:
            raise SearchConfigError("Brave search rejected the API key (401)")
        if response.status_code == 429:
            raise SearchProviderError("Brave search rate limit exceeded (429)")
        if response.status_code >= 400:
            raise SearchProviderError(f"Brave search returned HTTP {response.status_code}: {response.text[:200]}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise SearchProviderError("Brave search returned non-JSON response") from exc

        web_results = (payload.get("web") or {}).get("results") or []
        results: list[SearchResult] = []
        for item in web_results[:max_results]:
            url = item.get("url")
            title = item.get("title")
            if not url or not title:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=item.get("description", "") or "",
                )
            )
        return results
