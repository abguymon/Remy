"""P2 — saved-recipe relevance filter (Appendix A.2).

Given a meal query and the user's saved-recipe candidates (indexed, with key
ingredients), return the indices that are genuine matches. Fixes the legacy
match-by-name-string-equality bug by returning indices. Keeps the strictness
calibration examples; loosens to "plausible fits" when the query is vague.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from remy_api.prompts.base import RenderedPrompt, indexed, json_block

PROMPT_ID = "saved_recipe_relevance"
VERSION = 1


class RecipeCandidate(BaseModel):
    title: str
    key_ingredients: list[str] = Field(default_factory=list)


class SavedRecipeRelevanceInput(BaseModel):
    query: str
    is_specific: bool = True
    candidates: list[RecipeCandidate]


class SavedRecipeRelevanceOutput(BaseModel):
    relevant_indices: list[int] = Field(default_factory=list)


_SYSTEM = """\
You decide which of a user's SAVED recipes match a meal they want to cook.
Output MUST be JSON: {"relevant_indices": [int, ...]} — the `index` of each
matching candidate, or [] if none match.

Be strict for SPECIFIC queries: include a candidate only if it is the same dish
or a very close variant. Partial word overlap does NOT count.
Calibration:
- query "chicken tikka masala" vs "Chicken Tikka Masala" -> MATCH.
- query "pasta carbonara" vs "Spaghetti Carbonara" -> MATCH (same dish, different pasta).
- query "farro tomato mozzarella bake" vs "Coconut Fish and Tomato Bake" -> NO MATCH (different dish).

Use each candidate's key_ingredients, not just its title, to judge.

If the query is VAGUE (is_specific = false, e.g. "salmon dinner"), LOOSEN to
"plausible fits": include candidates that plausibly satisfy the intent (any
reasonable salmon dinner), not only exact-dish matches.
"""


def render(data: SavedRecipeRelevanceInput) -> RenderedPrompt:
    rows = indexed(list(data.candidates))
    user = (
        f'Meal query: "{data.query}"\n'
        f"is_specific: {str(data.is_specific).lower()}\n\n"
        f"Saved recipe candidates (indexed):\n{json_block(rows)}"
    )
    return RenderedPrompt(prompt_id=PROMPT_ID, version=VERSION, system=_SYSTEM, user=user, temperature=0.0)
