"""One-time invitation registration and session invalidation coverage."""

import pytest_asyncio
from sqlalchemy import select

from remy_api.db import get_session_factory
from remy_api.models import Invitation
from remy_api.user_service import create_user

ADMIN = "owner"
ADMIN_PASSWORD = "owner-password-123"


@pytest_asyncio.fixture
async def admin_client(client):
    factory = get_session_factory()
    async with factory() as session:
        await create_user(session, ADMIN, ADMIN_PASSWORD, is_admin=True)
    return client


async def _login(client, username=ADMIN, password=ADMIN_PASSWORD):
    response = await client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_invite_creates_self_service_account_once(admin_client):
    admin_token = await _login(admin_client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    created = await admin_client.post(
        "/admin/invitations", json={"recipient_label": "Aunt May", "expires_in_days": 7}, headers=headers
    )
    assert created.status_code == 201, created.text
    invitation = created.json()
    assert invitation["recipient_label"] == "Aunt May"
    assert invitation["invitation_token"]

    listed = await admin_client.get("/admin/invitations", headers=headers)
    assert listed.status_code == 200
    assert "invitation_token" not in listed.json()[0]

    registered = await admin_client.post(
        "/auth/register",
        json={
            "username": "may",
            "password": "a-long-password-123",
            "invitation_token": invitation["invitation_token"],
        },
    )
    assert registered.status_code == 201, registered.text
    assert registered.json()["username"] == "may"

    reused = await admin_client.post(
        "/auth/register",
        json={
            "username": "other",
            "password": "another-long-password",
            "invitation_token": invitation["invitation_token"],
        },
    )
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "invalid_invitation"

    factory = get_session_factory()
    async with factory() as session:
        row = await session.execute(select(Invitation))
        stored = row.scalar_one()
        assert stored.token_hash != invitation["invitation_token"]
        assert stored.redeemed_at is not None


async def test_non_admin_cannot_manage_invitations(admin_client):
    factory = get_session_factory()
    async with factory() as session:
        await create_user(session, "member", "member-password-123")
    token = await _login(admin_client, "member", "member-password-123")
    response = await admin_client.post("/admin/invitations", json={}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_required"


async def test_password_change_invalidates_existing_jwt(admin_client):
    token = await _login(admin_client)
    headers = {"Authorization": f"Bearer {token}"}
    changed = await admin_client.post(
        "/users/me/password",
        json={"current_password": ADMIN_PASSWORD, "new_password": "new-owner-password-123"},
        headers=headers,
    )
    assert changed.status_code == 204

    old_session = await admin_client.get("/users/me", headers=headers)
    assert old_session.status_code == 401
    fresh_token = await _login(admin_client, password="new-owner-password-123")
    fresh_session = await admin_client.get("/users/me", headers={"Authorization": f"Bearer {fresh_token}"})
    assert fresh_session.status_code == 200
