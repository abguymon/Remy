"""Normalized Pydantic models for Kroger data and the raw-response mappers.

The Kroger Public API returns deeply nested, verbose payloads. These models are
the narrow, stable shape the rest of Remy consumes (the planner, the web app,
and the MCP facade). ``*.from_raw`` classmethods do all the field-plucking and
defaulting so no consumer ever touches a raw Kroger dict.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel


class StockLevel(enum.StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    TEMPORARILY_OUT_OF_STOCK = "TEMPORARILY_OUT_OF_STOCK"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_raw(cls, value: str | None) -> StockLevel:
        if not value:
            return cls.UNKNOWN
        try:
            return cls(value.upper())
        except ValueError:
            return cls.UNKNOWN


class Modality(enum.StrEnum):
    """Cart fulfillment modality accepted by ``PUT /cart/add``."""

    PICKUP = "PICKUP"
    DELIVERY = "DELIVERY"


class OutcomeStatus(enum.StrEnum):
    ADDED = "added"
    FAILED = "failed"


# Kroger ``filter.fulfillment`` query values keyed by our plain vocabulary.
FULFILLMENT_FILTER = {"pickup": "csp", "delivery": "delivery", "instore": "ais"}


class Price(BaseModel):
    regular: float | None = None
    promo: float | None = None
    regular_per_unit: float | None = None
    promo_per_unit: float | None = None
    on_sale: bool = False

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> Price | None:
        if not raw:
            return None
        regular = raw.get("regular")
        # Kroger sends promo == 0 when there is no promotion; treat that as none.
        promo = raw.get("promo") or None
        on_sale = promo is not None and regular is not None and promo < regular
        return cls(
            regular=regular,
            promo=promo,
            regular_per_unit=raw.get("regularPerUnitEstimate"),
            promo_per_unit=raw.get("promoPerUnitEstimate") or None,
            on_sale=on_sale,
        )


def _select_image(images: list[dict[str, Any]], perspective: str = "front", size: str = "medium") -> str | None:
    """Pick a ``perspective``/``size`` image URL, degrading gracefully."""
    if not images:
        return None

    def size_url(img: dict[str, Any], want: str) -> str | None:
        for s in img.get("sizes") or []:
            if s.get("size") == want and s.get("url"):
                return s["url"]
        return None

    # Prefer the requested perspective, then a featured image, then the first.
    ordered = sorted(images, key=lambda i: (i.get("perspective") != perspective, not i.get("featured")))
    for img in ordered:
        url = size_url(img, size)
        if url:
            return url
    # Fall back to any size on the best-ranked image.
    for img in ordered:
        for s in img.get("sizes") or []:
            if s.get("url"):
                return s["url"]
    return None


class Product(BaseModel):
    """A normalized Kroger product (one search result)."""

    upc: str
    product_id: str | None = None
    description: str | None = None
    brand: str | None = None
    size: str | None = None
    price: Price | None = None
    stock_level: StockLevel = StockLevel.UNKNOWN
    pickup: bool = False
    delivery: bool = False
    instore: bool = False
    image_url: str | None = None
    department: str | None = None
    categories: list[str] = []
    aisle: str | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Product:
        items = raw.get("items") or []
        item = items[0] if items else {}
        fulfillment = item.get("fulfillment") or {}
        inventory = item.get("inventory") or {}
        categories = list(raw.get("categories") or [])
        aisles = raw.get("aisleLocations") or []
        aisle = aisles[0].get("description") if aisles and isinstance(aisles[0], dict) else None
        return cls(
            upc=raw.get("upc") or raw.get("productId") or "",
            product_id=raw.get("productId"),
            description=raw.get("description"),
            brand=raw.get("brand"),
            size=item.get("size"),
            price=Price.from_raw(item.get("price")),
            stock_level=StockLevel.from_raw(inventory.get("stockLevel")),
            pickup=bool(fulfillment.get("curbside")),
            delivery=bool(fulfillment.get("delivery")),
            instore=bool(fulfillment.get("inStore")),
            image_url=_select_image(raw.get("images") or []),
            department=categories[0] if categories else None,
            categories=categories,
            aisle=aisle,
        )


class StoreLocation(BaseModel):
    id: str
    name: str | None = None
    chain: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    full_address: str | None = None
    distance: float | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> StoreLocation:
        addr = raw.get("address") or {}
        street = addr.get("addressLine1", "")
        city = addr.get("city", "")
        state = addr.get("state", "")
        zip_code = addr.get("zipCode", "")
        full = f"{street}, {city}, {state} {zip_code}".strip(", ")
        return cls(
            id=raw.get("locationId") or "",
            name=raw.get("name"),
            chain=raw.get("chain"),
            address=street or None,
            city=city or None,
            state=state or None,
            zip_code=zip_code or None,
            full_address=full or None,
            # Kroger's location payload does not always include a distance; keep it optional.
            distance=raw.get("distance"),
        )


class CartItemRequest(BaseModel):
    upc: str
    quantity: int = 1
    modality: Modality = Modality.PICKUP


class CartItemOutcome(BaseModel):
    """Truthful per-item result of a cart write (FR-16)."""

    upc: str
    quantity: int
    modality: Modality
    status: OutcomeStatus
    reason: str | None = None


class KrogerTokenBundle(BaseModel):
    """A token response from Kroger's OAuth token endpoint."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 0
    refresh_token: str | None = None
    scope: str | None = None

    def expires_at(self, now: datetime | None = None) -> datetime:
        current = now or datetime.now(UTC)
        return current + timedelta(seconds=self.expires_in)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> KrogerTokenBundle:
        return cls(
            access_token=raw["access_token"],
            token_type=raw.get("token_type", "bearer"),
            expires_in=int(raw.get("expires_in", 0)),
            refresh_token=raw.get("refresh_token"),
            scope=raw.get("scope"),
        )
