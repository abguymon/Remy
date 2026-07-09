"""Kroger integration tests — fully offline via httpx.MockTransport.

Covers: search normalization, add-to-cart outcome mapping, the
401→refresh→retry-once path, token-refresh persistence (encrypted at rest), and
the OAuth callback / store-select router flows. No network, no credentials.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio

import remy_api.kroger.service as kservice
from remy_api.db import get_session_factory
from remy_api.kroger import (
    CartItemRequest,
    KrogerAPIError,
    KrogerClient,
    KrogerNotConnectedError,
    Modality,
    OutcomeStatus,
    StockLevel,
    add_items_to_cart,
    get_locations,
    search_products,
    store_tokens,
)
from remy_api.kroger.client import KROGER_API_BASE
from remy_api.kroger.models import KrogerTokenBundle
from remy_api.models import KrogerToken, OAuthState
from remy_api.security import create_access_token
from remy_api.user_service import create_user

# --- Real-shaped Kroger response fixtures (mined from the legacy MCP parsers) --

PRODUCTS_RESPONSE = {
    "data": [
        {
            "productId": "0001111041700",
            "upc": "0001111041700",
            "brand": "Kroger",
            "categories": ["Canned & Packaged", "Beans"],
            "description": "Kroger Black Beans",
            "items": [
                {
                    "itemId": "0001111041700",
                    "price": {"regular": 1.19, "promo": 0.99, "regularPerUnitEstimate": 1.19},
                    "size": "15 oz",
                    "soldBy": "UNIT",
                    "fulfillment": {"curbside": True, "delivery": True, "inStore": True, "shipToHome": False},
                    "inventory": {"stockLevel": "HIGH"},
                }
            ],
            "aisleLocations": [{"description": "Aisle 7", "number": "7"}],
            "images": [
                {
                    "perspective": "front",
                    "featured": True,
                    "sizes": [
                        {"size": "medium", "url": "https://img/black-beans-medium.jpg"},
                        {"size": "large", "url": "https://img/black-beans-large.jpg"},
                    ],
                },
                {"perspective": "back", "sizes": [{"size": "medium", "url": "https://img/back.jpg"}]},
            ],
        },
        {
            # Sparse product: no price, no inventory, no images — must not crash.
            "productId": "0002222",
            "upc": "0002222",
            "description": "Store Brand Black Beans No Salt",
            "items": [{"size": "15 oz", "fulfillment": {"delivery": True}}],
        },
    ],
    "meta": {"pagination": {"total": 2}},
}

LOCATIONS_RESPONSE = {
    "data": [
        {
            "locationId": "70100460",
            "chain": "FRED",
            "name": "Fred Meyer - Burlington",
            "address": {
                "addressLine1": "1815 S Burlington Blvd",
                "city": "Burlington",
                "state": "WA",
                "zipCode": "98233",
            },
            "geolocation": {"latitude": 48.45, "longitude": -122.33},
        }
    ],
    "meta": {},
}

LOCATION_DETAIL_RESPONSE = {
    "data": {
        "locationId": "70100460",
        "chain": "FRED",
        "name": "Fred Meyer - Burlington",
        "address": {"addressLine1": "1815 S Burlington Blvd", "city": "Burlington", "state": "WA", "zipCode": "98233"},
    }
}


# --- Mock transport plumbing --------------------------------------------------


def _token_body(access="app-token", refresh=None, expires_in=1800):
    body = {"access_token": access, "token_type": "bearer", "expires_in": expires_in, "scope": "product.compact"}
    if refresh:
        body["refresh_token"] = refresh
    return body


def make_client(handler) -> KrogerClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url=KROGER_API_BASE)
    return KrogerClient(
        base_url=KROGER_API_BASE,
        client_id="test-client-id",
        client_secret="test-client-secret",
        redirect_uri="https://remy.example.com/api/kroger/callback",
        http=http,
    )


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure the process-wide client singleton never leaks between tests."""
    kservice._client = None
    yield
    kservice._client = None


@pytest_asyncio.fixture
async def user_id(client) -> str:
    """A persisted user id (the ``client`` fixture has reset the schema)."""
    factory = get_session_factory()
    async with factory() as session:
        user = await create_user(session, "krogeruser", "pw12345678")
        return user.id


# --- search_products normalization -------------------------------------------


