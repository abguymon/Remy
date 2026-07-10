"""Search-provider factory, selected by settings.search_provider (PRD §7.3)."""

from __future__ import annotations

from remy_api.providers.settings import ProviderSettings, get_provider_settings
from remy_api.search.base import SearchConfigError, SearchProvider
from remy_api.search.brave import BraveSearchProvider
from remy_api.search.llm_provider import LLMSearchProvider
from remy_api.search.searxng import SearxngSearchProvider


def get_search_provider(settings: ProviderSettings | None = None) -> SearchProvider:
    """Build the configured search provider.

    Raises:
        SearchConfigError: unknown provider name or missing required config.
    """
    settings = settings or get_provider_settings()
    name = (settings.search_provider or "").strip().lower()

    if name == "brave":
        return BraveSearchProvider(api_key=settings.search_api_key, timeout=settings.search_timeout)
    if name == "llm":
        return LLMSearchProvider(model=settings.llm_model, timeout=settings.search_timeout)
    if name == "searxng":
        if not (settings.searxng_url or "").strip():
            raise SearchConfigError("SEARCH_PROVIDER=searxng but SEARXNG_URL is not set")
        return SearxngSearchProvider(base_url=settings.searxng_url, timeout=settings.search_timeout)

    raise SearchConfigError(
        f"Unknown SEARCH_PROVIDER '{settings.search_provider}'; expected 'brave', 'llm', or 'searxng'"
    )
