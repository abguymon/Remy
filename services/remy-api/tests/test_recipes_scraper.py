"""Scraper tests (offline): schema.org fixtures + typed-error fallback path."""

from pathlib import Path

import httpx
import pytest

from remy_api.recipes.llm_fallback import RecipeParseError
from remy_api.recipes.schemas import LLMRecipeExtraction, ParsedRecipe
from remy_api.recipes.scraper import (
    extract_page_text,
    fetch_page,
    parse_with_scrapers,
    scrape_recipe,
)

FIXTURES = Path(__file__).parent / "fixtures" / "recipes"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_clean_schema_hummus():
    parsed = parse_with_scrapers(_read("clean_schema_hummus.html"), "https://cookieandkate.com/best-hummus-recipe/")
    assert parsed.is_complete()
    assert "Hummus" in parsed.title
    assert len(parsed.ingredients) >= 5
    assert len(parsed.instructions) >= 3
    assert parsed.total_time  # times normalized
    assert parsed.image_url


def test_parse_clean_schema_tacos():
    parsed = parse_with_scrapers(_read("clean_schema_tacos.html"), "https://example.com/tacos")
    assert parsed.is_complete()
    assert parsed.title == "Weeknight Street Tacos"
    assert len(parsed.ingredients) == 6
    assert len(parsed.instructions) == 4
    assert parsed.recipe_yield == "4 servings"
    assert parsed.prep_time == "15 min"
    assert parsed.total_time == "35 min"
    # Raw lines are retained; parsed components stay null (P4a parses later).
    assert parsed.ingredients[0].raw.startswith("1 lb flank steak")
    assert parsed.ingredients[0].food is None


def test_messy_page_reports_incomplete():
    """A page with no recipe schema must not silently yield a partial recipe."""
    with pytest.raises(Exception):  # noqa: B017 - library raises; scrape_recipe wraps it
        parse_with_scrapers(_read("messy_no_schema.html"), "https://example.com/salmon")


async def test_scrape_recipe_fallback_skipped_raises_typed_error(monkeypatch):
    """With no LLM wired, an unparseable page raises a typed RecipeParseError."""

    async def fake_fetch(url, *, client=None):
        return _read("messy_no_schema.html")

    monkeypatch.setattr("remy_api.recipes.scraper.fetch_page", fake_fetch)
    with pytest.raises(RecipeParseError) as excinfo:
        await scrape_recipe("https://example.com/salmon", llm=None)
    reasons = excinfo.value.reasons
    assert "llm_unavailable" in reasons
    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "recipe_parse_failed"


async def test_scrape_recipe_uses_llm_fallback_when_wired(monkeypatch):
    """When a client is wired, an unparseable page routes to the LLM fallback."""

    async def fake_fetch(url, *, client=None):
        return _read("messy_no_schema.html")

    monkeypatch.setattr("remy_api.recipes.scraper.fetch_page", fake_fetch)

    class FakeLLM:
        async def structured(self, prompt_id, input, schema):  # noqa: A002
            assert prompt_id == "recipe_parse_fallback"
            assert "page_text" in input
            return LLMRecipeExtraction(
                found=True,
                title="Grandma's Salmon Bowls",
                ingredients=["1 salmon fillet", "1 cup rice", "1 avocado"],
                instructions=["Cook salmon.", "Make rice.", "Assemble."],
            )

    parsed = await scrape_recipe("https://example.com/salmon", llm=FakeLLM())
    assert isinstance(parsed, ParsedRecipe)
    assert parsed.title == "Grandma's Salmon Bowls"
    assert len(parsed.ingredients) == 3
    assert parsed.source_url == "https://example.com/salmon"


async def test_fetch_page_http_error_is_typed():
    def handler(request):
        return httpx.Response(404, text="nope")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RecipeParseError) as excinfo:
            await fetch_page("https://example.com/missing", client=client)
    assert "http_404" in excinfo.value.reasons


def test_extract_page_text_strips_scripts():
    text = extract_page_text(
        "<html><head><style>x{}</style></head><body><p>Hello</p><script>bad()</script></body></html>"
    )
    assert "Hello" in text
    assert "bad()" not in text
    assert "x{}" not in text


async def test_fetch_page_403_falls_back_to_curl_cffi(monkeypatch):
    """A bot-wall 403 from httpx must escalate to the curl_cffi impersonation
    fallback rather than becoming a typed error."""
    called = {}

    async def fake_impersonated_get(url, *, headers, timeout, max_bytes=None):
        called["url"] = url
        return 200, b"<html><body>impersonated ok</body></html>", "text/html"

    monkeypatch.setattr("remy_api.recipes.scraper.impersonated_get", fake_impersonated_get)

    def handler(request):
        return httpx.Response(403, text="blocked")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        html = await fetch_page("https://www.seriouseats.com/blocked", client=client)
    assert "impersonated ok" in html
    assert called["url"] == "https://www.seriouseats.com/blocked"


async def test_fetch_page_200_skips_curl_cffi(monkeypatch):
    """The common 200 path must never touch the heavy curl_cffi fallback."""

    async def boom(*args, **kwargs):
        raise AssertionError("curl_cffi fallback must not run on a 200 response")

    monkeypatch.setattr("remy_api.recipes.scraper.impersonated_get", boom)

    def handler(request):
        return httpx.Response(200, text="<html><body>direct ok</body></html>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        html = await fetch_page("https://example.com/ok", client=client)
    assert "direct ok" in html


async def test_fetch_page_impersonation_403_is_typed(monkeypatch):
    """If curl_cffi is also blocked, surface a typed http_403 (no silent fail)."""

    async def fake_impersonated_get(url, *, headers, timeout, max_bytes=None):
        return 403, b"still blocked", "text/html"

    monkeypatch.setattr("remy_api.recipes.scraper.impersonated_get", fake_impersonated_get)

    def handler(request):
        return httpx.Response(403, text="blocked")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RecipeParseError) as excinfo:
            await fetch_page("https://www.seriouseats.com/blocked", client=client)
    assert "http_403" in excinfo.value.reasons
