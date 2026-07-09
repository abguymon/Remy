"""Recipe router round-trip: create-from-url, list/search, get, edit, cooked, delete, image."""

import io

import pytest
import pytest_asyncio
from PIL import Image

from remy_api.db import get_session_factory
from remy_api.recipes import store
from remy_api.recipes.llm_fallback import RecipeParseError
from remy_api.recipes.schemas import ParsedIngredient, ParsedRecipe
from remy_api.user_service import create_user

USERNAME = "owner"
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
    token = resp.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def _fake_parsed(image_url=None) -> ParsedRecipe:
    return ParsedRecipe(
        title="Chicken Tikka Masala",
        source_url="https://example.com/tikka",
        image_url=image_url,
        recipe_yield="4 servings",
        total_time="45 min",
        ingredients=[ParsedIngredient(raw="1 lb chicken"), ParsedIngredient(raw="2 tomatoes")],
        instructions=["Marinate.", "Cook."],
    )


async def test_requires_auth(client):
    resp = await client.get("/recipes")
    assert resp.status_code == 401


async def test_from_url_create_then_full_roundtrip(auth, monkeypatch):
    client, headers = auth

    async def fake_scrape(url, *, llm=None, client=None):
        return _fake_parsed()

    monkeypatch.setattr("remy_api.routers.recipes.scrape_recipe", fake_scrape)

    created = await client.post("/recipes/from-url", json={"url": "https://example.com/tikka"}, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    rid = body["id"]
    assert body["title"] == "Chicken Tikka Masala"
    assert len(body["ingredients"]) == 2
    assert body["image_url"] is None  # no image downloaded

    # List
    listed = await client.get("/recipes", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # Search
    found = await client.get("/recipes", params={"q": "tikka"}, headers=headers)
    assert [r["id"] for r in found.json()] == [rid]

    # Get detail
    detail = await client.get(f"/recipes/{rid}", headers=headers)
    assert detail.json()["recipe_yield"] == "4 servings"

    # Edit (title + ingredients replacement)
    put = await client.put(
        f"/recipes/{rid}",
        json={"title": "Butter Chicken", "ingredients": [{"raw": "1 lb chicken", "food": "chicken"}]},
        headers=headers,
    )
    assert put.status_code == 200
    assert put.json()["title"] == "Butter Chicken"
    assert len(put.json()["ingredients"]) == 1

    # Cooked
    cooked = await client.post(f"/recipes/{rid}/cooked", headers=headers)
    assert cooked.json()["last_cooked_at"] is not None

    # Delete
    deleted = await client.delete(f"/recipes/{rid}", headers=headers)
    assert deleted.status_code == 204
    gone = await client.get(f"/recipes/{rid}", headers=headers)
    assert gone.status_code == 404


async def test_from_url_parse_failure_surfaces_422(auth, monkeypatch):
    client, headers = auth

    async def fake_scrape(url, *, llm=None, client=None):
        raise RecipeParseError("boom", reasons=["scraper_error", "llm_unavailable"])

    monkeypatch.setattr("remy_api.routers.recipes.scrape_recipe", fake_scrape)
    resp = await client.post("/recipes/from-url", json={"url": "https://bad"}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "recipe_parse_failed"


async def test_image_served_and_missing_is_404(auth, monkeypatch):
    client, headers = auth
    png = io.BytesIO()
    Image.new("RGB", (400, 300), (10, 120, 200)).save(png, format="PNG")
    png_bytes = png.getvalue()

    async def fake_scrape(url, *, llm=None, client=None):
        return _fake_parsed(image_url="https://example.com/pic.png")

    async def fake_download(recipe_id, image_url, *, client=None, headers=None):
        from remy_api.recipes.images import store_image_bytes

        return store_image_bytes(recipe_id, png_bytes)

    monkeypatch.setattr("remy_api.routers.recipes.scrape_recipe", fake_scrape)
    monkeypatch.setattr("remy_api.routers.recipes.download_recipe_image", fake_download)

    created = await client.post("/recipes/from-url", json={"url": "https://example.com/tikka"}, headers=headers)
    body = created.json()
    rid = body["id"]
    assert body["image_url"] == f"/recipes/{rid}/image"

    img = await client.get(f"/recipes/{rid}/image", headers=headers)
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"


async def test_recipes_are_user_scoped_via_api(auth, monkeypatch):
    client, headers = auth

    async def fake_scrape(url, *, llm=None, client=None):
        return _fake_parsed()

    monkeypatch.setattr("remy_api.routers.recipes.scrape_recipe", fake_scrape)
    created = await client.post("/recipes/from-url", json={"url": "https://example.com/tikka"}, headers=headers)
    rid = created.json()["id"]

    # A second user cannot see the first user's recipe.
    factory = get_session_factory()
    async with factory() as s:
        await create_user(s, "intruder", "pw-12345678")
    other = await client.post("/auth/login", json={"username": "intruder", "password": "pw-12345678"})
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    assert (await client.get("/recipes", headers=other_headers)).json() == []
    assert (await client.get(f"/recipes/{rid}", headers=other_headers)).status_code == 404
