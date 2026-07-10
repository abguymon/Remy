"""Live prompt evals (``-m prompts``).

Skipped automatically when no LLM key is present (see conftest). Assertions are
semantic, not exact-string, so they tolerate reasonable model variation while
catching regressions in the behaviors Appendix A calls out.
"""

from __future__ import annotations

import base64

import pytest

from remy_api.llm.prompt import ImagePart
from remy_api.prompts import (
    ingredient_parsing,
    listicle_filter,
    meal_extraction,
    product_extraction,
    product_ranking,
    recipe_from_images,
    saved_recipe_relevance,
)
from remy_api.prompts.listicle_filter import ListicleFilterInput, SearchCandidate

from .conftest import load_fixture

pytestmark = pytest.mark.prompts


# --- P1 meal extraction -------------------------------------------------------


async def test_p1_preserves_vagueness_and_strips_chatter(llm_client):
    out = await llm_client.structured(
        meal_extraction.render(
            meal_extraction.MealExtractionInput(
                text="chicken tikka masala, some kind of salmon dish, and tacos on Friday"
            )
        ),
        meal_extraction.MealExtractionOutput,
    )
    queries = [m.query.lower() for m in out.meals]
    assert len(out.meals) == 3
    # vague salmon stays vague, not invented into a specific dish
    salmon = next(m for m in out.meals if "salmon" in m.query.lower())
    assert salmon.is_specific is False
    # scheduling chatter stripped from the query
    tacos = next(m for m in out.meals if "taco" in m.query.lower())
    assert "friday" not in tacos.query.lower()
    assert any("tikka" in q for q in queries)


async def test_p1_extracts_inline_url(llm_client):
    out = await llm_client.structured(
        meal_extraction.render(
            meal_extraction.MealExtractionInput(text="make this https://cooking.example.com/lasagna and also tacos")
        ),
        meal_extraction.MealExtractionOutput,
    )
    assert any(m.url and "lasagna" in m.url for m in out.meals)
    assert any("taco" in (m.query or "").lower() for m in out.meals)


async def test_p1_empty_when_no_food(llm_client):
    out = await llm_client.structured(
        meal_extraction.render(meal_extraction.MealExtractionInput(text="hello, how are you today?")),
        meal_extraction.MealExtractionOutput,
    )
    assert out.meals == []


# --- P2 saved-recipe relevance ------------------------------------------------


async def test_p2_strictness(llm_client):
    inp = saved_recipe_relevance.SavedRecipeRelevanceInput(
        query="farro tomato mozzarella bake",
        is_specific=True,
        candidates=[
            saved_recipe_relevance.RecipeCandidate(
                title="Coconut Fish and Tomato Bake", key_ingredients=["cod", "coconut milk", "tomato"]
            ),
            saved_recipe_relevance.RecipeCandidate(
                title="Farro Caprese Bake", key_ingredients=["farro", "tomato", "mozzarella"]
            ),
        ],
    )
    out = await llm_client.structured(
        saved_recipe_relevance.render(inp), saved_recipe_relevance.SavedRecipeRelevanceOutput
    )
    assert 1 in out.relevant_indices
    assert 0 not in out.relevant_indices


# --- P3 listicle filter -------------------------------------------------------


async def test_p3_drops_listicles_and_categories(llm_client):
    case = load_fixture("search_results.json")["cases"][0]  # chicken tikka masala
    cands = [SearchCandidate(title=c["title"], url=c["url"], snippet=c["snippet"]) for c in case["candidates"]]
    out = await llm_client.structured(
        listicle_filter.render(ListicleFilterInput(query=case["query"], candidates=cands)),
        listicle_filter.ListicleFilterOutput,
    )
    kept_titles = {cands[i].title for i in out.keep_indices if 0 <= i < len(cands)}
    assert "Easy Chicken Tikka Masala" in kept_titles
    assert not any("15 Best" in t for t in kept_titles)


# --- P4a ingredient parsing ---------------------------------------------------


async def test_p4a_canonicalizes_food(llm_client):
    out = await llm_client.structured(
        ingredient_parsing.render(
            ingredient_parsing.IngredientParsingInput(lines=["6 scallions, thinly sliced", "3 cloves garlic, minced"])
        ),
        ingredient_parsing.IngredientParsingOutput,
    )
    by_index = {p.index: p for p in out.ingredients}
    assert by_index[1].food == "garlic"
    assert by_index[1].unit == "clove"


# --- P4 product extraction ----------------------------------------------------


async def test_p4_black_beans_default_canned(llm_client):
    out = await llm_client.structured(
        product_extraction.render_batch(
            product_extraction.ProductExtractionInput(
                lines=[product_extraction.ParsedLine(quantity=1, unit="cup", food="black bean")]
            )
        ),
        product_extraction.ProductExtractionOutput,
    )
    term = out.items[0].products[0].search_term.lower()
    assert "black bean" in term and "canned" in term
    assert out.items[0].products[0].package_quantity == 1


async def test_p4_multi_product_expansion(llm_client):
    out = await llm_client.structured(
        product_extraction.render_batch(
            product_extraction.ProductExtractionInput(
                lines=[product_extraction.ParsedLine(food="salt and pepper", note="to taste")]
            )
        ),
        product_extraction.ProductExtractionOutput,
    )
    assert len(out.items[0].products) >= 2


