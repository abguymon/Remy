"""Recipe extraction from photos / scanned pages (multimodal, PRD FR-6).

The upload flow (``routers/recipes.py`` ``POST /recipes/from-upload``) hands this
prompt 1..N images — phone photos of a cookbook page, a screenshot, or the
rendered pages of a scanned PDF — and asks for a single structured recipe. The
output schema is ``remy_api.recipes.schemas.LLMRecipeExtraction`` (owned by the
recipes module — the caller supplies it; this module only renders the prompt),
the SAME contract as the text ``recipe_parse_fallback`` prompt so both paths
converge on one shape.

ANTI-HALLUCINATION IS THE SPEC. A vision model asked to "read a recipe" will
happily invent plausible quantities for smudged text. Every rule below exists to
force verbatim transcription of only what is visible, and an honest
``found=false`` when the images are not a legible recipe.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from remy_api.llm.prompt import ImagePart, RenderedPrompt

PROMPT_ID = "recipe_from_images"
VERSION = 1

# Defensive cap; the endpoint already limits page/file count upstream.
_MAX_IMAGES = 10
_MAX_HINT_CHARS = 500


class RecipeFromImagesInput(BaseModel):
    """Typed input: ordered images plus an optional free-text user hint."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    images: list[ImagePart] = Field(min_length=1)
    hint: str | None = None


_SYSTEM = """\
You transcribe a single recipe from one or more images of a page (a photo of a
cookbook or handwritten card, a screenshot, or scanned pages). Output MUST be JSON:
{"found": bool, "title": str|null, "image_url": str|null, "recipe_yield": str|null,
 "prep_time": str|null, "cook_time": str|null, "total_time": str|null,
 "ingredients": [str], "instructions": [str]}

Rules — you are a transcriber, NOT an author. Never use recipe knowledge to fill gaps:
- Transcribe ONLY text that is actually visible in the images. Do NOT add, infer,
  normalize, complete, or "correct" anything. If the page omits a step or a
  quantity, your output omits it too.
- ingredients: one entry per visible ingredient line, verbatim — keep the exact
  quantities, units, and wording as written ("1 1/2 cups flour, sifted"). Do not
  merge two lines, split one line, reorder, or convert units.
- instructions: one entry per visible step, in order, without step numbers.
- Text you cannot read (blur, glare, a fold, a cut-off edge) is transcribed as the
  literal string "[illegible]" in place — NEVER guess the missing characters or
  numbers. A partially-readable line keeps what you can read plus "[illegible]".
- found=false when the images are not a single legible recipe: too blurry to read,
  not a recipe at all, or only a photo of finished food with no text. When
  found=false, leave title null and the lists empty. A dark or slightly blurry but
  still readable page is found=true.
- Multiple images are ONE recipe spread across pages, in the given order (page 1
  first). Concatenate their content into a single recipe; do not emit duplicates
  for text that repeats across an overlap.
- title: the recipe's name as written on the page. If no title is visible, use a
  short literal description of the dish from the page text; never invent a
  marketing name. image_url is always null (there is no source page).
- Times/yield: copy as human-readable strings only if written on the page
  ("35 minutes", "serves 4"), else null.
"""


def render(data: RecipeFromImagesInput) -> RenderedPrompt:
    images = tuple(data.images[:_MAX_IMAGES])
    lines = [f"This recipe spans {len(images)} image(s), in order (page 1 first)."]
    hint = (data.hint or "").strip()
    if hint:
        lines.append(f'User hint (which recipe / where to look): "{hint[:_MAX_HINT_CHARS]}"')
    lines.append("Transcribe the recipe as JSON per the rules. Do not invent anything not visible.")
    return RenderedPrompt(
        prompt_id=PROMPT_ID,
        version=VERSION,
        system=_SYSTEM,
        user="\n".join(lines),
        temperature=0.0,
        images=images,
    )
