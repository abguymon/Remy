"""Shared HTTP fetch helpers with a ``curl_cffi`` TLS-impersonation fallback.

Some sites (e.g. seriouseats.com) return 403 to plain ``httpx`` even with a
browser ``User-Agent`` because they fingerprint the TLS/JA3 handshake, not just
the header. ``curl_cffi`` can impersonate a real Chrome handshake and get
through. It is heavier than ``httpx``, so it is used strictly as a *fallback*:
the common path stays lightweight ``httpx`` and only bot-walled responses
escalate to impersonation.

Both the recipe scraper (page fetch) and the og:image thumbnail fetcher share
:func:`impersonated_get` so the fallback lives in exactly one place.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Response statuses that typically signal a bot wall / TLS-fingerprint rejection
# (worth retrying with impersonation) rather than a genuine client/not-found
# error. 403 is the seriouseats case; 406/429/503 are common Cloudflare/WAF
# responses to non-browser clients.
BLOCKED_STATUSES = frozenset({403, 406, 429, 503})


async def impersonated_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float,
    max_bytes: int | None = None,
) -> tuple[int, bytes, str]:
    """GET ``url`` with ``curl_cffi`` impersonating Chrome.

    Returns ``(status_code, content, content_type)``. When ``max_bytes`` is
    given, ``content`` is truncated to ``max_bytes + 1`` bytes so callers can
    still detect an over-cap response. Raises on transport failure — the caller
    decides whether that becomes a typed error or a ``None`` degraded result.

    ``curl_cffi`` is imported lazily so it is only loaded on the fallback path.
    """
    from curl_cffi import AsyncSession  # lazy: heavy, fallback-only

    async with AsyncSession() as session:
        resp = await session.get(
            url,
            headers=headers,
            timeout=timeout,
            impersonate="chrome",
            allow_redirects=True,
        )
        content = resp.content
        if max_bytes is not None:
            content = content[: max_bytes + 1]
        ctype = resp.headers.get("content-type", "") or ""
        return resp.status_code, content, ctype
