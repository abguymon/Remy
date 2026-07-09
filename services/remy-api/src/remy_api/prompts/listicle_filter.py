"""P3 — listicle/roundup filter (Appendix A.3).

Two-stage: a zero-cost regex prefilter auto-drops obvious leading-number
listicle titles, then the LLM judges the remaining ambiguous cases using
{title, url, snippet} (the URL slug is often the stronger signal). Both stages
return/operate on indices, fixing the legacy match-by-title-string bug.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from remy_api.prompts.base import RenderedPrompt, indexed, json_block

PROMPT_ID = "listicle_filter"
VERSION = 1


class SearchCandidate(BaseModel):
    title: str
    url: str = ""
    snippet: str = ""


class ListicleFilterInput(BaseModel):
    query: str
    candidates: list[SearchCandidate]


class ListicleFilterOutput(BaseModel):
    keep_indices: list[int] = Field(
        default_factory=list,
        description="Indices of candidates that are single recipe pages to keep.",
    )


# ---------------------------------------------------------------------------
# Regex prefilter (no LLM). Runs first; drops obvious leading-number listicles.
# ---------------------------------------------------------------------------

# "15 Best...", "20 Easy...", "7 Quick..." — leading number + a roundup adjective.
_LEADING_NUM_ADJ = re.compile(
    r"^\s*\d{1,3}\s+"
    r"(best|easy|quick|simple|delicious|amazing|healthy|great|top|favorite|"
    r"favourite|classic|essential|must[- ]?try|tasty|awesome|incredible|"
    r"perfect|creative|genius|popular|budget|weeknight)\b",
    re.IGNORECASE,
)
# "23 Taco Recipes", "10 Ways to...", "12 Dinner Ideas" — leading number + collection noun somewhere.
_LEADING_NUM_COLLECTION = re.compile(
    r"^\s*\d{1,3}\b.*\b(recipes|ideas|ways|dishes|meals|dinners|desserts|"
    r"variations|takes|twists|favorites|favourites)\b",
    re.IGNORECASE,
)


def is_listicle_title(title: str) -> bool:
    """True if the title is an obvious leading-number roundup/listicle."""
    if not title:
        return False
    return bool(_LEADING_NUM_ADJ.search(title) or _LEADING_NUM_COLLECTION.search(title))


def prefilter_listicles(candidates: list[SearchCandidate]) -> tuple[list[int], list[int]]:
    """Split candidate indices into (survivors, auto_dropped) by title regex.

    Survivors still need the LLM pass; auto_dropped are confidently listicles.
    """
    survivors: list[int] = []
    dropped: list[int] = []
    for i, c in enumerate(candidates):
        (dropped if is_listicle_title(c.title) else survivors).append(i)
    return survivors, dropped


# ---------------------------------------------------------------------------
# LLM stage
# ---------------------------------------------------------------------------

_SYSTEM = """\
You filter web search results down to SINGLE recipe pages. Output MUST be JSON:
{"keep_indices": [int, ...]} — the `index` of each candidate that is an
individual recipe page. Return [] if none qualify.

KEEP: single recipe pages ("Easy Chicken Tikka Masala", "Pesto Pasta Recipe"),
including ones whose URL slug names one dish (/recipes/chicken-tikka-masala/).

DROP:
- Roundups / listicles ("15 Best Tacos", "20 Easy Dinners", "10 Ways to ...").
- Category or collection/tag pages (/recipes/, /category/tacos/, /tag/...).
- Non-recipe articles (reviews, news, technique explainers, product posts).

The URL slug is often the strongest signal — a slug like /best-taco-recipes/ or
one containing a leading number is a roundup even if the title looks innocent.
"""


def render(data: ListicleFilterInput) -> RenderedPrompt:
    rows = indexed(list(data.candidates))
    user = f'Search query: "{data.query}"\n\nCandidates (indexed):\n{json_block(rows)}'
    return RenderedPrompt(prompt_id=PROMPT_ID, version=VERSION, system=_SYSTEM, user=user, temperature=0.0)
