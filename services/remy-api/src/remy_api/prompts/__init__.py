"""Versioned prompt library (T4).

Each prompt module exposes typed ``*Input``/``*Output`` Pydantic models and a
``render(input) -> RenderedPrompt`` function. Business logic imports these and
runs them through :func:`remy_api.llm.get_llm_client` — no prompt text lives in
business logic (V2_PLAN instruction 5).

Prompt map:
- P1  meal_extraction          -> {meals: [{query, verbatim, is_specific, url?}]}
- P2  saved_recipe_relevance   -> {relevant_indices}
- P3  listicle_filter          -> {keep_indices}  (+ regex prefilter)
- P4a ingredient_parsing       -> {ingredients: [{quantity, unit, food, note}]}
- P4  product_extraction       -> {items: [{index, products: [...]}]} (+ single fallback)
- P5  product_ranking          -> {ranked: [{index, reason}], none_acceptable}
"""

from remy_api.prompts import (
    ingredient_parsing,
    listicle_filter,
    meal_extraction,
    product_extraction,
    product_ranking,
    receipt_items,
    recipe_from_images,
    saved_recipe_relevance,
)
from remy_api.prompts.base import RenderedPrompt
from remy_api.prompts.rules import PRODUCT_RULES

__all__ = [
    "RenderedPrompt",
    "PRODUCT_RULES",
    "meal_extraction",
    "saved_recipe_relevance",
    "listicle_filter",
    "ingredient_parsing",
    "product_extraction",
    "product_ranking",
    "receipt_items",
    "recipe_from_images",
]
