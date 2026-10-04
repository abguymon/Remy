"""Ingredient sections + author-written unit conversions (recipes/enrich.py)."""

import json

import pytest
import pytest_asyncio
import sqlalchemy as sa

from remy_api.db import get_session_factory
from remy_api.recipes import store
from remy_api.recipes.enrich import align_sections, wprm_alternates
from remy_api.recipes.schemas import ParsedIngredient, ParsedRecipe
from remy_api.user_service import create_user


def _wprm_page(ingredients: list[dict]) -> str:
    data = {"recipe-1": {"id": 1, "ingredients": ingredients}}
    return f"<html><script>window.wprm_recipes = {json.dumps(data)};</script></html>"


def _item(amount, unit, name, notes="", conv_amount=None, conv_unit=None):
    item = {"type": "ingredient", "amount": amount, "unit": unit, "name": name, "notes": notes}
    if conv_amount is not None:
        item["converted"] = {"2": {"amount": conv_amount, "unit": conv_unit}}
    return item


LINES = ["245 g milk (warm)", "2 large eggs", "500 g all-purpose flour"]


def test_wprm_alternates_from_metric_primary():
    html = _wprm_page(
        [
            _item("245", "g", "milk", "warm", "1", "cup"),
            _item("2", "large", "eggs", "", "2", "large"),  # not a real conversion
            _item("500", "g", "all-purpose flour", "", "4", "cups"),
        ]
    )
    assert wprm_alternates(html, LINES) == ["1 cup milk (warm)", None, "4 cups all-purpose flour"]


def test_wprm_alternates_from_us_primary():
    html = _wprm_page([_item("1", "cup", "milk", "", "245", "g")])
    assert wprm_alternates(html, ["1 cup milk"]) == ["245 g milk"]


def test_wprm_alternates_count_or_name_mismatch_yields_none():
    html = _wprm_page([_item("245", "g", "milk", "", "1", "cup")])
    assert wprm_alternates(html, LINES) == [None, None, None]  # count mismatch
    assert wprm_alternates(html, ["245 g buttermilk"]) == ["1 cup milk"]  # name contained
    assert wprm_alternates(html, ["1 lb chicken"]) == [None]  # name not in line
    assert wprm_alternates("<html>no plugin</html>", ["1 lb chicken"]) == [None]


def test_align_sections():
    groups = [
        ("For the dough:", ["245 g milk (warm)", "2 large eggs"]),
        ("For the topping:", ["500 g all-purpose flour"]),
    ]
    assert align_sections(LINES, groups) == ["For the dough:", "For the dough:", "For the topping:"]
    # one unnamed group = no sections
    assert align_sections(LINES, [(None, LINES)]) == [None, None, None]
    # a line the groups don't contain → don't guess any section
    assert align_sections([*LINES, "salt"], groups) == [None, None, None, None]


@pytest.fixture(autouse=True)
def _reset_fts_cache():
    store._fts_available = None
    yield
    store._fts_available = None


@pytest_asyncio.fixture
async def auth(client):
    factory = get_session_factory()
    async with factory() as s:
        await create_user(s, "baker", "sup3r-secret-pw")
    resp = await client.post("/auth/login", json={"username": "baker", "password": "sup3r-secret-pw"})
    return client, {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_sections_and_alts_roundtrip_and_survive_unchanged_edits(auth):
    client, headers = auth
    factory = get_session_factory()
    async with factory() as s:
        user_id = (await s.execute(sa.text("SELECT id FROM users WHERE username='baker'"))).scalar_one()
        recipe = await store.create_recipe(
            s,
            user_id,
            ParsedRecipe(
                title="Rolls",
                ingredients=[
                    ParsedIngredient(raw="245 g milk", section="For the dough:", alt_raw="1 cup milk"),
                    ParsedIngredient(raw="220 g brown sugar", section="For the filling:", alt_raw="1 cup brown sugar"),
                ],
                instructions=["Bake."],
            ),
        )
    body = (await client.get(f"/recipes/{recipe.id}", headers=headers)).json()
    assert [(i["section"], i["alt_raw"]) for i in body["ingredients"]] == [
        ("For the dough:", "1 cup milk"),
        ("For the filling:", "1 cup brown sugar"),
    ]

    # Edit: first line unchanged keeps its conversion; the changed line loses it.
    resp = await client.put(
        f"/recipes/{recipe.id}",
        json={
            "ingredients": [
                {"raw": "245 g milk", "section": "For the dough:"},
                {"raw": "200 g brown sugar", "section": "For the filling:"},
                {"raw": "pinch of salt", "section": "  "},
            ]
        },
        headers=headers,
    )
    lines = resp.json()["ingredients"]
    assert [(i["raw"], i["section"], i["alt_raw"]) for i in lines] == [
        ("245 g milk", "For the dough:", "1 cup milk"),
        ("200 g brown sugar", "For the filling:", None),
        ("pinch of salt", None, None),
    ]
