"""P5 — product-match ranking (Appendix A.5).

Given the search term (and optional target_size) plus indexed Kroger products
(description, size, PRICE, department), return a ranked top-4 with reasons and a
none_acceptable escape hatch. Fixes legacy "reply with only the number": returns
structured indices, includes price for unit-price reasoning, and yields both the
match and its alternatives in one call (cart review needs up to 3 alternatives).
Deterministic stock/substitution logic runs on this output downstream (A.8).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from remy_api.prompts.base import RenderedPrompt, indexed, json_block

PROMPT_ID = "product_ranking"
VERSION = 1


class RankableProduct(BaseModel):
    description: str
    size: str | None = None
    price: float | None = Field(default=None, description="Regular price in dollars, if known.")
    sale_price: float | None = None
    department: str | None = None


class ProductRankingInput(BaseModel):
    search_term: str
    target_size: str | None = None
    package_quantity: int = 1
    products: list[RankableProduct]


class RankedProduct(BaseModel):
    index: int = Field(description="Index of the ranked product.")
    reason: str = Field(description="Short reason this product placed here.")


class ProductRankingOutput(BaseModel):
    ranked: list[RankedProduct] = Field(
        default_factory=list, description="Best matches first, up to 4. Empty if none acceptable."
    )
    none_acceptable: bool = Field(
        default=False, description="True when no product is a reasonable match (surface 'search manually')."
    )


_SYSTEM = """\
You rank grocery products for how well they match a shopping search term.
Output MUST be JSON:
{"ranked": [{"index": int, "reason": str}], "none_acceptable": bool}
List the best matches first, at most 4 (a top pick + up to 3 alternatives).
Only include genuinely plausible matches. If NONE are acceptable, return
{"ranked": [], "none_acceptable": true}.

Ranking rules:
- Pick the ACTUAL ingredient, not a prepared food, mix, or seasoning that merely
  contains it. Disambiguate by intent: "green onions" = fresh scallions, NOT
  noodles/dips; "fresh mint" = the herb, NOT gum/candy/tea.
- For produce, prefer fresh/raw over processed/frozen/canned (unless the term
  says canned/frozen).
- Avoid multipacks/value packs: prefer a SINGLE unit over a 4-pack/6-pack unless
  package_quantity >= 4. Avoid "BIG DEAL", "Value Pack", "Family Size" unless the
  needed quantity justifies it. Use price for unit-price sanity (a $1.19 single
  can beats a $6 six-pack when one can is needed).
- When target_size is given, prefer the product whose size is closest to it.
- Stay brand-neutral: do not prefer organic/premium/name-brand unless the search
  term explicitly asks for it.
- Give a short reason per ranked item (why it placed there / any caveat).
"""


def render(data: ProductRankingInput) -> RenderedPrompt:
    rows = indexed(list(data.products))
    header = f'Search term: "{data.search_term}"\nPackages needed: {data.package_quantity}'
    if data.target_size:
        header += f"\nTarget size: {data.target_size}"
    user = f"{header}\n\nProducts (indexed):\n{json_block(rows)}"
    return RenderedPrompt(prompt_id=PROMPT_ID, version=VERSION, system=_SYSTEM, user=user, temperature=0.0)
