"""Deterministic stock/fulfillment-aware product selection (Appendix A.8).

Runs on P5's ranked output (best-first) plus each candidate product's stock and
fulfillment flags. Ported from the legacy ``_process_cart_item`` walk, but as
pure code operating on typed models and with the A.8 improvement: distinguish
``substituted`` (a different product than the top pick was chosen) from
``stock_unknown`` (the top pick was kept but has no stock data). ``not_found`` is
returned when nothing is acceptable so the review UI can offer manual search.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from remy_api.kroger.models import Product, StockLevel


class MatchStatus(enum.StrEnum):
    MATCHED = "matched"  # top-ranked pick, confirmed in stock
    SUBSTITUTED = "substituted"  # a different (lower-ranked) product was chosen
    STOCK_UNKNOWN = "stock_unknown"  # top pick kept, but no stock signal
    NOT_FOUND = "not_found"  # nothing acceptable / all out of stock


# Explicit, actionable stock levels (the legacy "HIGH/LOW/MEDIUM" set).
_CONFIRMED_STOCK = {StockLevel.HIGH, StockLevel.MEDIUM, StockLevel.LOW}


@dataclass
class Selection:
    status: MatchStatus
    chosen: Product | None
    alternatives: list[Product]


def _fulfillment_ok(product: Product, fulfillment: str | None) -> bool:
    """Whether ``product`` is available for the requested fulfillment modality.

    Mirrors the legacy "not explicitly unavailable" leniency: when Kroger omits
    fulfillment data entirely (all flags false after normalization) we don't
    disqualify the product; when it reports *some* modality we require the
    requested one.
    """
    if fulfillment not in ("pickup", "delivery"):
        return True
    has_any = product.pickup or product.delivery or product.instore
    if not has_any:
        return True  # no fulfillment data at all — don't exclude
    return product.pickup if fulfillment == "pickup" else product.delivery


def select_product(
    ranked_products: list[Product],
    *,
    fulfillment: str | None = None,
) -> Selection:
    """Walk ``ranked_products`` (best-first) and pick the best obtainable one.

    Order of preference:

    1. The first fulfillment-eligible product with a confirmed stock level. If it
       is the top-ranked product -> ``matched``; otherwise -> ``substituted``.
    2. Otherwise, the first fulfillment-eligible product with unknown stock. If it
       is the top-ranked -> ``stock_unknown``; otherwise -> ``substituted``.
    3. Otherwise -> ``not_found``.

    ``alternatives`` are the other ranked, fulfillment-eligible products (up to 3),
    for the cart-review swap affordance (FR-15).
    """
    eligible = [p for p in ranked_products if _fulfillment_ok(p, fulfillment)]
    if not eligible:
        return Selection(status=MatchStatus.NOT_FOUND, chosen=None, alternatives=[])

    top = ranked_products[0] if ranked_products else None

    confirmed_idx = next((i for i, p in enumerate(eligible) if p.stock_level in _CONFIRMED_STOCK), None)
    if confirmed_idx is not None:
        chosen = eligible[confirmed_idx]
        status = MatchStatus.MATCHED if chosen is top else MatchStatus.SUBSTITUTED
    else:
        # No confirmed stock anywhere — fall back to the first eligible (unknown stock).
        chosen = eligible[0]
        status = MatchStatus.STOCK_UNKNOWN if chosen is top else MatchStatus.SUBSTITUTED

    alternatives = [p for p in eligible if p is not chosen][:3]
    return Selection(status=status, chosen=chosen, alternatives=alternatives)
