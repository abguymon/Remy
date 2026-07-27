"""Regression tests for ingredient lines that expand into several list items."""

from remy_api.planner import deps
from remy_api.planner.consolidation import consolidate
from remy_api.planner.listing import _parse_recipe_lines
from remy_api.prompts import ingredient_parsing
from remy_api.recipes import store
from remy_api.recipes.schemas import ParsedIngredient, ParsedRecipe
from remy_api.user_service import create_user


class _ToppingLLM:
    async def structured(self, prompt, schema):
        assert prompt.prompt_id == ingredient_parsing.PROMPT_ID
        foods = ["plain yogurt", "whipped cream", "maple syrup", "honey", "fresh fruit"]
        return ingredient_parsing.IngredientParsingOutput(
            ingredients=[
                ingredient_parsing.ParsedIngredient(
                    index=0,
                    food=food,
                    note="optional",
                )
                for food in foods
            ]
        )


async def test_parse_recipe_lines_expands_optional_toppings(session, monkeypatch):
    user = await create_user(session, "topping-owner", "sup3r-secret-pw")
    raw = (
        "Optional toppings for serving: plain/vanilla yogurt or whipped cream, "
        "additional maple syrup or honey for drizzling, and/or additional fresh fruit"
    )
    recipe = await store.create_recipe(
        session,
        user.id,
        ParsedRecipe(
            title="Blueberry Baked Oatmeal",
            ingredients=[ParsedIngredient(raw=raw, food="topping")],
            instructions=["Bake."],
        ),
    )
    monkeypatch.setattr(deps, "get_llm_client", lambda: _ToppingLLM())

    contributions = await _parse_recipe_lines(session, recipe.id, recipe.title)

    assert [item.food for item in contributions] == [
        "plain yogurt",
        "whipped cream",
        "maple syrup",
        "honey",
        "fresh fruit",
    ]
    assert all(item.raw == raw and item.note == "optional" for item in contributions)
    assert recipe.ingredients[0].food is None


class _CombinationLLM:
    async def structured(self, prompt, schema):
        assert prompt.prompt_id == ingredient_parsing.PROMPT_ID
        return ingredient_parsing.IngredientParsingOutput(
            ingredients=[
                ingredient_parsing.ParsedIngredient(
                    index=0,
                    quantity=0.5,
                    unit="cup",
                    food=food,
                    note="combination totaling 1/2 cup",
                )
                for food in ("dill", "mint", "parsley")
            ]
        )


async def test_parse_recipe_lines_expands_explicit_combination_as_selectable_lines(session, monkeypatch):
    user = await create_user(session, "combination-owner", "sup3r-secret-pw")
    raw = "½ cup fresh dill, mint or parsley leaves (or any combination), torn if large"
    recipe = await store.create_recipe(
        session,
        user.id,
        ParsedRecipe(
            title="Lemony Orzo With Asparagus and Garlic Bread Crumbs",
            ingredients=[ParsedIngredient(raw=raw, quantity=0.5, unit="cup", food="dill")],
            instructions=["Cook."],
        ),
    )
    monkeypatch.setattr(deps, "get_llm_client", lambda: _CombinationLLM())

    contributions = await _parse_recipe_lines(session, recipe.id, recipe.title)
    lines = consolidate(contributions)

    assert [line.food for line in lines] == ["dill", "mint", "parsley"]
    assert [line.display for line in lines] == ["dill", "mint", "parsley"]
    assert all(line.quantity is None and line.unit is None for line in lines)
    assert all(item.note == "combination totaling 1/2 cup" for item in contributions)
