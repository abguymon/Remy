"""Keyless unit tests for the og:image thumbnail fetcher."""

from __future__ import annotations

import httpx

from remy_api.search import thumbnails

_HTML_OG = """
<html><head>
<meta property="og:image" content="https://cdn.example.com/pic.jpg">
<title>Recipe</title>
</head><body>...</body></html>
"""

_HTML_TWITTER = """
<html><head>
<meta name="twitter:image" content="https://cdn.example.com/tw.jpg">
</head><body></body></html>
"""

_HTML_NONE = "<html><head><title>no image</title></head><body></body></html>"


def _extract(html: str):
    return thumbnails._extract_image(html)


def test_extract_og_image():
    assert _extract(_HTML_OG) == "https://cdn.example.com/pic.jpg"


def test_extract_twitter_fallback():
    assert _extract(_HTML_TWITTER) == "https://cdn.example.com/tw.jpg"


def test_extract_none_when_absent():
    assert _extract(_HTML_NONE) is None


async def _fetch(monkeypatch, handler, url="https://site.test/recipe"):
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "remy_api.search.thumbnails.httpx.AsyncClient",
        lambda *a, **k: real_client(*a, transport=transport, **k),
    )
    return await thumbnails.fetch_og_image(url)


async def test_fetch_og_image_success(monkeypatch):
    def handler(request):
        return httpx.Response(200, text=_HTML_OG, headers={"content-type": "text/html"})

    assert await _fetch(monkeypatch, handler) == "https://cdn.example.com/pic.jpg"


async def test_fetch_returns_none_on_404(monkeypatch):
    def handler(request):
        return httpx.Response(404, text="nope")

    assert await _fetch(monkeypatch, handler) is None


async def test_fetch_returns_none_on_error_never_raises(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("boom")

    assert await _fetch(monkeypatch, handler) is None


async def test_fetch_skips_non_html(monkeypatch):
    def handler(request):
        return httpx.Response(200, content=b"\xff\xd8\xff", headers={"content-type": "image/jpeg"})

    assert await _fetch(monkeypatch, handler) is None


async def test_fetch_thumbnails_batch_dedups_and_maps(monkeypatch):
    def handler(request):
        return httpx.Response(200, text=_HTML_OG, headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "remy_api.search.thumbnails.httpx.AsyncClient",
        lambda *a, **k: real_client(*a, transport=transport, **k),
    )
    urls = ["https://a.test/1", "https://a.test/1", "https://b.test/2", ""]
    out = await thumbnails.fetch_thumbnails(urls)
    assert set(out.keys()) == {"https://a.test/1", "https://b.test/2"}
    assert all(v == "https://cdn.example.com/pic.jpg" for v in out.values())
