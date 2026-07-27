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
VERSION = 3


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

Normally return exactly one object per input line, echoing its `index`.
For a compound line explicitly introduced as "optional toppings", "toppings",
"optional garnishes", "garnishes", or similar, the label itself is NOT food:
return one object for EACH concrete food option named, repeating the source
`index` for each object. Mark each one's note as "optional" plus any relevant
prep. For example, "Optional toppings: yogurt or whipped cream, maple syrup or
honey, and fresh fruit" becomes five objects (yogurt, whipped cream, maple syrup,
honey, fresh fruit), all with the same index. Never emit generic "topping" or
"garnish" as food.
Likewise, when a line explicitly says the named foods may be used in "any
combination", as a "mixture", or equivalent, return one object for EACH named
option with the same source `index`. Since the stated quantity applies to the
combination as a whole, set each option's quantity and unit to null rather than
incorrectly assigning the full amount to every option. Put the shared amount in
the note, e.g. "combination totaling 1/2 cup". This lets the shopper include any
subset without overstating how much of each food the recipe requires.

Fields:
- quantity: the numeric amount as a number (convert fractions: "1/2" -> 0.5,
  "1 1/2" -> 1.5). null if the line states no amount.
- unit: measurement unit lowercased and singular (cup, tbsp, tsp, lb, oz, g, kg,
  ml, clove, can, bunch, pinch, ...). null if none.
- food: the core ingredient, normalized to CANONICAL SINGULAR LOWERCASE
  ("onions" -> "onion", "cloves garlic" -> "garlic", "black beans" -> "black bean",
  "boneless chicken thighs" -> "chicken thigh"). Drop leading quantities/units and
  trailing prep. Keep meaningful qualifiers that change the product
  ("brown sugar", "green onion", "smoked paprika"). Preserve a specific variety
  or example supplied by the recipe instead of generalizing it: "waxy or
  all-purpose potatoes, such as Yukon Gold" -> food:"yukon gold potato".
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
