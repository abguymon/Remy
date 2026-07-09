"""P1 — meal extraction (Appendix A.1).

Free text -> list of distinct meal intents. Preserves vagueness (does NOT invent
specific recipe names), strips scheduling/serving chatter, and captures inline
recipe URLs as url-type meal entries (instead of the legacy all-or-nothing URL
branch that skipped search whenever any URL appeared). Empty list is valid and
drives the "what would you like to make?" reprompt.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from remy_api.prompts.base import RenderedPrompt

PROMPT_ID = "meal_extraction"
VERSION = 1


class MealExtractionInput(BaseModel):
    text: str


class Meal(BaseModel):
    query: str = Field(
        description="Search-friendly phrase preserving the user's specificity level "
        "('salmon dinner' stays vague; 'chicken tikka masala' stays specific). "
        "Empty string when this meal is a URL entry."
    )
    verbatim: str = Field(description="The user's own words for this meal, for display as the section header.")
    is_specific: bool = Field(description="True if the user named a concrete dish; False if the intent is vague.")
    url: str | None = Field(default=None, description="A recipe URL the user pasted for this meal, if any.")


class MealExtractionOutput(BaseModel):
    meals: list[Meal] = Field(default_factory=list)


_SYSTEM = """\
You extract distinct meal intents from a user's free-text grocery/meal-planning \
message. Output MUST be JSON matching this schema:
{"meals": [{"query": str, "verbatim": str, "is_specific": bool, "url": str|null}]}

Rules:
- One entry per distinct meal the user wants to cook. If none, return {"meals": []}.
- PRESERVE VAGUENESS. Never invent a specific recipe name from a vague request.
  "some kind of salmon dish" -> query "salmon dinner", is_specific false.
  "chicken tikka masala" -> query "chicken tikka masala", is_specific true.
- verbatim = the user's own words for that meal (for the section header).
- Strip scheduling/quantity/serving chatter from `query` but do NOT error on it:
  "tacos on Friday for 6 people" -> query "tacos", verbatim "tacos on Friday".
- If the user pastes a recipe URL, emit a meal entry with that `url` set, `query` "",
  is_specific true, and verbatim = a short human label (e.g. the domain or "pasted link").
  A message can mix URLs and free-text meals — capture all of them.
- Ignore non-food content and pleasantries in mixed messages.
"""


def render(data: MealExtractionInput) -> RenderedPrompt:
    return RenderedPrompt(
        prompt_id=PROMPT_ID,
        version=VERSION,
        system=_SYSTEM,
        user=f"User message:\n{data.text}",
        temperature=0.0,
    )
