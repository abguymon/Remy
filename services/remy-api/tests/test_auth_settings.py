"""End-to-end auth + settings + API-token flow (T1 acceptance).

bootstrap -> login -> settings round-trip (defaults seeded from yaml) ->
API token create -> use as bearer -> revoke -> rejected.
"""

import pytest_asyncio

from remy_api.db import get_session_factory
from remy_api.models import FulfillmentMethod
from remy_api.seed import default_favorite_sites, default_pantry_items
from remy_api.user_service import create_user

USERNAME = "owner"
PASSWORD = "sup3r-secret-pw"


@pytest_asyncio.fixture
async def bootstrapped(client):
    """Create the first user (CLI bootstrap equivalent) and return the client."""
    factory = get_session_factory()
    async with factory() as session:
        await create_user(session, USERNAME, PASSWORD)
    return client


async def _login(client, username=USERNAME, password=PASSWORD) -> str:
    resp = await client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def test_login_success_and_failure(bootstrapped):
    client = bootstrapped
    token = await _login(client)
    assert token

    bad = await client.post("/auth/login", json={"username": USERNAME, "password": "wrong"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "unauthenticated"

    unknown = await client.post("/auth/login", json={"username": "nope", "password": "x"})
    assert unknown.status_code == 401


async def test_unauthenticated_requests_rejected(client):
    resp = await client.get("/users/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


async def test_settings_defaults_seeded_from_yaml(bootstrapped):
    client = bootstrapped
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/users/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == USERNAME

    resp = await client.get("/users/me/settings", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    # Seeded from repo-root pantry.yaml / recipe_sources.yaml.
    assert body["pantry_items"] == default_pantry_items()
    assert "salt" in body["pantry_items"]
    assert body["favorite_sites"] == default_favorite_sites()
    assert "seriouseats.com" in body["favorite_sites"]
    assert body["fulfillment_method"] == FulfillmentMethod.PICKUP.value


async def test_settings_update_round_trip(bootstrapped):
    client = bootstrapped
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    update = {
        "pantry_items": ["salt", "olive oil"],
        "store_location_id": "70100123",
        "store_name": "Fred Meyer Interstate",
        "zip_code": "97217",
        "fulfillment_method": "DELIVERY",
    }
    put = await client.put("/users/me/settings", json=update, headers=headers)
    assert put.status_code == 200
    body = put.json()
    assert body["pantry_items"] == ["salt", "olive oil"]
    assert body["store_location_id"] == "70100123"
    assert body["fulfillment_method"] == "DELIVERY"

    # Partial update leaves untouched fields intact.
    partial = await client.put("/users/me/settings", json={"zip_code": "98101"}, headers=headers)
    assert partial.status_code == 200
    assert partial.json()["zip_code"] == "98101"
    assert partial.json()["store_name"] == "Fred Meyer Interstate"

    # Persisted across a fresh GET.
    again = await client.get("/users/me/settings", headers=headers)
    assert again.json()["zip_code"] == "98101"


async def test_api_token_lifecycle(bootstrapped):
    client = bootstrapped
    jwt_token = await _login(client)
    jwt_headers = {"Authorization": f"Bearer {jwt_token}"}

    # Create — full token returned exactly once, with recognizable prefix.
    created = await client.post("/users/me/api-tokens", json={"name": "claude-desktop"}, headers=jwt_headers)
    assert created.status_code == 201
    payload = created.json()
    full_token = payload["token"]
    token_id = payload["id"]
    assert full_token.startswith("remy_")

    # List never leaks the token.
    listed = await client.get("/users/me/api-tokens", headers=jwt_headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert "token" not in rows[0]
    assert rows[0]["name"] == "claude-desktop"
    assert rows[0]["revoked_at"] is None
    assert rows[0]["last_used_at"] is None

    # Use the API token as bearer on an authed endpoint.
    api_headers = {"Authorization": f"Bearer {full_token}"}
    me = await client.get("/users/me", headers=api_headers)
    assert me.status_code == 200
    assert me.json()["username"] == USERNAME

    # last_used_at is stamped after use.
    listed2 = await client.get("/users/me/api-tokens", headers=jwt_headers)
    assert listed2.json()[0]["last_used_at"] is not None

    # Revoke, then the token is rejected.
    revoke = await client.delete(f"/users/me/api-tokens/{token_id}", headers=jwt_headers)
    assert revoke.status_code == 204
    rejected = await client.get("/users/me", headers=api_headers)
    assert rejected.status_code == 401

    # Revoking a nonexistent id is 404.
    missing = await client.delete("/users/me/api-tokens/does-not-exist", headers=jwt_headers)
    assert missing.status_code == 404
