"""Admin user-management endpoints (role gate, CRUD, activation, temp passwords)."""

import pytest_asyncio

from remy_api.db import get_session_factory
from remy_api.user_service import create_user

ADMIN = "boss"
ADMIN_PW = "admin-secret-pw-1"
USER = "regular"
USER_PW = "regular-secret-pw"


@pytest_asyncio.fixture
async def seeded(client):
    """An admin and a plain user; returns the client."""
    factory = get_session_factory()
    async with factory() as session:
        await create_user(session, ADMIN, ADMIN_PW, is_admin=True)
        await create_user(session, USER, USER_PW)
    return client


async def _login(client, username, password) -> str:
    resp = await client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _headers(client, username, password) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _login(client, username, password)}"}


async def test_me_reports_is_admin(seeded):
    client = seeded
    admin_me = await client.get("/users/me", headers=await _headers(client, ADMIN, ADMIN_PW))
    assert admin_me.status_code == 200
    assert admin_me.json()["is_admin"] is True

    user_me = await client.get("/users/me", headers=await _headers(client, USER, USER_PW))
    assert user_me.json()["is_admin"] is False


async def test_list_users(seeded):
    client = seeded
    resp = await client.get("/admin/users", headers=await _headers(client, ADMIN, ADMIN_PW))
    assert resp.status_code == 200
    rows = resp.json()
    assert {r["username"] for r in rows} == {ADMIN, USER}
    for r in rows:
        assert "password_hash" not in r
        assert "password" not in r
        assert set(r) == {"id", "username", "is_admin", "is_active", "created_at", "kroger_connected"}
        assert r["kroger_connected"] is False


async def test_non_admin_gets_403_on_every_admin_endpoint(seeded):
    client = seeded
    headers = await _headers(client, USER, USER_PW)
    # A target id to exercise the parametrized routes.
    users = await client.get("/admin/users", headers=await _headers(client, ADMIN, ADMIN_PW))
    target_id = next(r["id"] for r in users.json() if r["username"] == USER)

    calls = [
        ("get", "/admin/users", None),
        ("post", "/admin/users", {"username": "newbie"}),
        ("post", f"/admin/users/{target_id}/reset-password", None),
        ("post", f"/admin/users/{target_id}/deactivate", None),
        ("post", f"/admin/users/{target_id}/activate", None),
    ]
    for method, path, body in calls:
        resp = await getattr(client, method)(path, headers=headers, **({"json": body} if body else {}))
        assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"
        assert resp.json()["error"]["code"] == "admin_required"


async def test_create_user_returns_temp_password_and_seeds_settings(seeded):
    client = seeded
    headers = await _headers(client, ADMIN, ADMIN_PW)
    resp = await client.post("/admin/users", json={"username": "newbie"}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    temp = body["temp_password"]
    assert temp and body["username"] == "newbie"

    # Temp password works at login, and the new user has seeded default settings.
    new_headers = await _headers(client, "newbie", temp)
    settings = await client.get("/users/me/settings", headers=new_headers)
    assert settings.status_code == 200
    assert settings.json()["pantry_items"]  # seeded, non-empty

    # Duplicate username is a 409.
    dup = await client.post("/admin/users", json={"username": "newbie"}, headers=headers)
    assert dup.status_code == 409


async def test_create_then_change_password_flow(seeded):
    client = seeded
    admin_headers = await _headers(client, ADMIN, ADMIN_PW)
    created = await client.post("/admin/users", json={"username": "changer"}, headers=admin_headers)
    temp = created.json()["temp_password"]

    new_headers = await _headers(client, "changer", temp)
    changed = await client.post(
        "/users/me/password",
        json={"current_password": temp, "new_password": "chosen-strong-pw"},
        headers=new_headers,
    )
    assert changed.status_code == 204
    # Old temp no longer logs in; the chosen password does.
    old = await client.post("/auth/login", json={"username": "changer", "password": temp})
    assert old.status_code == 401
    fresh = await client.post("/auth/login", json={"username": "changer", "password": "chosen-strong-pw"})
    assert fresh.status_code == 200


async def test_reset_password_returns_new_temp(seeded):
    client = seeded
    admin_headers = await _headers(client, ADMIN, ADMIN_PW)
    users = await client.get("/admin/users", headers=admin_headers)
    user_id = next(r["id"] for r in users.json() if r["username"] == USER)

    resp = await client.post(f"/admin/users/{user_id}/reset-password", headers=admin_headers)
    assert resp.status_code == 200
    temp = resp.json()["temp_password"]
    assert temp

    # Old password rejected; the reset temp works.
    old = await client.post("/auth/login", json={"username": USER, "password": USER_PW})
    assert old.status_code == 401
    fresh = await client.post("/auth/login", json={"username": USER, "password": temp})
    assert fresh.status_code == 200

    # Reset on an unknown id is a 404.
    missing = await client.post("/admin/users/nope/reset-password", headers=admin_headers)
    assert missing.status_code == 404


async def test_deactivate_blocks_login_and_activate_restores(seeded):
    client = seeded
    admin_headers = await _headers(client, ADMIN, ADMIN_PW)
    users = await client.get("/admin/users", headers=admin_headers)
    user_id = next(r["id"] for r in users.json() if r["username"] == USER)

    deact = await client.post(f"/admin/users/{user_id}/deactivate", headers=admin_headers)
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False

    denied = await client.post("/auth/login", json={"username": USER, "password": USER_PW})
    assert denied.status_code == 401

    act = await client.post(f"/admin/users/{user_id}/activate", headers=admin_headers)
    assert act.status_code == 200
    assert act.json()["is_active"] is True

    allowed = await client.post("/auth/login", json={"username": USER, "password": USER_PW})
    assert allowed.status_code == 200


async def test_admin_cannot_deactivate_self(seeded):
    client = seeded
    admin_headers = await _headers(client, ADMIN, ADMIN_PW)
    users = await client.get("/admin/users", headers=admin_headers)
    admin_id = next(r["id"] for r in users.json() if r["username"] == ADMIN)

    resp = await client.post(f"/admin/users/{admin_id}/deactivate", headers=admin_headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "cannot_deactivate_self"

    # Admin can still log in — nothing changed.
    still = await client.post("/auth/login", json={"username": ADMIN, "password": ADMIN_PW})
    assert still.status_code == 200


async def test_deactivated_user_api_token_rejected(seeded):
    """A deactivated user's bearer auth is rejected on authed endpoints (403)."""
    client = seeded
    admin_headers = await _headers(client, ADMIN, ADMIN_PW)
    user_headers = await _headers(client, USER, USER_PW)

    # The user is active now — a normal call succeeds.
    ok = await client.get("/users/me", headers=user_headers)
    assert ok.status_code == 200

    users = await client.get("/admin/users", headers=admin_headers)
    user_id = next(r["id"] for r in users.json() if r["username"] == USER)
    await client.post(f"/admin/users/{user_id}/deactivate", headers=admin_headers)

    # Existing JWT now rejected because the account is disabled.
    disabled = await client.get("/users/me", headers=user_headers)
    assert disabled.status_code == 403
