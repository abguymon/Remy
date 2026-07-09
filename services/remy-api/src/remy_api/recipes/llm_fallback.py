"""LLM fallback interface for recipe parsing (T3 ⇄ T4 seam).

The scraper (``scraper.py``) parses with ``recipe-scrapers`` first. When that
fails or returns clearly incomplete data (no ingredients or no instructions), it
falls back to an LLM structured-output extraction over the fetched page text.

T4 owns the real provider-agnostic LLM client (`llm/`), whose single entrypoint
is ``structured(prompt_id, input, schema)`` (PRD §7.1). T3 must not import T4's
module, so we depend only on the :class:`StructuredLLM` Protocol below, matching
that signature. The fallback is cleanly *skippable*: when no client is wired
(``llm=None``), the scraper raises :class:`RecipeParseError` listing exactly what
was missing instead of guessing.

The real client is wired at both parse sites — ``planner.select_step`` and
``routers.recipes.create_recipe_from_url`` pass ``llm=get_prompt_id_llm()`` into
``scrape_recipe`` — and the ``recipe_parse_fallback`` prompt (schema
:class:`LLMRecipeExtraction`) is registered in the prompt library.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from remy_api.errors import APIError
from remy_api.recipes.schemas import LLMRecipeExtraction, ParsedIngredient, ParsedRecipe

T = TypeVar("T", bound=BaseModel)

# Prompt id the T4 library must register for the recipe-parse fallback.
RECIPE_PARSE_PROMPT_ID = "recipe_parse_fallback"


class RecipeParseError(APIError):
    """Raised when a recipe URL cannot be parsed into a usable recipe.

    Carries ``reasons`` — the specific failures (fetch error, no ingredients, no
    instructions, LLM unavailable) — so the API surfaces *why* rather than a bare
    "no results" (PRD §9.1: no silent failures).
    """

    status_code = 422
    code = "recipe_parse_failed"

    def __init__(self, message: str, *, reasons: list[str] | None = None) -> None:
        super().__init__(message)
        self.reasons = reasons or []


class StructuredLLM(Protocol):
    """Minimal T4 LLM-client surface the recipe fallback needs.

    Mirrors T4's planned ``structured(prompt_id, input, schema)`` entrypoint: run
    ``prompt_id`` with ``input`` and return an instance of ``schema`` validated by
    Pydantic (with T4's built-in retry-on-validation).
    """

    async def structured(self, prompt_id: str, input: dict, schema: type[T]) -> T:  # noqa: A002
        ...


async def llm_extract_recipe(
    llm: StructuredLLM,
    *,
    page_text: str,
    source_url: str,
) -> ParsedRecipe:
    """Extract a recipe from raw page text via T4's structured-output client.

    Returns a :class:`ParsedRecipe`; raises :class:`RecipeParseError` if the model
    reports the page is not a recipe or the result is still incomplete.
    """
    result = await llm.structured(
        RECIPE_PARSE_PROMPT_ID,
        {"page_text": page_text, "source_url": source_url},
        LLMRecipeExtraction,
    )
    if not result.found or not result.title:
        raise RecipeParseError(
            "The page does not appear to contain a single recipe.",
            reasons=["llm_no_recipe"],
        )
    parsed = ParsedRecipe(
        title=result.title,
        image_url=result.image_url,
        source_url=source_url,
        recipe_yield=result.recipe_yield,
        prep_time=result.prep_time,
        cook_time=result.cook_time,
        total_time=result.total_time,
        ingredients=[ParsedIngredient(raw=line) for line in result.ingredients if line.strip()],
        instructions=[step for step in result.instructions if step.strip()],
    )
    if not parsed.is_complete():
        raise RecipeParseError(
            "LLM extraction did not yield a complete recipe.",
            reasons=[f"missing_{m}" for m in parsed.missing()],
        )
    return parsed
