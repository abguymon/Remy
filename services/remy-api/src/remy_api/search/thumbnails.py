"""og:image thumbnail fetcher.

Thumbnails are cosmetic (PRD §7.3): a failure for one URL returns ``None`` and
never raises or blocks. Uses a real HTML parser (selectolax) rather than the
legacy regex-over-raw-HTML approach (Appendix A.9), with a bounded streaming
read through the document head, a short per-URL timeout, and bounded
concurrency across a batch.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from selectolax.parser import HTMLParser

from remy_api.net import BLOCKED_STATUSES, impersonated_get

logger = logging.getLogger(__name__)

# Some recipe sites inject enough scripts and styles ahead of their social meta
# tags to push og:image beyond 200KB. Read through </head> when possible, while
# retaining a hard ceiling for malformed pages that never close their head.
_MAX_HEAD_BYTES = 1_000_000
_TIMEOUT = 5.0
_CONCURRENCY = 8
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Meta tags that carry a preview image, in priority order.
_IMAGE_META = (
    ("property", "og:image"),
    ("property", "og:image:url"),
    ("name", "twitter:image"),
    ("name", "twitter:image:src"),
)


def _extract_image(html: str) -> str | None:
    tree = HTMLParser(html)
    for attr, value in _IMAGE_META:
        node = tree.css_first(f'meta[{attr}="{value}"]')
        if node:
            content = node.attributes.get("content")
            if content:
                return content.strip()
    return None


def _decode_head(content: bytes) -> str:
    """Decode only the HTML head from a bounded response prefix."""
    lowered = content.lower()
    head_start = lowered.find(b"</head")
    if head_start >= 0:
        head_end = lowered.find(b">", head_start)
        if head_end >= 0:
            content = content[: head_end + 1]
    return content.decode("utf-8", errors="ignore")


async def fetch_og_image(
    url: str,
    client: httpx.AsyncClient | None = None,
    timeout: float = _TIMEOUT,
) -> str | None:
    """Return the og:image (or twitter:image) URL for ``url``, or ``None``.

    Never raises: any network/parse failure yields ``None``.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=_HEADERS)
    try:
        async with client.stream("GET", url, headers=_HEADERS) as response:
            # Bot-walled hosts 403 plain httpx despite the browser UA (TLS
            # fingerprinting). Retry via curl_cffi impersonation; still cosmetic,
            # so any failure there falls through to None.
            if response.status_code in BLOCKED_STATUSES:
                return await _fetch_og_image_impersonated(url, timeout)
            if response.status_code != 200:
                return None
            ctype = response.headers.get("content-type", "")
            if ctype and "html" not in ctype.lower():
                return None

            buf = bytearray()
            async for chunk in response.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > _MAX_HEAD_BYTES:
                    del buf[_MAX_HEAD_BYTES:]
                if b"</head" in buf.lower() or len(buf) >= _MAX_HEAD_BYTES:
                    break
            return _extract_image(_decode_head(bytes(buf)))
    except Exception as exc:  # noqa: BLE001 - cosmetic; log at debug and move on
        logger.debug("og:image fetch failed for %s: %s", url, exc)
        return None
    finally:
        if owns_client:
            await client.aclose()


async def _fetch_og_image_impersonated(url: str, timeout: float) -> str | None:
    """curl_cffi fallback for og:image, keeping the bounded head read."""
    try:
        status, content, ctype = await impersonated_get(
            url, headers=_HEADERS, timeout=timeout, max_bytes=_MAX_HEAD_BYTES
        )
    except Exception as exc:  # noqa: BLE001 - cosmetic; log at debug and move on
        logger.debug("og:image impersonated fetch failed for %s: %s", url, exc)
        return None
    if status != 200:
        return None
    if ctype and "html" not in ctype.lower():
        return None
    return _extract_image(_decode_head(content))


async def fetch_thumbnails(urls: list[str], concurrency: int = _CONCURRENCY) -> dict[str, str | None]:
    """Fetch og:image for many URLs with bounded concurrency.

    Returns a ``{url: image_url | None}`` map. De-duplicates input URLs.
    """
    unique = list(dict.fromkeys(u for u in urls if u))
    if not unique:
        return {}

    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(follow_redirects=True, timeout=_TIMEOUT, headers=_HEADERS) as client:

        async def _one(u: str) -> tuple[str, str | None]:
            async with sem:
                return u, await fetch_og_image(u, client=client)

        pairs = await asyncio.gather(*(_one(u) for u in unique))

    return dict(pairs)