async def test_search_products_normalization():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/oauth2/token"):
            return httpx.Response(200, json=_token_body())
        assert request.url.path.endswith("/products")
        assert request.url.params["filter.term"] == "black beans"
        assert request.url.params["filter.locationId"] == "70100460"
        assert request.url.params["filter.fulfillment"] == "csp"  # pickup → csp
        return httpx.Response(200, json=PRODUCTS_RESPONSE)

    kc = make_client(handler)
    products = await search_products(None, "black beans", "70100460", limit=10, fulfillment="pickup", client=kc)

    assert len(products) == 2
    p = products[0]
    assert p.upc == "0001111041700"
    assert p.description == "Kroger Black Beans"
    assert p.brand == "Kroger"
    assert p.size == "15 oz"
    assert p.price is not None
    assert p.price.regular == 1.19
    assert p.price.promo == 0.99
    assert p.price.on_sale is True
    assert p.stock_level is StockLevel.HIGH
    assert p.pickup is True and p.delivery is True and p.instore is True
    assert p.image_url == "https://img/black-beans-medium.jpg"  # front + medium preferred
    assert p.department == "Canned & Packaged"
    assert p.aisle == "Aisle 7"

    sparse = products[1]
    assert sparse.price is None
    assert sparse.stock_level is StockLevel.UNKNOWN
    assert sparse.pickup is False and sparse.delivery is True
    assert sparse.image_url is None


async def test_get_locations_normalization():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/oauth2/token"):
            return httpx.Response(200, json=_token_body())
        assert request.url.path.endswith("/locations")
        assert request.url.params["filter.zipCode.near"] == "98233"
        return httpx.Response(200, json=LOCATIONS_RESPONSE)

    kc = make_client(handler)
    stores = await get_locations("98233", limit=8, client=kc)
    assert len(stores) == 1
    s = stores[0]
    assert s.id == "70100460"
    assert s.name == "Fred Meyer - Burlington"
    assert s.zip_code == "98233"
    assert s.full_address == "1815 S Burlington Blvd, Burlington, WA 98233"


