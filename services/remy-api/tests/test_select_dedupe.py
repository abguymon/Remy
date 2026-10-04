"""Picking a web recipe that's already in the cookbook reuses it instead of saving a copy."""

import pytest

from remy_api.db import get_session_factory
from remy_api.planner import deps, select_step
from remy_api.recipes import store
from remy_api.recipes.schemas import ParsedIngredient, ParsedRecipe
from remy_api.user_service import create_user

URL = "https://www.hot-thai-kitchen.com/massaman-curry/"


@pytest.fixture(autouse=True)
def _reset_fts_cache():
    store._fts_available = None
    yield
    store._fts_available = None


@pytest.mark.parametrize(
    "variant",
    [
        URL,
        "https://hot-thai-kitchen.com/massaman-curry",
        "https://www.hot-thai-kitchen.com/Massaman-Curry/?utm_source=x#tasty-recipes-jump",
    ],
)
def test_normalize_recipe_url_ignores_www_slash_query_fragment(variant):
    assert store.normalize_recipe_url(variant) == "hot-thai-kitchen.com/massaman-curry"


async def test_save_web_recipe_reuses_existing_source_url(client, monkeypatch):
    factory = get_session_factory()
    async with factory() as s:
        user_id = (await create_user(s, "deduper", "sup3r-secret-pw")).id
        saved = await store.create_recipe(
            s,
            user_id,
            ParsedRecipe(
                title="Massaman Curry",
                source_url=URL,
                ingredients=[ParsedIngredient(raw="2 lb chicken")],
                instructions=["Simmer."],
            ),
        )

    async def must_not_scrape(*args, **kwargs):
        raise AssertionError("scraped a URL that is already saved")

    monkeypatch.setattr(deps, "scrape_recipe", must_not_scrape)
    async with factory() as s:
        rid, title = await select_step._save_web_recipe(
            s, user_id, "https://hot-thai-kitchen.com/massaman-curry?share=1"
        )
    assert (rid, title) == (saved.id, "Massaman Curry")


async def test_other_users_recipe_is_not_reused(client, monkeypatch):
    factory = get_session_factory()
    async with factory() as s:
        owner_id = (await create_user(s, "owner2", "sup3r-secret-pw")).id
        other_id = (await create_user(s, "other2", "sup3r-secret-pw")).id
        await store.create_recipe(
            s, owner_id, ParsedRecipe(title="Theirs", source_url=URL, ingredients=[], instructions=[])
        )
        assert await store.find_by_source_url(s, other_id, URL) is None
