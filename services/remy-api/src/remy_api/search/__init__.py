"""Pluggable web search + thumbnail fetching (T4)."""

from remy_api.search.base import (
    SearchConfigError,
    SearchError,
    SearchProvider,
    SearchProviderError,
    SearchResult,
    SearchTimeoutError,
)
from remy_api.search.brave import BraveSearchProvider
from remy_api.search.factory import get_search_provider
from remy_api.search.llm_provider import LLMSearchProvider
from remy_api.search.searxng import SearxngSearchProvider
from remy_api.search.thumbnails import fetch_og_image, fetch_thumbnails

__all__ = [
    "SearchResult",
    "SearchProvider",
    "SearchError",
    "SearchConfigError",
    "SearchProviderError",
    "SearchTimeoutError",
    "BraveSearchProvider",
    "LLMSearchProvider",
    "SearxngSearchProvider",
    "get_search_provider",
    "fetch_og_image",
    "fetch_thumbnails",
]
