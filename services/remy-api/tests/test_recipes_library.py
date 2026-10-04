"""Cookbook library fields: favorites, ratings, notes, tags, cooked count (COOKBOOK_PLAN v1)."""

import pytest
import pytest_asyncio
import sqlalchemy as sa

from remy_api.db import _apply_additive_migrations, get_session_factory
from remy_api.recipes import store
from remy_api.recipes.schemas import ParsedIngredient, ParsedRecipe, normalize_tags
from remy_api.user_service import create_user

USERNAME = "librarian"
PASSWORD = "sup3r-secret-pw"


@pytest.fixture(autouse=True)
def _reset_fts_cache():
    store._fts_available = None
    yield
    store._fts_available = None


@pytest_asyncio.fixture
async def auth(client):
    factory = get_session_factory()
    async with factory() as s:
        await create_user(s, USERNAME, PASSWORD)
    resp = await client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    return client, {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _make(title: str) -> str:
    factory = get_session_factory()
    async with factory() as s:
        user_id = (await s.execute(sa.text("SELECT id FROM users WHERE username = :u"), {"u": USERNAME})).scalar_one()
        recipe = await store.create_recipe(
            s,
            user_id,
            ParsedRecipe(title=title, ingredients=[ParsedIngredient(raw="1 cup rice")], instructions=["Cook."]),
        )
        return recipe.id


async def test_new_recipe_has_empty_library_fields(auth):
    client, headers = auth
    rid = await _make("Plain Rice")
    body = (await client.get(f"/recipes/{rid}", headers=headers)).json()
    assert body["is_favorite"] is False
    assert body["rating"] is None
    assert body["notes"] is None
    assert body["tags"] == []
    assert body["cooked_count"] == 0
    summary = (await client.get("/recipes", headers=headers)).json()[0]
    assert {"is_favorite", "rating", "tags", "cooked_count"} <= summary.keys()
    assert "notes" not in summary  # detail-only


async def test_favorite_rating_notes_tags_roundtrip(auth):
    client, headers = auth
    rid = await _make("Weeknight Curry")
    resp = await client.put(
        f"/recipes/{rid}",
        json={
            "is_favorite": True,
            "rating": 4,
            "notes": "Half the salt.",
            "tags": [" Weeknight ", "thai", "weeknight"],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_favorite"] is True
    assert body["rating"] == 4
    assert body["notes"] == "Half the salt."
    assert body["tags"] == ["Weeknight", "thai"]  # trimmed, case-insensitive dedupe

    # A partial update leaves the other fields alone; null clears rating/notes
    # but is ignored for favorite/tags (never-null columns).
    resp = await client.put(
        f"/recipes/{rid}", json={"rating": None, "notes": "  ", "is_favorite": None, "tags": None}, headers=headers
    )
    body = resp.json()
    assert body["rating"] is None
    assert body["notes"] is None  # blank notes clear
    assert body["is_favorite"] is True
    assert body["tags"] == ["Weeknight", "thai"]
    assert body["title"] == "Weeknight Curry"


@pytest.mark.parametrize("rating", [0, 6])
async def test_rating_out_of_range_rejected(auth, rating):
    client, headers = auth
    rid = await _make("Toast")
    resp = await client.put(f"/recipes/{rid}", json={"rating": rating}, headers=headers)
    assert resp.status_code == 422


def test_tag_limits():
    with pytest.raises(ValueError):
        normalize_tags(["x" * 41])
    with pytest.raises(ValueError):
        normalize_tags([f"t{i}" for i in range(21)])
    assert normalize_tags(["", "  ", "A  b"]) == ["A b"]


async def test_tags_endpoint_counts_and_search_finds_tags(auth):
    client, headers = auth
    a = await _make("Pad Thai")
    b = await _make("Green Curry")
    c = await _make("Oatmeal")
    await client.put(f"/recipes/{a}", json={"tags": ["Thai", "Weeknight"]}, headers=headers)
    await client.put(f"/recipes/{b}", json={"tags": ["thai"]}, headers=headers)
    await client.put(f"/recipes/{c}", json={"tags": ["Breakfast"]}, headers=headers)

    tags = (await client.get("/recipes/tags", headers=headers)).json()
    assert tags[0] == {"name": "Thai", "count": 2}  # case-insensitive count, first-seen spelling on ties
    assert {t["name"] for t in tags} == {"Thai", "Weeknight", "Breakfast"}

    found = (await client.get("/recipes", params={"q": "weeknight"}, headers=headers)).json()
    assert [r["id"] for r in found] == [a]


async def test_cooked_increments_count(auth):
    client, headers = auth
    rid = await _make("Lentil Soup")
    await client.post(f"/recipes/{rid}/cooked", headers=headers)
    body = (await client.post(f"/recipes/{rid}/cooked", headers=headers)).json()
    assert body["cooked_count"] == 2
    assert body["last_cooked_at"] is not None


def test_additive_migration_backfills_cooked_count(tmp_path):
    """An existing DB without the new columns gains them; previously-cooked recipes count as 1."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE recipes (id VARCHAR(36) PRIMARY KEY, title VARCHAR(512), last_cooked_at DATETIME)"
        )
        conn.exec_driver_sql("INSERT INTO recipes VALUES ('a', 'Cooked', '2026-07-01 00:00:00'), ('b', 'New', NULL)")
        _apply_additive_migrations(conn)
        _apply_additive_migrations(conn)  # idempotent
        rows = conn.exec_driver_sql("SELECT id, cooked_count, is_favorite, tags FROM recipes ORDER BY id").all()
    assert rows == [("a", 1, 0, "[]"), ("b", 0, 0, "[]")]