async def test_p4_or_is_a_single_alternative(llm_client):
    """A plain 'or' between options means ALTERNATIVES: extract exactly one
    product (the first-listed option), not one per option (real bug report:
    russet-or-yukon potatoes produced two bags; milk-or-cream produced both).
    """
    out = await llm_client.structured(
        product_extraction.render_batch(
            product_extraction.ProductExtractionInput(
                lines=[
                    product_extraction.ParsedLine(quantity=4, unit="lb", food="potato", note="russet or Yukon gold"),
                    product_extraction.ParsedLine(quantity=1, unit="cup", food="milk", note="or cream"),
                ]
            )
        ),
        product_extraction.ProductExtractionOutput,
    )
    by_index = {it.index: it for it in out.items}
    potatoes = by_index[0].products
    assert len(potatoes) == 1, f"expected one potato product, got {[p.search_term for p in potatoes]}"
    assert "russet" in potatoes[0].search_term.lower()
    milk = by_index[1].products
    assert len(milk) == 1, f"expected one milk product, got {[p.search_term for p in milk]}"
    assert "milk" in milk[0].search_term.lower()
    assert "cream" not in milk[0].search_term.lower()


async def test_p4_explicit_mixture_keeps_all_options(llm_client):
    """The explicit-mixture exception: 'preferably a mixture' overrides 'or' and
    keeps every listed option."""
    out = await llm_client.structured(
        product_extraction.render_batch(
            product_extraction.ProductExtractionInput(
                lines=[product_extraction.ParsedLine(food="cilantro", note="parsley, or mint, preferably a mixture")]
            )
        ),
        product_extraction.ProductExtractionOutput,
    )
    terms = " ".join(p.search_term.lower() for p in out.items[0].products)
    assert len(out.items[0].products) >= 3
    assert "cilantro" in terms and "parsley" in terms and "mint" in terms


# --- P5 product ranking -------------------------------------------------------


async def test_p5_avoids_multipack_when_qty_one(llm_client):
    case = load_fixture("kroger_products.json")["cases"][0]  # canned black beans
    inp = product_ranking.ProductRankingInput(
        search_term=case["search_term"],
        package_quantity=case["package_quantity"],
        products=[product_ranking.RankableProduct(**p) for p in case["products"]],
    )
    out = await llm_client.structured(product_ranking.render(inp), product_ranking.ProductRankingOutput)
    assert out.ranked, "expected at least one ranked product"
    top = case["products"][out.ranked[0].index]["description"]
    assert "8-Pack" not in top and "Value" not in top


async def test_p5_none_acceptable_escape_hatch(llm_client):
    case = load_fixture("kroger_products.json")["cases"][4]  # saffron -> nothing acceptable
    inp = product_ranking.ProductRankingInput(
        search_term=case["search_term"],
        package_quantity=case["package_quantity"],
        products=[product_ranking.RankableProduct(**p) for p in case["products"]],
    )
    out = await llm_client.structured(product_ranking.render(inp), product_ranking.ProductRankingOutput)
    assert out.none_acceptable is True


# --- recipe_from_images (multimodal vision) -----------------------------------


def _synthetic_recipe_image(lines: list[str]) -> ImagePart:
    """Render short recipe text onto a plain image (no fixtures on disk)."""
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (900, 700), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 30
    for line in lines:
        draw.text((40, y), line, fill=(0, 0, 0))
        y += 34
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return ImagePart(media_type="image/jpeg", data=base64.b64encode(buf.getvalue()).decode("ascii"))


async def test_vision_transcribes_without_inventing(llm_client):
    from remy_api.recipes.schemas import LLMRecipeExtraction

    ingredients = [
        "2 cups all-purpose flour",
        "1 teaspoon baking soda",
        "1 cup unsalted butter",
        "3/4 cup brown sugar",
        "2 large eggs",
        "2 cups chocolate chips",
    ]
    lines = [
        "Best Chocolate Chip Cookies",
        "Makes 24 cookies",
        "",
        "Ingredients:",
        *ingredients,
        "",
        "Instructions:",
        "1. Cream butter and sugar.",
        "2. Mix in eggs, then dry ingredients.",
        "3. Fold in chocolate chips and bake at 375F for 10 minutes.",
    ]
    img = _synthetic_recipe_image(lines)
    out = await llm_client.structured(
        recipe_from_images.render(recipe_from_images.RecipeFromImagesInput(images=[img])),
        LLMRecipeExtraction,
    )
    assert out.found is True
    assert "chocolate chip cookies" in (out.title or "").lower()
    # Exact ingredient count — no invented or dropped lines.
    assert len(out.ingredients) == len(ingredients)
    joined = " ".join(out.ingredients).lower()
    assert "flour" in joined and "chocolate chips" in joined and "baking soda" in joined
    assert len(out.instructions) == 3


async def test_vision_reports_not_found_for_non_recipe(llm_client):
    from remy_api.recipes.schemas import LLMRecipeExtraction

    img = _synthetic_recipe_image(["Quarterly Sales Report", "Revenue up 12% year over year.", "Thanks, the team."])
    out = await llm_client.structured(
        recipe_from_images.render(recipe_from_images.RecipeFromImagesInput(images=[img])),
        LLMRecipeExtraction,
    )
    assert out.found is False
