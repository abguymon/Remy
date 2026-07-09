"""Mealie import against a mocked Mealie API (offline)."""

import io

import httpx
import pytest
from PIL import Image

from remy_api.recipes import store
from remy_api.recipes.mealie_import import import_mealie, map_recipe
from remy_api.user_service import create_user

BASE = "https://mealie.local"


@pytest.fixture(autouse=True)
def _reset_fts_cache():
    store._fts_available = None
    yield
    store._fts_available = None


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (40, 160, 90)).save(buf, format="PNG")
    return buf.getvalue()


_RECIPES = {
    "chicken-tikka-masala": {
        "id": "id-tikka",
        "slug": "chicken-tikka-masala",
        "name": "Chicken Tikka Masala",
        "image": "tikka.webp",
        "orgURL": "https://source.example/tikka",
        "recipeYield": "4 servings",
        "prepTime": 20,
        "cookTime": 40,
        "totalTime": 60,
        "recipeIngredient": [
            {"quantity": 1, "unit": "lb", "food": "chicken", "originalText": "1 lb chicken thighs"},
            {"note": "2 cups tomato puree", "originalText": "2 cups tomato puree"},
        ],
        "recipeInstructions": [
            {"text": "Marinate the chicken."},
            {"text": "Simmer in sauce."},
        ],
    },
    "salmon-bowls": {
        "id": "id-salmon",
        "slug": "salmon-bowls",
        "name": "Salmon Bowls",
        "image": None,
        "orgURL": None,
        "recipeYield": "2 servings",
        "recipeIngredient": [{"originalText": "1 salmon fillet"}],
        "recipeInstructions": [{"text": "Cook and assemble."}],
    },
}


def _make_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/recipes":
            page = int(request.url.params.get("page", "1"))
            if page == 1:
                items = [{"slug": s} for s in _RECIPES]
                return httpx.Response(200, json={"items": items, "total_pages": 1})
            return httpx.Response(200, json={"items": [], "total_pages": 1})
        if path.startswith("/api/recipes/"):
            slug = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json=_RECIPES[slug])
        if "/api/media/recipes/" in path:
            return httpx.Response(200, content=_png(), headers={"Content-Type": "image/webp"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_map_recipe_drops_parsed_fields_keeps_raw():
    parsed, slug, image_url = map_recipe(_RECIPES["chicken-tikka-masala"], BASE)
    assert slug == "chicken-tikka-masala"
    assert parsed.title == "Chicken Tikka Masala"
    assert parsed.source_url == "https://source.example/tikka"
    assert parsed.total_time == "1 hr"
    # Raw lines retained; parsed components deliberately left null (planner P4a).
    assert [i.raw for i in parsed.ingredients] == ["1 lb chicken thighs", "2 cups tomato puree"]
    assert all(i.food is None and i.quantity is None for i in parsed.ingredients)
    assert image_url == f"{BASE}/api/media/recipes/id-tikka/images/original.webp"


async def test_import_creates_recipes_and_images(session):
    user = await create_user(session, "owner", "pw-123456")
    async with httpx.AsyncClient(base_url=BASE, transport=_make_transport()) as client:
        stats = await import_mealie(session, user.id, BASE, "api-key", client=client)
    assert stats.imported == 2
    assert stats.failed == 0

    recipes = await store.list_recipes(session, user.id)
    titles = {r.title for r in recipes}
    assert titles == {"Chicken Tikka Masala", "Salmon Bowls"}
    tikka = next(r for r in recipes if r.mealie_slug == "chicken-tikka-masala")
    assert tikka.image_path is not None  # image downloaded + stored

    # Searchable via FTS using raw ingredient text (food fields are null).
    hits = await store.search_recipes(session, "tomato", user_id=user.id)
    assert [r.title for r in hits] == ["Chicken Tikka Masala"]


async def test_import_is_idempotent(session):
    user = await create_user(session, "owner", "pw-123456")
    async with httpx.AsyncClient(base_url=BASE, transport=_make_transport()) as client:
        first = await import_mealie(session, user.id, BASE, "k", client=client)
        second = await import_mealie(session, user.id, BASE, "k", client=client)
    assert first.imported == 2
    assert second.imported == 0
    assert second.skipped == 2
    assert len(await store.list_recipes(session, user.id)) == 2


async def test_dry_run_writes_nothing(session):
    user = await create_user(session, "owner", "pw-123456")
    async with httpx.AsyncClient(base_url=BASE, transport=_make_transport()) as client:
        stats = await import_mealie(session, user.id, BASE, "k", dry_run=True, client=client)
    assert stats.imported == 2
    assert await store.list_recipes(session, user.id) == []
