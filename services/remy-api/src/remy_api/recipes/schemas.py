"""Pydantic models for recipe parsing and the recipe API (T3).

``ParsedRecipe`` / ``ParsedIngredient`` are the internal shape produced by the
scraper (and the LLM fallback) and consumed by the store. The ``Recipe*`` models
are the API request/response contracts for ``routers/recipes.py``.

Parsed ingredient fields (``quantity``/``unit``/``food``/``note``) are left
optional: ``recipe-scrapers`` gives us only raw lines, and structured parsing
(FR-9, prompt P4a) happens later in the planner (T5/T4). The raw line is always
retained.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ParsedIngredient(BaseModel):
    """One ingredient line: raw text plus (optional) parsed components."""

    raw: str
    quantity: float | None = None
    unit: str | None = None
    food: str | None = None
    note: str | None = None


class ParsedRecipe(BaseModel):
    """Normalized recipe extracted from a URL (scraper or LLM fallback)."""

    title: str
    image_url: str | None = None
    source_url: str | None = None
    recipe_yield: str | None = None
    prep_time: str | None = None
    cook_time: str | None = None
    total_time: str | None = None
    ingredients: list[ParsedIngredient] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)

    def is_complete(self) -> bool:
        """A parse is usable only if it has both ingredients and instructions."""
        return bool(self.ingredients) and bool(self.instructions)

    def missing(self) -> list[str]:
        """Human-readable list of what a parse is missing (for error detail)."""
        gaps: list[str] = []
        if not self.title:
            gaps.append("title")
        if not self.ingredients:
            gaps.append("ingredients")
        if not self.instructions:
            gaps.append("instructions")
        return gaps


class LLMRecipeExtraction(BaseModel):
    """Structured-output schema handed to the LLM fallback (T4 wires the client).

    Kept separate from :class:`ParsedRecipe` so the prompt's contract is explicit
    and independent of internal representation. ``found`` lets the model signal a
    page that is not a recipe at all (paywall, 404 shell, listicle).
    """

    found: bool = Field(description="True only if the page is a single recipe.")
    title: str | None = None
    image_url: str | None = None
    recipe_yield: str | None = None
    prep_time: str | None = None
    cook_time: str | None = None
    total_time: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)


# --- API request/response models --------------------------------------------


class IngredientInput(BaseModel):
    """Editable ingredient line on PUT (FR-8)."""

    raw: str = Field(min_length=1)
    quantity: float | None = None
    unit: str | None = None
    food: str | None = None
    note: str | None = None


class IngredientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    raw: str
    quantity: float | None
    unit: str | None
    food: str | None
    note: str | None


class RecipeSummary(BaseModel):
    """Card-grid row for the Recipes screen (FR-19)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    slug: str
    source_url: str | None
    image_url: str | None = None
    total_time: str | None
    created_at: datetime
    last_cooked_at: datetime | None


class RecipeDetail(RecipeSummary):
    """Full recipe detail view."""

    recipe_yield: str | None
    prep_time: str | None
    cook_time: str | None
    instructions: list[str]
    ingredients: list[IngredientOut]


class RecipeFromUrl(BaseModel):
    url: str = Field(min_length=1)


class RecipeUpdate(BaseModel):
    """Partial edit of a saved recipe (FR-8). Only provided fields change.

    If ``ingredients`` is provided it fully replaces the existing lines.
    """

    title: str | None = None
    source_url: str | None = None
    recipe_yield: str | None = None
    prep_time: str | None = None
    cook_time: str | None = None
    total_time: str | None = None
    instructions: list[str] | None = None
    ingredients: list[IngredientInput] | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("title must not be blank")
        return value
