"""Web-search provider contract and typed errors (PRD §7.3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """A single web-search hit."""

    title: str
    url: str
    snippet: str = ""


@runtime_checkable
class SearchProvider(Protocol):
    """Pluggable web-search backend.

    Implementations must raise :class:`SearchError` subclasses on failure — never
    return an empty list to mask an error (PRD §9.1). An empty list means the
    query genuinely had no results.
    """

    async def search(
        self,
        query: str,
        site: str | None = None,
        max_results: int = 10,
    ) -> list[SearchResult]:
        """Run a search, optionally restricted to a single ``site`` domain."""
        ...


class SearchError(Exception):
    """Base class for web-search failures."""


class SearchConfigError(SearchError):
    """Misconfiguration (missing API key, unsupported provider)."""


class SearchProviderError(SearchError):
    """The provider returned an error or unparseable response."""


class SearchTimeoutError(SearchError):
    """The provider did not respond within the configured timeout."""


class _ResultsEnvelope(BaseModel):
    """Internal helper for validating LLM-native search output."""

    results: list[SearchResult] = Field(default_factory=list)
