"""GET /orders — user-scoped, newest-first order history (FR-17, DESIGN_BRIEF §4.9)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from remy_api.db import get_session_factory
from remy_api.models import Order
from remy_api.user_service import create_user

USERNAME = "owner"
PASSWORD = "sup3r-secret-pw"


@pytest_asyncio.fixture
async def auth(client):
    factory = get_session_factory()
    async with factory() as s:
        user = await create_user(s, USERNAME, PASSWORD)
        user_id = user.id
    resp = await client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    token = resp.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}, user_id


async def test_requires_auth(client):
    resp = await client.get("/orders")
    assert resp.status_code == 401


async def test_empty_history(auth):
    client, headers, _ = auth
    resp = await client.get("/orders", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_lists_newest_first_and_scopes_to_user(auth):
    client, headers, user_id = auth
    factory = get_session_factory()
    async with factory() as s:
        # Two orders for our user + one for a stranger who must not appear.
        stranger = await create_user(s, "stranger", PASSWORD)
        now = datetime.now(UTC)
        s.add_all(
            [
                Order(
                    user_id=user_id,
                    items=[{"description": "old"}],
                    estimated_total=10.0,
                    created_at=now - timedelta(days=1),
                ),
                Order(
                    user_id=user_id,
                    items=[{"description": "new"}],
                    estimated_total=42.5,
                    created_at=now,
                ),
                Order(user_id=stranger.id, items=[{"description": "theirs"}], estimated_total=99.0),
            ]
        )
        await s.commit()

    resp = await client.get("/orders", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2  # stranger's order excluded
    # Newest first: the $42.50 order was inserted last.
    assert body[0]["estimated_total"] == 42.5
    assert body[0]["items"] == [{"description": "new"}]
    assert {"id", "plan_id", "items", "estimated_total", "created_at"} <= body[0].keys()
