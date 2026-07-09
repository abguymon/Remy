"""Domain functions consumed by the planner (T5), the router, and the MCP facade.

These wrap :class:`KrogerClient` with the DB-backed per-user token store and the
normalization mappers, and are the *only* Kroger surface the rest of the app
should call. Calling conventions (for T5):

* ``search_products(session, term, location_id, limit=10, fulfillment=None)``
  → ``list[Product]``. ``fulfillment`` is ``"pickup" | "delivery" | None``.
  Uses the shared app token (no user connection required).
* ``get_locations(zip_code, limit=8, chain=...)`` → ``list[StoreLocation]``.
  App token only.
* ``add_items_to_cart(session, user_id, items)`` → ``list[CartItemOutcome]``.
  Requires a connected user; performs the 401→refresh→retry-once path. ``items``
  is a list of dicts/``CartItemRequest`` with ``upc``, ``quantity``, ``modality``.

All failures raise a :class:`KrogerError` subclass — never ``None`` (PRD §9.1).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.models import KrogerToken

from .client import TOKEN_SKEW_SECONDS, KrogerClient
from .errors import KrogerAuthError, KrogerError, KrogerNotConnectedError
from .models import (
    CartItemOutcome,
    CartItemRequest,
    KrogerTokenBundle,
    Modality,
    OutcomeStatus,
    Product,
    StoreLocation,
)

# Process-wide client singleton (owns the app-token cache + httpx pool).
_client: KrogerClient | None = None


def get_client() -> KrogerClient:
    global _client
    if _client is None:
        _client = KrogerClient()
    return _client


async def close_client() -> None:
    """Close the shared client (app shutdown). Safe to call when unused."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _resolve(client: KrogerClient | None) -> KrogerClient:
    return client or get_client()


# --- Token store -------------------------------------------------------------


async def _load_token(session: AsyncSession, user_id: str) -> KrogerToken | None:
    row = await session.execute(select(KrogerToken).where(KrogerToken.user_id == user_id))
    return row.scalar_one_or_none()


async def store_tokens(session: AsyncSession, user_id: str, bundle: KrogerTokenBundle) -> KrogerToken:
    """Upsert a user's Kroger tokens (encrypted columns handle encryption)."""
    token = await _load_token(session, user_id)
    expires_at = bundle.expires_at()
    if token is None:
        token = KrogerToken(
            user_id=user_id,
            access_token=bundle.access_token,
            refresh_token=bundle.refresh_token,
            expires_at=expires_at,
        )
        session.add(token)
    else:
        token.access_token = bundle.access_token
        # Kroger may omit a fresh refresh token on refresh — keep the existing one.
        if bundle.refresh_token:
            token.refresh_token = bundle.refresh_token
        token.expires_at = expires_at
    await session.commit()
    await session.refresh(token)
    return token


def _is_expired(token: KrogerToken, *, skew: int = TOKEN_SKEW_SECONDS) -> bool:
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return datetime.now(UTC) >= expires_at - timedelta(seconds=skew)


async def _valid_access_token(
    session: AsyncSession, user_id: str, client: KrogerClient, *, force_refresh: bool = False
) -> str:
    token = await _load_token(session, user_id)
    if token is None:
        raise KrogerNotConnectedError("Kroger not connected — visit Settings to connect your account.")
    if not force_refresh and not _is_expired(token):
        return token.access_token
    if not token.refresh_token:
        raise KrogerNotConnectedError("Kroger session expired and cannot be refreshed — reconnect in Settings.")
    try:
        bundle = await client.refresh(token.refresh_token)
    except KrogerAuthError as exc:
        # A failed refresh means the grant is dead — the user must reconnect.
        raise KrogerNotConnectedError("Kroger session could not be refreshed — reconnect in Settings.") from exc
    refreshed = await store_tokens(session, user_id, bundle)
    return refreshed.access_token


# --- Domain functions --------------------------------------------------------


async def get_locations(
    zip_code: str,
    limit: int = 8,
    *,
    chain: str | None = None,
    radius_in_miles: int = 25,
    client: KrogerClient | None = None,
) -> list[StoreLocation]:
    kroger = _resolve(client)
    raw = await kroger.get_locations_raw(zip_code=zip_code, limit=limit, chain=chain, radius_in_miles=radius_in_miles)
    return [StoreLocation.from_raw(loc) for loc in raw.get("data") or []]


async def get_location(location_id: str, *, client: KrogerClient | None = None) -> StoreLocation | None:
    """Fetch one store; ``None`` if it does not exist (for store selection)."""
    kroger = _resolve(client)
    raw = await kroger.get_location_raw(location_id)
    if raw is None:
        return None
    return StoreLocation.from_raw(raw.get("data") or {})