async def test_app_token_cached_across_calls():
    calls = {"token": 0, "products": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/oauth2/token"):
            calls["token"] += 1
            return httpx.Response(200, json=_token_body())
        calls["products"] += 1
        return httpx.Response(200, json=PRODUCTS_RESPONSE)

    kc = make_client(handler)
    await search_products(None, "beans", "70100460", client=kc)
    await search_products(None, "rice", "70100460", client=kc)
    assert calls["products"] == 2
    assert calls["token"] == 1  # token fetched once, then cached


# --- add_items_to_cart outcome mapping ---------------------------------------


async def _seed_token(uid: str, *, access="user-access", refresh="user-refresh", expires_in=3600):
    factory = get_session_factory()
    async with factory() as session:
        await store_tokens(
            session,
            uid,
            KrogerTokenBundle(access_token=access, refresh_token=refresh, expires_in=expires_in),
        )


async def test_add_items_success(user_id):
    await _seed_token(user_id)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cart/add"):
            seen["auth"] = request.headers["Authorization"]
            seen["body"] = request.read().decode()
            return httpx.Response(204)
        return httpx.Response(200, json=_token_body())

    kc = make_client(handler)
    factory = get_session_factory()
    async with factory() as session:
        outcomes = await add_items_to_cart(
            session,
            user_id,
            [{"upc": "0001111041700", "quantity": 2, "modality": "PICKUP"}],
            client=kc,
        )
    assert len(outcomes) == 1
    assert outcomes[0].status is OutcomeStatus.ADDED
    assert outcomes[0].quantity == 2
    assert seen["auth"] == "Bearer user-access"
    assert '"upc":"0001111041700"' in seen["body"]


async def test_add_items_invalid_item_not_sent(user_id):
    await _seed_token(user_id)
    sent = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cart/add"):
            sent["count"] += 1
            body = request.read().decode()
            # Only the valid item should reach the API.
            assert "0001111041700" in body
            assert "BADITEM" not in body
            return httpx.Response(204)
        return httpx.Response(200, json=_token_body())

    kc = make_client(handler)
    factory = get_session_factory()
    async with factory() as session:
        outcomes = await add_items_to_cart(
            session,
            user_id,
            [
                {"upc": "0001111041700", "quantity": 1, "modality": "PICKUP"},
                {"upc": "", "quantity": 1, "modality": "PICKUP"},  # missing UPC
                {"upc": "BADITEM", "quantity": 0, "modality": "PICKUP"},  # bad qty
            ],
            client=kc,
        )
    assert sent["count"] == 1
    by_upc = {o.upc: o for o in outcomes}
    assert by_upc["0001111041700"].status is OutcomeStatus.ADDED
    assert by_upc[""].status is OutcomeStatus.FAILED
    assert by_upc["BADITEM"].status is OutcomeStatus.FAILED
    assert by_upc["BADITEM"].reason is not None


async def test_add_items_api_failure_marks_all_failed(user_id):
    await _seed_token(user_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cart/add"):
            return httpx.Response(500, json={"error": "server boom"})
        return httpx.Response(200, json=_token_body())

    kc = make_client(handler)
    factory = get_session_factory()
    async with factory() as session:
        outcomes = await add_items_to_cart(
            session, user_id, [CartItemRequest(upc="0001111041700", quantity=1)], client=kc
        )
    assert len(outcomes) == 1
    assert outcomes[0].status is OutcomeStatus.FAILED
    assert "500" in (outcomes[0].reason or "")


async def test_add_items_not_connected_raises(user_id):
    # No token seeded → must raise, never silently no-op.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_token_body())

    kc = make_client(handler)
    factory = get_session_factory()
    async with factory() as session:
        with pytest.raises(KrogerNotConnectedError):
            await add_items_to_cart(session, user_id, [{"upc": "0001111041700", "quantity": 1}], client=kc)


# --- 401 → refresh → retry-once ----------------------------------------------


async def test_cart_401_triggers_refresh_and_retry(user_id):
    await _seed_token(user_id, access="stale-access", refresh="refresh-1")
    events: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/connect/oauth2/token"):
            form = request.read().decode()
            assert "grant_type=refresh_token" in form
            events.append("refresh")
            return httpx.Response(200, json=_token_body(access="fresh-access", refresh="refresh-2"))
        if path.endswith("/cart/add"):
            auth = request.headers["Authorization"]
            events.append(f"cart:{auth}")
            if auth == "Bearer stale-access":
                return httpx.Response(401, json={"error": "expired"})
            return httpx.Response(204)
        return httpx.Response(200, json=_token_body())

    kc = make_client(handler)
    factory = get_session_factory()
    async with factory() as session:
        outcomes = await add_items_to_cart(session, user_id, [{"upc": "0001111041700", "quantity": 1}], client=kc)
    assert outcomes[0].status is OutcomeStatus.ADDED
    assert events == ["cart:Bearer stale-access", "refresh", "cart:Bearer fresh-access"]

    # The refreshed token was persisted (new access + rotated refresh token).
    async with factory() as session:
        from sqlalchemy import select

        token = (await session.execute(select(KrogerToken).where(KrogerToken.user_id == user_id))).scalar_one()
        assert token.access_token == "fresh-access"
        assert token.refresh_token == "refresh-2"


async def test_expired_token_refreshes_before_request(user_id, db_path):
    # Token already expired on disk → a refresh happens before the cart write,
    # and the persisted refreshed tokens must be encrypted at rest.
    factory = get_session_factory()
    async with factory() as session:
        await store_tokens(
            session,
            user_id,
            KrogerTokenBundle(access_token="old-access", refresh_token="old-refresh", expires_in=-10),
        )
    events: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/oauth2/token"):
            events.append("refresh")
            return httpx.Response(
                200, json=_token_body(access="rotated-access-SENTINEL", refresh="rotated-refresh-SENTINEL")
            )
        if request.url.path.endswith("/cart/add"):
            events.append(request.headers["Authorization"])
            return httpx.Response(204)
        return httpx.Response(200, json=_token_body())

    kc = make_client(handler)
    async with factory() as session:
        outcomes = await add_items_to_cart(session, user_id, [{"upc": "0001111041700", "quantity": 1}], client=kc)
    assert outcomes[0].status is OutcomeStatus.ADDED
    assert events == ["refresh", "Bearer rotated-access-SENTINEL"]

    # Encrypted at rest: raw DB bytes must not contain the plaintext tokens.
    raw = open(db_path, "rb").read()
    assert b"rotated-access-SENTINEL" not in raw
    assert b"rotated-refresh-SENTINEL" not in raw


# --- OAuth router flows -------------------------------------------------------


async def test_oauth_callback_happy_path(client, user_id):
    factory = get_session_factory()
    async with factory() as session:
        session.add(OAuthState(state="state-good", user_id=user_id, pkce_verifier="verifier-abc"))
        await session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/connect/oauth2/token")
        form = request.read().decode()
        assert "grant_type=authorization_code" in form
        assert "code_verifier=verifier-abc" in form
        assert "code=auth-code-123" in form
        return httpx.Response(200, json=_token_body(access="cb-access", refresh="cb-refresh"))

    kservice._client = make_client(handler)

    resp = await client.get(
        "/kroger/callback", params={"code": "auth-code-123", "state": "state-good"}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert "kroger=connected" in resp.headers["location"]

    async with factory() as session:
        from sqlalchemy import select

        token = (await session.execute(select(KrogerToken).where(KrogerToken.user_id == user_id))).scalar_one()
        assert token.access_token == "cb-access"
        # State is single-use — consumed on the callback.
        state = await session.get(OAuthState, "state-good")
        assert state is None


async def test_oauth_callback_bad_state(client, user_id):
    resp = await client.get("/kroger/callback", params={"code": "c", "state": "does-not-exist"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "reason=invalid_state" in resp.headers["location"]


async def test_oauth_callback_expired_state(client, user_id):
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            OAuthState(
                state="state-old",
                user_id=user_id,
                pkce_verifier="v",
                created_at=datetime.now(UTC) - timedelta(minutes=20),
            )
        )
        await session.commit()

    resp = await client.get("/kroger/callback", params={"code": "c", "state": "state-old"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "reason=state_expired" in resp.headers["location"]
    # Expired state is still deleted (single-use).
    async with factory() as session:
        assert await session.get(OAuthState, "state-old") is None


async def test_oauth_callback_provider_error(client, user_id):
    resp = await client.get("/kroger/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "reason=access_denied" in resp.headers["location"]


async def test_auth_url_persists_state(client, user_id):
    token = create_access_token(user_id)
    resp = await client.get("/kroger/auth", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    auth_url = resp.json()["auth_url"]
    assert "code_challenge_method=S256" in auth_url
    assert "response_type=code" in auth_url
    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import select

        states = (await session.execute(select(OAuthState).where(OAuthState.user_id == user_id))).scalars().all()
        assert len(states) == 1
        assert states[0].pkce_verifier  # a verifier was stored for the exchange


async def test_status_and_disconnect(client, user_id):
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # Not connected yet.
    resp = await client.get("/kroger/status", headers=headers)
    assert resp.json()["connected"] is False

    await _seed_token(user_id)
    resp = await client.get("/kroger/status", headers=headers)
    body = resp.json()
    assert body["connected"] is True
    assert body["expired"] is False

    resp = await client.delete("/kroger/disconnect", headers=headers)
    assert resp.status_code == 204
    resp = await client.get("/kroger/status", headers=headers)
    assert resp.json()["connected"] is False


async def test_store_select_round_trip(client, user_id):
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/oauth2/token"):
            return httpx.Response(200, json=_token_body())
        assert request.url.path.endswith("/locations/70100460")
        return httpx.Response(200, json=LOCATION_DETAIL_RESPONSE)

    kservice._client = make_client(handler)

    resp = await client.post("/kroger/stores/70100460/select", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["store_location_id"] == "70100460"
    assert body["store_name"] == "Fred Meyer - Burlington"
    assert body["zip_code"] == "98233"

    # Persisted to user settings.
    resp = await client.get("/users/me/settings", headers=headers)
    settings = resp.json()
    assert settings["store_location_id"] == "70100460"
    assert settings["store_name"] == "Fred Meyer - Burlington"


async def test_store_select_unknown_store_404(client, user_id):
    token = create_access_token(user_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/oauth2/token"):
            return httpx.Response(200, json=_token_body())
        return httpx.Response(404, json={"errors": {"reason": "not found"}})

    kservice._client = make_client(handler)
    resp = await client.post("/kroger/stores/99999999/select", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


# --- Direct client error mapping ---------------------------------------------


async def test_stores_endpoint_maps_rate_limit(client, user_id):
    token = create_access_token(user_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/oauth2/token"):
            return httpx.Response(200, json=_token_body())
        return httpx.Response(429, headers={"Retry-After": "30"}, json={"error": "slow down"})

    kservice._client = make_client(handler)
    resp = await client.get("/kroger/stores", params={"zip": "98233"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    assert resp.headers.get("Retry-After") == "30"


def test_pkce_challenge_is_valid_s256():
    import base64
    import hashlib

    from remy_api.kroger.client import generate_pkce

    verifier, challenge = generate_pkce()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert challenge == expected
    assert 43 <= len(verifier) <= 128


def test_kroger_api_error_is_typed():
    err = KrogerAPIError("boom", status_code=503)
    assert err.status_code == 503
    assert err.message == "boom"


def test_modality_enum_values():
    assert Modality.PICKUP.value == "PICKUP"
    assert Modality.DELIVERY.value == "DELIVERY"
