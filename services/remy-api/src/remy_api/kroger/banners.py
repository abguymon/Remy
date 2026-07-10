"""Kroger banner → cart-handoff URL mapping (single source of truth).

Kroger operates many regional banners (Fred Meyer, QFC, Ralphs, King Soopers,
Fry's, Smith's, Dillons, City Market, Harris Teeter, …), each with its own
website and its own ``/cart`` page. The Kroger Locations API returns a ``chain``
code per store; we persist it on the user's settings and use it to hand the user
off to the *right* banner's cart at checkout, rather than always kroger.com.

``banner_cart_url`` is the one place that mapping lives. It matches on the chain
code first (exact, punctuation/space-insensitive) and falls back to fuzzy
store-name matching (e.g. "Fred Meyer - Eagle Island"). Anything unknown degrades
to the generic kroger.com cart — never a wrong banner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DEFAULT_CART_URL = "https://www.kroger.com/cart"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class _Banner:
    url: str
    # Chain codes as returned by the Locations API, normalized (lowercase, no
    # separators). Matched by equality against the normalized input.
    chains: frozenset[str] = field(default_factory=frozenset)
    # Substrings matched against a normalized store name (fuzzy fallback).
    name_keywords: tuple[str, ...] = ()


# Ordered by specificity so a fuzzy name match never grabs a more generic banner
# before a specific one. Chain codes mirror Kroger's Locations API ``chain``.
_BANNERS: tuple[_Banner, ...] = (
    _Banner("https://www.fredmeyer.com/cart", frozenset({"fred", "fredmeyer"}), ("fredmeyer",)),
    _Banner("https://www.qfc.com/cart", frozenset({"qfc"}), ("qfc", "qualityfood")),
    _Banner("https://www.ralphs.com/cart", frozenset({"ralphs"}), ("ralphs",)),
    _Banner("https://www.kingsoopers.com/cart", frozenset({"kingsoopers"}), ("kingsoopers",)),
    _Banner("https://www.frysfood.com/cart", frozenset({"frys", "frysfood"}), ("frys",)),
    _Banner("https://www.smithsfoodanddrug.com/cart", frozenset({"smiths"}), ("smiths",)),
    _Banner("https://www.dillons.com/cart", frozenset({"dillons"}), ("dillons",)),
    _Banner("https://www.citymarket.com/cart", frozenset({"citymarket"}), ("citymarket",)),
    _Banner("https://www.harristeeter.com/cart", frozenset({"harristeeter"}), ("harristeeter",)),
    _Banner("https://www.kroger.com/cart", frozenset({"kroger"}), ("kroger",)),
)


def _normalize(value: str) -> str:
    """Lowercase and strip everything but alphanumerics for a stable match key."""
    return _NON_ALNUM.sub("", value.lower())


def banner_cart_url(chain_or_name: str | None) -> str:
    """Map a Kroger ``chain`` code (or a store name) to its cart-handoff URL.

    Matches the chain code exactly first, then falls back to fuzzy name matching.
    Returns :data:`DEFAULT_CART_URL` (kroger.com) for empty or unknown input —
    handing off to the generic Kroger cart is always safe, a wrong banner is not.
    """
    if not chain_or_name:
        return DEFAULT_CART_URL
    normalized = _normalize(chain_or_name)
    if not normalized:
        return DEFAULT_CART_URL
    # 1) Exact chain-code match (e.g. "FRED", "QFC", "KINGSOOPERS").
    for banner in _BANNERS:
        if normalized in banner.chains:
            return banner.url
    # 2) Fuzzy store-name match (e.g. "Fred Meyer - Eagle Island" → fredmeyer).
    for banner in _BANNERS:
        if any(keyword in normalized for keyword in banner.name_keywords):
            return banner.url
    return DEFAULT_CART_URL
