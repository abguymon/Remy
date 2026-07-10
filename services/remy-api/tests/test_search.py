"""Keyless unit tests for search providers, factory, and error typing."""

from __future__ import annotations

import httpx
import pytest

from remy_api.providers.settings import ProviderSettings
from remy_api.search import (
    BraveSearchProvider,
    LLMSearchProvider,
    SearchConfigError,
    SearchProvider,
    SearchProviderError,
    SearchResult,
    SearxngSearchProvider,
    get_search_provider,
)

_BRAVE_PAYLOAD = {
    "web": {
        "results": [
            {"title": "Easy Tacos", "url": "https://x.com/tacos", "description": "yum"},
            {"title": "Taco Night", "url": "https://y.com/night", "description": ""},
            {"title": "no url here"},
        ]
    }
}


def _brave_with_transport(handler) -> BraveSearchProvider:
    provider = BraveSearchProvider(api_key="k", timeout=5)
    # Patch the client construction by monkeypatching httpx.AsyncClient at call site
    return provider


async def _run_brave(monkeypatch, handler) -> list[SearchResult]:
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("remy_api.search.brave.httpx.AsyncClient", factory)
    return await BraveSearchProvider(api_key="k", timeout=5).search("tacos", max_results=10)


async def test_brave_parses_results(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Subscription-Token"] == "k"
        return httpx.Response(200, json=_BRAVE_PAYLOAD)

    results = await _run_brave(monkeypatch, handler)
    assert [r.url for r in results] == ["https://x.com/tacos", "https://y.com/night"]
    assert results[0].snippet == "yum"


async def test_brave_site_restriction(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["q"] = request.url.params.get("q")
        return httpx.Response(200, json={"web": {"results": []}})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "remy_api.search.brave.httpx.AsyncClient",
        lambda *a, **k: real_client(*a, transport=transport, **k),
    )
    await BraveSearchProvider(api_key="k").search("tacos", site="seriouseats.com")
    assert "site:seriouseats.com" in seen["q"]


async def test_brave_401_is_config_error(monkeypatch):
    def handler(request):
        return httpx.Response(401, text="bad key")

    with pytest.raises(SearchConfigError):
        await _run_brave(monkeypatch, handler)


async def test_brave_500_is_provider_error(monkeypatch):
    def handler(request):
        return httpx.Response(500, text="oops")

    with pytest.raises(SearchProviderError):
        await _run_brave(monkeypatch, handler)


def test_brave_requires_key():
    with pytest.raises(SearchConfigError):
        BraveSearchProvider(api_key="")


def test_factory_brave():
    s = ProviderSettings(search_provider="brave", search_api_key="k")
    provider = get_search_provider(s)
    assert isinstance(provider, BraveSearchProvider)
    assert isinstance(provider, SearchProvider)  # runtime_checkable protocol


def test_factory_llm():
    s = ProviderSettings(search_provider="llm", llm_model="anthropic/claude-sonnet-4-5")
    assert isinstance(get_search_provider(s), LLMSearchProvider)


def test_factory_unknown_provider():
    s = ProviderSettings(search_provider="bing")
    with pytest.raises(SearchConfigError):
        get_search_provider(s)


def test_llm_provider_rejects_unsupported_model():
    with pytest.raises(SearchConfigError):
        LLMSearchProvider(model="mistral/mistral-large")


def test_llm_provider_detects_supported():
    assert LLMSearchProvider(model="anthropic/claude-sonnet-4-5")._provider == "anthropic"
    assert LLMSearchProvider(model="openai/gpt-4o")._provider == "openai"


# --- SearXNG ---

_SEARXNG_PAYLOAD = {
    "results": [
        {"title": "Easy Tacos", "url": "https://x.com/tacos", "content": "yum"},
        {"title": "Taco Night", "url": "https://y.com/night", "content": ""},
        {"title": "no url here"},
    ]
}


async def _run_searxng(monkeypatch, handler, **search_kwargs) -> list[SearchResult]:
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "remy_api.search.searxng.httpx.AsyncClient",
        lambda *a, **k: real_client(*a, transport=transport, **k),
    )
    return await SearxngSearchProvider(base_url="http://searxng:8080", timeout=5).search("tacos", **search_kwargs)


async def test_searxng_parses_results(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("format") == "json"
        assert request.url.params.get("safesearch") == "1"
        assert request.url.path == "/search"
        return httpx.Response(200, json=_SEARXNG_PAYLOAD)

    results = await _run_searxng(monkeypatch, handler, max_results=10)
    assert [r.url for r in results] == ["https://x.com/tacos", "https://y.com/night"]
    assert results[0].snippet == "yum"


async def test_searxng_site_restriction(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["q"] = request.url.params.get("q")
        return httpx.Response(200, json={"results": []})

    await _run_searxng(monkeypatch, handler, site="budgetbytes.com")
    assert "site:budgetbytes.com" in seen["q"]


async def test_searxng_max_results_truncation(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SEARXNG_PAYLOAD)

    results = await _run_searxng(monkeypatch, handler, max_results=1)
    assert len(results) == 1
    assert results[0].url == "https://x.com/tacos"


async def test_searxng_403_is_provider_error(monkeypatch):
    def handler(request):
        return httpx.Response(403, text="forbidden")

    with pytest.raises(SearchProviderError):
        await _run_searxng(monkeypatch, handler)


async def test_searxng_500_is_provider_error(monkeypatch):
    def handler(request):
        return httpx.Response(500, text="oops")

    with pytest.raises(SearchProviderError):
        await _run_searxng(monkeypatch, handler)


def test_searxng_requires_url():
    with pytest.raises(SearchConfigError):
        SearxngSearchProvider(base_url="")


def test_factory_searxng():
    s = ProviderSettings(search_provider="searxng", searxng_url="http://searxng:8080")
    provider = get_search_provider(s)
    assert isinstance(provider, SearxngSearchProvider)
    assert isinstance(provider, SearchProvider)  # runtime_checkable protocol


def test_factory_searxng_missing_url():
    s = ProviderSettings(search_provider="searxng", searxng_url="")
    with pytest.raises(SearchConfigError):
        get_search_provider(s)
