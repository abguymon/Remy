"""P4 — batched product extraction + P4-single fallback (Appendix A.4).

The highest-value legacy prompt. Input is now PARSED, consolidated lines
({quantity, unit, food, note}), not raw strings. Output per line is a list of
products ({search_term, package_quantity, target_size?, confidence}) with
multi-product expansion. Both the batch and the per-item fallback share ONE
rules block (``PRODUCT_RULES``) so they can never drift, and both use indexed
I/O so a whitespace/case change can't break the join (the legacy defect).

P4-single is the retry path only — used per item after a batch validation failure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from remy_api.prompts.base import RenderedPrompt, indexed, json_block
from remy_api.prompts.rules import PRODUCT_RULES

PROMPT_ID = "product_extraction"
PROMPT_ID_SINGLE = "product_extraction_single"
VERSION = 3


class ParsedLine(BaseModel):
    quantity: float | None = None
    unit: str | None = None
    food: str
    note: str | None = None


class ProductExtractionInput(BaseModel):
    lines: list[ParsedLine]


class ExtractedProduct(BaseModel):
    search_term: str = Field(description="Grocery-store search term (US naming, fresh-prefix, canned default).")
    package_quantity: int = Field(ge=1, description="Number of packages/items to buy from the store.")
    target_size: str | None = Field(
        default=None, description="Desired package size hint (e.g. '2 lb', '14 oz'), or null."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="0-1 confidence in the search term.")


class ProductExtractionItem(BaseModel):
    index: int
    products: list[ExtractedProduct] = Field(default_factory=list)


class ProductExtractionOutput(BaseModel):
    items: list[ProductExtractionItem] = Field(default_factory=list)


class ProductExtractionSingleOutput(BaseModel):
    products: list[ExtractedProduct] = Field(default_factory=list)


_OUTPUT_CONTRACT_BATCH = """\
Output MUST be JSON:
{"items": [{"index": int, "products": [{"search_term": str, "package_quantity": int,
"target_size": str|null, "confidence": number}]}]}
Return exactly one object per input line, echoing its `index`. A line may expand
to multiple products (rule 6); every line yields at least one product.
"""

_OUTPUT_CONTRACT_SINGLE = """\
Output MUST be JSON:
{"products": [{"search_term": str, "package_quantity": int, "target_size": str|null,
"confidence": number}]}
This is ONE ingredient line; it may still expand to multiple products (rule 6).
"""

_SYSTEM_BATCH = f"{PRODUCT_RULES}\n\n{_OUTPUT_CONTRACT_BATCH}"
_SYSTEM_SINGLE = f"{PRODUCT_RULES}\n\n{_OUTPUT_CONTRACT_SINGLE}"


def render_batch(data: ProductExtractionInput) -> RenderedPrompt:
    rows = indexed(list(data.lines))
    user = "Parsed ingredient lines (indexed):\n" + json_block(rows)
    return RenderedPrompt(prompt_id=PROMPT_ID, version=VERSION, system=_SYSTEM_BATCH, user=user, temperature=0.0)


def render_single(line: ParsedLine) -> RenderedPrompt:
    user = "Parsed ingredient line:\n" + json_block(line.model_dump())
    return RenderedPrompt(
        prompt_id=PROMPT_ID_SINGLE, version=VERSION, system=_SYSTEM_SINGLE, user=user, temperature=0.0
    )
