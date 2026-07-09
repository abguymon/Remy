"""Recipe-parse fallback (PRD FR-6, V2_PLAN A — no legacy equivalent).

When ``recipe-scrapers`` fails or returns incomplete data, the scraper feeds the
fetched page text through this prompt to extract a structured recipe. The output
schema is ``remy_api.recipes.schemas.LLMRecipeExtraction`` (owned by the recipes
module — the caller supplies it; this module only renders the prompt). ``found``
must be False for non-recipe pages (paywall shells, 404s, roundups) so the
scraper can raise a typed error instead of inventing a recipe.
"""

from __future__ import annotations

from pydantic import BaseModel

from remy_api.prompts.base import RenderedPrompt

PROMPT_ID = "recipe_parse_fallback"
VERSION = 1

# Page text is pre-truncated by the scraper, but cap defensively.
_MAX_PAGE_TEXT = 40_000


class RecipeExtractionInput(BaseModel):
    page_text: str
    source_url: str


_SYSTEM = """\
You extract a single recipe from the text of a web page. Output MUST be JSON:
{"found": bool, "title": str|null, "image_url": str|null, "recipe_yield": str|null,
 "prep_time": str|null, "cook_time": str|null, "total_time": str|null,
 "ingredients": [str], "instructions": [str]}

Rules:
- found=true ONLY if the page contains one actual recipe with ingredients and
  instructions. Paywall shells, error pages, category/roundup pages, and articles
  about food are found=false (leave the other fields null/empty).
- ingredients: one entry per ingredient line, verbatim as written (keep
  quantities and units — do not normalize, merge, or invent lines).
- instructions: one entry per step, in order, without step numbers.
- title: the recipe's name, not the site name or SEO suffix ("Best Ever ... | Site").
- Times/yield: copy as human-readable strings if present ("35 minutes", "4 servings"),
  else null. image_url only if a main recipe image URL appears in the text, else null.
- Never fabricate content that is not on the page.
"""


def render(data: RecipeExtractionInput) -> RenderedPrompt:
    return RenderedPrompt(
        prompt_id=PROMPT_ID,
        version=VERSION,
        system=_SYSTEM,
        user=f"Source URL: {data.source_url}\n\nPage text:\n{data.page_text[:_MAX_PAGE_TEXT]}",
        temperature=0.0,
    )
