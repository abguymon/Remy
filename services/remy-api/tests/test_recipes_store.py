"""Recipe store: CRUD, FTS search (ranking + scoping), ILIKE fallback."""

import pytest

from remy_api.recipes import store
from remy_api.recipes.schemas import IngredientInput, ParsedIngredient, ParsedRecipe, RecipeUpdate
from remy_api.user_service import create_user


def _recipe(title: str, foods: list[str], instructions=("Do it.",)) -> ParsedRecipe:
    return ParsedRecipe(
        title=title,
        source_url=f"https://example.com/{title.replace(' ', '-').lower()}",
        ingredients=[ParsedIngredient(raw=f, food=f) for f in foods],
        instructions=list(instructions),
    )


@pytest.fixture(autouse=True)
def _reset_fts_cache():
    """Each test re-probes FTS availability (isolates monkeypatched fallback)."""
    store._fts_available = None
    yield
    store._fts_available = None


async def _user(session, name="owner"):
    user = await create_user(session, name, "pw-123456")
    return user.id


async def test_create_and_get_roundtrip(session):
    uid = await _user(session)
    parsed = _recipe("Chicken Tikka Masala", ["chicken", "tomato", "garam masala"])
    created = await store.create_recipe(session, uid, parsed)
    assert created.slug == "chicken-tikka-masala"
    assert len(created.ingredients) == 3

    fetched = await store.get_recipe(session, uid, created.id)
    assert fetched.title == "Chicken Tikka Masala"
    assert fetched.ingredients[0].food == "chicken"


async def test_unique_slug_collision(session):
    uid = await _user(session)
    a = await store.create_recipe(session, uid, _recipe("Tacos", ["beef"]))
    b = await store.create_recipe(session, uid, _recipe("Tacos", ["fish"]))
    assert a.slug == "tacos"
    assert b.slug == "tacos-2"


async def test_search_matches_title_and_ingredient(session):
    uid = await _user(session)
    await store.create_recipe(session, uid, _recipe("Chicken Tikka Masala", ["chicken", "tomato"]))
    await store.create_recipe(session, uid, _recipe("Salmon Bowls", ["salmon", "rice", "avocado"]))
    await store.create_recipe(session, uid, _recipe("Street Tacos", ["beef", "cilantro", "lime"]))

    by_title = await store.search_recipes(session, "tikka", user_id=uid)
    assert [r.title for r in by_title] == ["Chicken Tikka Masala"]

    # Ingredient-only match (word not in any title).
    by_ingredient = await store.search_recipes(session, "avocado", user_id=uid)
    assert [r.title for r in by_ingredient] == ["Salmon Bowls"]


async def test_search_ranking_prefers_stronger_match(session):
    uid = await _user(session)
    # "chicken" appears in the title of one and only an ingredient of the other.
    await store.create_recipe(session, uid, _recipe("Chicken Curry", ["chicken", "coconut"]))
    await store.create_recipe(session, uid, _recipe("Garden Salad", ["lettuce", "grilled chicken"]))
    results = await store.search_recipes(session, "chicken", user_id=uid)
    assert len(results) == 2
    # Title match should rank first.
    assert results[0].title == "Chicken Curry"


async def test_search_is_user_scoped(session):
    owner = await _user(session, "owner")
    other = await _user(session, "intruder")
    await store.create_recipe(session, owner, _recipe("Owner Tikka", ["chicken"]))
    await store.create_recipe(session, other, _recipe("Intruder Tikka", ["chicken"]))

    owner_hits = await store.search_recipes(session, "tikka", user_id=owner)
    assert [r.title for r in owner_hits] == ["Owner Tikka"]
    other_hits = await store.search_recipes(session, "tikka", user_id=other)
    assert [r.title for r in other_hits] == ["Intruder Tikka"]


async def test_empty_query_returns_recent(session):
    uid = await _user(session)
    await store.create_recipe(session, uid, _recipe("A", ["x"]))
    await store.create_recipe(session, uid, _recipe("B", ["y"]))
    results = await store.search_recipes(session, "   ", user_id=uid)
    assert len(results) == 2


async def test_ilike_fallback_when_no_fts(session, monkeypatch):
    async def no_fts(_session):
        return False

    monkeypatch.setattr(store, "_ensure_fts", no_fts)
    uid = await _user(session)
    await store.create_recipe(session, uid, _recipe("Chicken Tikka Masala", ["chicken", "tomato"]))
    await store.create_recipe(session, uid, _recipe("Salmon Bowls", ["salmon", "avocado"]))

    hits = await store.search_recipes(session, "avocado", user_id=uid)
    assert [r.title for r in hits] == ["Salmon Bowls"]
    title_hits = await store.search_recipes(session, "tikka", user_id=uid)
    assert [r.title for r in title_hits] == ["Chicken Tikka Masala"]


async def test_update_replaces_ingredients_and_resyncs_search(session):
    uid = await _user(session)
    created = await store.create_recipe(session, uid, _recipe("Mystery Dish", ["placeholder"]))
    updated = await store.update_recipe(
        session,
        uid,
        created.id,
        RecipeUpdate(
            title="Beef Stew",
            ingredients=[IngredientInput(raw="beef", food="beef"), IngredientInput(raw="carrot", food="carrot")],
        ),
    )
    assert updated.title == "Beef Stew"
    assert [i.food for i in updated.ingredients] == ["beef", "carrot"]
    # Old term no longer matches; new one does.
    assert await store.search_recipes(session, "placeholder", user_id=uid) == []
    assert [r.title for r in await store.search_recipes(session, "carrot", user_id=uid)] == ["Beef Stew"]


async def test_mark_cooked_stamps_timestamp(session):
    uid = await _user(session)
    created = await store.create_recipe(session, uid, _recipe("Pasta", ["pasta"]))
    assert created.last_cooked_at is None
    cooked = await store.mark_cooked(session, uid, created.id)
    assert cooked.last_cooked_at is not None


async def test_delete_removes_recipe_and_from_search(session):
    uid = await _user(session)
    created = await store.create_recipe(session, uid, _recipe("Deletable", ["thing"]))
    await store.delete_recipe(session, uid, created.id)
    from remy_api.errors import NotFoundError

    with pytest.raises(NotFoundError):
        await store.get_recipe(session, uid, created.id)
    assert await store.search_recipes(session, "thing", user_id=uid) == []


async def test_get_recipe_cross_user_is_not_found(session):
    owner = await _user(session, "owner")
    other = await _user(session, "other")
    created = await store.create_recipe(session, owner, _recipe("Private", ["secret"]))
    from remy_api.errors import NotFoundError

    with pytest.raises(NotFoundError):
        await store.get_recipe(session, other, created.id)
