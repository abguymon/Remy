"""P4a — ingredient-line parsing (Appendix A.6, new in v2).

Parse raw ingredient lines into {quantity, unit, food, note}, batched per recipe
and indexed. `food` is normalized to a canonical singular lowercase form (drives
consolidation and word-boundary pantry matching); the raw line is retained by the
caller against the same index.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from remy_api.prompts.base import RenderedPrompt, indexed, json_block

PROMPT_ID = "ingredient_parsing"
VERSION = 1


class IngredientParsingInput(BaseModel):
    lines: list[str] = Field(description="Raw ingredient lines from a single recipe, in order.")


class ParsedIngredient(BaseModel):
    index: int = Field(description="Index of the source line this parse belongs to.")
    quantity: float | None = Field(default=None, description="Numeric amount, or null if none stated.")
    unit: str | None = Field(default=None, description="Unit of measure (cup, lb, clove, can, ...), or null.")
    food: str = Field(description="Canonical singular lowercase food name (e.g. 'onion', 'black bean').")
    note: str | None = Field(
        default=None, description="Preparation/qualifier ('diced', 'to taste', 'drained'), or null."
    )


class IngredientParsingOutput(BaseModel):
    ingredients: list[ParsedIngredient] = Field(default_factory=list)


_SYSTEM = """\
You parse recipe ingredient lines into structured fields. Output MUST be JSON:
{"ingredients": [{"index": int, "quantity": number|null, "unit": string|null,
"food": string, "note": string|null}]}

Return exactly one object per input line, echoing its `index`.

Fields:
- quantity: the numeric amount as a number (convert fractions: "1/2" -> 0.5,
  "1 1/2" -> 1.5). null if the line states no amount.
- unit: measurement unit lowercased and singular (cup, tbsp, tsp, lb, oz, g, kg,
  ml, clove, can, bunch, pinch, ...). null if none.
- food: the core ingredient, normalized to CANONICAL SINGULAR LOWERCASE
  ("onions" -> "onion", "cloves garlic" -> "garlic", "black beans" -> "black bean",
  "boneless chicken thighs" -> "chicken thigh"). Drop leading quantities/units and
  trailing prep. Keep meaningful qualifiers that change the product
  ("brown sugar", "green onion", "smoked paprika").
- note: prep or qualifier text ("finely diced", "to taste", "drained and rinsed",
  "at room temperature"), or null.

Examples:
  "2 cloves garlic, minced" -> {quantity:2, unit:"clove", food:"garlic", note:"minced"}
  "1 (14 oz) can black beans, drained" -> {quantity:1, unit:"can", food:"black bean", note:"drained"}
  "Salt and pepper to taste" -> {quantity:null, unit:null, food:"salt and pepper", note:"to taste"}
  "1/2 cup chopped fresh cilantro" -> {quantity:0.5, unit:"cup", food:"cilantro", note:"chopped, fresh"}
"""


def render(data: IngredientParsingInput) -> RenderedPrompt:
    rows = indexed(data.lines, key="index")
    # `indexed` wraps plain strings as {"index": i, "value": line}
    user = "Ingredient lines (indexed):\n" + json_block(rows)
    return RenderedPrompt(prompt_id=PROMPT_ID, version=VERSION, system=_SYSTEM, user=user, temperature=0.0)