async def search_products(
    session: AsyncSession,  # noqa: ARG001 — kept for a uniform planner calling convention
    term: str,
    location_id: str,
    limit: int = 10,
    fulfillment: str | None = None,
    *,
    client: KrogerClient | None = None,
) -> list[Product]:
    """Search products at ``location_id``. ``session`` is accepted for a uniform
    call signature with the cart function (and future per-user tuning) but the
    product endpoint uses the shared app token, so no user connection is needed.
    """
    kroger = _resolve(client)
    raw = await kroger.get_products_raw(term=term, location_id=location_id, limit=limit, fulfillment=fulfillment)
    return [Product.from_raw(p) for p in raw.get("data") or []]


async def add_items_to_cart(
    session: AsyncSession,
    user_id: str,
    items: list[dict[str, Any] | CartItemRequest],
    *,
    client: KrogerClient | None = None,
) -> list[CartItemOutcome]:
    """Add ``items`` to the user's real Kroger cart (add-only ``PUT /cart/add``).

    Returns a truthful per-item outcome list (FR-16). Invalid items are marked
    ``failed`` without being sent; the remaining valid items are submitted in one
    batch. A failed API call surfaces as ``failed`` on every attempted item —
    never as silent success. The batch endpoint gives no per-item response, so a
    2xx marks all attempted items ``added`` and any error marks them all
    ``failed`` with the same reason.
    """
    kroger = _resolve(client)

    outcomes: list[CartItemOutcome] = []
    valid: list[CartItemRequest] = []
    for raw_item in items:
        parsed, error = _parse_cart_item(raw_item)
        if error is not None:
            upc = ""
            qty = 0
            modality = Modality.PICKUP
            if isinstance(raw_item, CartItemRequest):
                upc, qty, modality = raw_item.upc, raw_item.quantity, raw_item.modality
            elif isinstance(raw_item, dict):
                upc = str(raw_item.get("upc") or "")
                qty = int(raw_item.get("quantity") or 0) if str(raw_item.get("quantity") or "0").isdigit() else 0
            outcomes.append(
                CartItemOutcome(upc=upc, quantity=qty, modality=modality, status=OutcomeStatus.FAILED, reason=error)
            )
        else:
            valid.append(parsed)

    if not valid:
        return outcomes

    payload = [{"upc": i.upc, "quantity": i.quantity, "modality": i.modality.value} for i in valid]

    # Token acquisition failures (never connected / dead refresh) propagate as
    # KrogerNotConnectedError so the UI/agent shows "connect Kroger" — they are a
    # connection problem, not a per-item cart result. Only failures of the actual
    # PUT /cart/add map to per-item ``failed`` outcomes (FR-16).
    access_token = await _valid_access_token(session, user_id, kroger)
    try:
        await kroger.put_cart_add(access_token=access_token, items=payload)
    except KrogerAuthError:
        # 401 → refresh once (may raise KrogerNotConnectedError, which propagates)
        # and retry the write exactly once.
        access_token = await _valid_access_token(session, user_id, kroger, force_refresh=True)
        try:
            await kroger.put_cart_add(access_token=access_token, items=payload)
        except KrogerError as exc:
            return _mark_failed(items, outcomes, valid, exc)
    except KrogerError as exc:
        return _mark_failed(items, outcomes, valid, exc)

    for item in valid:
        outcomes.append(
            CartItemOutcome(upc=item.upc, quantity=item.quantity, modality=item.modality, status=OutcomeStatus.ADDED)
        )
    return _reorder_outcomes(items, outcomes)


def _mark_failed(
    original: list[dict[str, Any] | CartItemRequest],
    outcomes: list[CartItemOutcome],
    valid: list[CartItemRequest],
    exc: KrogerError,
) -> list[CartItemOutcome]:
    reason = getattr(exc, "message", str(exc))
    for item in valid:
        outcomes.append(
            CartItemOutcome(
                upc=item.upc,
                quantity=item.quantity,
                modality=item.modality,
                status=OutcomeStatus.FAILED,
                reason=reason,
            )
        )
    return _reorder_outcomes(original, outcomes)


def _parse_cart_item(raw_item: dict[str, Any] | CartItemRequest) -> tuple[CartItemRequest, None] | tuple[None, str]:
    try:
        item = raw_item if isinstance(raw_item, CartItemRequest) else CartItemRequest.model_validate(raw_item)
    except Exception as exc:  # noqa: BLE001 — normalize any validation issue to a reason
        return None, f"Invalid cart item: {exc}"
    if not item.upc:
        return None, "Missing UPC."
    if item.quantity < 1:
        return None, "Quantity must be at least 1."
    return item, None


def _reorder_outcomes(
    original: list[dict[str, Any] | CartItemRequest], outcomes: list[CartItemOutcome]
) -> list[CartItemOutcome]:
    """Return outcomes in the same order as the input items (best-effort by UPC)."""

    def key(item: dict[str, Any] | CartItemRequest) -> str:
        return item.upc if isinstance(item, CartItemRequest) else str(item.get("upc") or "")

    remaining = list(outcomes)
    ordered: list[CartItemOutcome] = []
    for item in original:
        upc = key(item)
        for i, outcome in enumerate(remaining):
            if outcome.upc == upc:
                ordered.append(remaining.pop(i))
                break
    ordered.extend(remaining)
    return ordered
