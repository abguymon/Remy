"""Keyless unit tests: render functions, output-schema validation, regex prefilter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from remy_api.llm import RenderedPrompt
from remy_api.prompts import (
    ingredient_parsing,
    listicle_filter,
    meal_extraction,
    product_extraction,
    product_ranking,
    saved_recipe_relevance,
)
from remy_api.prompts.listicle_filter import (
    SearchCandidate,
    is_listicle_title,
    prefilter_listicles,
)
from remy_api.prompts.rules import PRODUCT_RULES

FIXTURES = Path(__file__).parent / "prompts" / "fixtures"


# --- render functions produce a valid RenderedPrompt --------------------------


def test_meal_extraction_render():
    p = meal_extraction.render(meal_extraction.MealExtractionInput(text="tacos on friday"))
    assert isinstance(p, RenderedPrompt)
    assert p.prompt_id == "meal_extraction" and p.version >= 1
    assert "tacos on friday" in p.user
    assert p.temperature == 0.0


def test_saved_recipe_relevance_render_is_indexed():
    inp = saved_recipe_relevance.SavedRecipeRelevanceInput(
        query="pasta carbonara",
        is_specific=True,
        candidates=[
            saved_recipe_relevance.RecipeCandidate(title="Spaghetti Carbonara", key_ingredients=["egg", "pancetta"])
        ],
    )
    p = saved_recipe_relevance.render(inp)
    assert '"index": 0' in p.user and "Spaghetti Carbonara" in p.user


def test_listicle_render_carries_url_and_snippet():
    inp = listicle_filter.ListicleFilterInput(
        query="tacos",
        candidates=[SearchCandidate(title="Best Tacos", url="https://x/tacos", snippet="yum")],
    )
    p = listicle_filter.render(inp)
    assert "https://x/tacos" in p.user and "yum" in p.user


def test_ingredient_parsing_render_indexes_lines():
    p = ingredient_parsing.render(ingredient_parsing.IngredientParsingInput(lines=["1 cup black beans", "2 limes"]))
    assert '"index": 0' in p.user and '"index": 1' in p.user
    assert "black beans" in p.user


def test_product_extraction_shares_one_rules_block():
    batch = product_extraction.render_batch(
        product_extraction.ProductExtractionInput(
            lines=[product_extraction.ParsedLine(food="black bean", quantity=1, unit="cup")]
        )
    )
    single = product_extraction.render_single(product_extraction.ParsedLine(food="black bean"))
    # Same canonical rules text in both system prompts (Appendix A.4 no-drift fix).
    assert PRODUCT_RULES in batch.system
    assert PRODUCT_RULES in single.system
    assert batch.prompt_id != single.prompt_id


def test_product_ranking_render_includes_price_and_target_size():
    inp = product_ranking.ProductRankingInput(
        search_term="canned black beans",
        target_size="15 oz",
        products=[
            product_ranking.RankableProduct(
                description="Kroger Black Beans", size="15 oz", price=1.19, department="Canned"
            )
        ],
    )
    p = product_ranking.render(inp)
    assert "1.19" in p.user and "15 oz" in p.user and "Target size" in p.user


# --- output-schema validation -------------------------------------------------


def test_meal_output_schema_validates():
    out = meal_extraction.MealExtractionOutput.model_validate(
        {"meals": [{"query": "salmon dinner", "verbatim": "some salmon thing", "is_specific": False, "url": None}]}
    )
    assert out.meals[0].is_specific is False


def test_product_extraction_output_rejects_bad_quantity():
    with pytest.raises(ValidationError):
        product_extraction.ExtractedProduct(search_term="salt", package_quantity=0, confidence=0.5)


def test_product_ranking_output_none_acceptable():
    out = product_ranking.ProductRankingOutput.model_validate({"ranked": [], "none_acceptable": True})
    assert out.none_acceptable is True


def test_ranking_confidence_bounds():
    with pytest.raises(ValidationError):
        product_extraction.ExtractedProduct(search_term="x", package_quantity=1, confidence=1.5)


# --- regex prefilter (no LLM) against fixtures --------------------------------


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_regex_prefilter_matches_fixture_expectations():
    data = _load("search_results.json")
    for case in data["cases"]:
        for cand in case["candidates"]:
            assert is_listicle_title(cand["title"]) == cand["is_listicle"], cand["title"]


def test_prefilter_partitions_indices():
    cands = [
        SearchCandidate(title="15 Best Tacos"),
        SearchCandidate(title="Easy Chicken Tikka Masala"),
        SearchCandidate(title="10 Ways to Cook Salmon"),
    ]
    survivors, dropped = prefilter_listicles(cands)
    assert survivors == [1] and dropped == [0, 2]


def test_prefilter_does_not_drop_ingredient_count_titles():
    # "5-Ingredient ..." is a real recipe, not a roundup.
    assert is_listicle_title("5-Ingredient Honey Garlic Salmon") is False
    assert is_listicle_title("Five Cheese Lasagna") is False
