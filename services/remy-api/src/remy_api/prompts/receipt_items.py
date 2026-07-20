"""Receipt / order-history line-item extraction (multimodal, post-launch usuals).

Turns a grocery receipt or order-history screenshot/PDF/photo — or pasted order
history text — into a flat list of purchased line items the import flow searches
Kroger for and seeds as "usuals". Mirrors the ``recipe_from_images`` multimodal
pattern: same ``ImagePart`` contract, an anti-hallucination system prompt, and a
``found_items=false`` escape for content that is not a receipt/order history.

ANTI-HALLUCINATION IS THE SPEC. A model asked to "read a receipt" will happily
normalize abbreviations into full product names or invent prices for smudged
lines. Every rule forces verbatim transcription of only the product lines that
are actually present, and honest ``found_items=false`` for non-receipt content.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from remy_api.llm.prompt import ImagePart, RenderedPrompt

PROMPT_ID = "receipt_items"
VERSION = 1

# Defensive caps (the endpoint already bounds file/page count upstream).
_MAX_IMAGES = 6
_MAX_TEXT_CHARS = 12_000


class ReceiptItemsInput(BaseModel):
    """Typed input: EITHER pasted text OR ordered images (at least one present)."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    images: list[ImagePart] = Field(default_factory=list)
    text: str | None = None


class ReceiptLineItem(BaseModel):
    name: str = Field(description="The product name/description exactly as written on the receipt.")
    quantity: int | None = Field(default=None, ge=1, description="Quantity if shown on the line, else null.")
    price: float | None = Field(default=None, description="Line price in dollars if shown, else null.")


class ReceiptItemsOutput(BaseModel):
    found_items: bool = Field(description="True only when the content is a grocery receipt / order history.")
    items: list[ReceiptLineItem] = Field(default_factory=list)


_SYSTEM = """\
You extract the purchased grocery line items from a store receipt, an online
order-history page, or a photo/screenshot/PDF of one. Output MUST be JSON:
{"found_items": bool, "items": [{"name": str, "quantity": int|null, "price": number|null}]}

Rules — you are a transcriber, NOT an author. Never use grocery knowledge to invent items:
- Transcribe ONE entry per purchased product line that is actually visible. Keep
  the product name as written (abbreviations and all: "KRO SHRD CHEDDAR" stays as
  written; do not expand it into "Kroger Shredded Cheddar Cheese").
- quantity: copy the line quantity only if the line shows one; otherwise null.
  Do not assume 1.
- price: copy the line's item price if shown (a plain dollar amount); otherwise
  null. Never compute or estimate a price.
- SKIP every non-product line: the store name/address/header, date/time, cashier,
  card/payment lines, SUBTOTAL, TAX, TOTAL, BALANCE, CHANGE, savings/coupon lines,
  loyalty/fuel-points lines, bag fees, tips, "you saved", barcodes, and thank-you
  footers. These are NOT items.
- Deposits/bottle fees, bag fees, and delivery/service fees are NOT products.
- If a line is too smudged/blurry to read the product name, omit it — never guess.
- found_items=false when the content is not a receipt or order history at all
  (a random photo, a recipe, a document, blank/illegible). When found_items=false,
  return an empty items list.
- Multiple images are pages of ONE receipt/order in the given order; concatenate
  their items and do not duplicate lines that repeat across a page overlap.
"""

_TEXT_ONLY_NOTE = (
    "The content below is pasted order-history / receipt text. Extract the product "
    "line items per the rules; skip totals, tax, fees, and headers."
)
_IMAGE_NOTE = (
    "The receipt / order history spans {n} image(s), in order. Extract the product "
    "line items per the rules; skip totals, tax, fees, and headers."
)


def render(data: ReceiptItemsInput) -> RenderedPrompt:
    images = tuple(data.images[:_MAX_IMAGES])
    text = (data.text or "").strip()
    if images:
        lines = [_IMAGE_NOTE.format(n=len(images))]
        if text:
            lines.append(f'Additional pasted text/context:\n"{text[:_MAX_TEXT_CHARS]}"')
    else:
        lines = [_TEXT_ONLY_NOTE, "", text[:_MAX_TEXT_CHARS]]
    return RenderedPrompt(
        prompt_id=PROMPT_ID,
        version=VERSION,
        system=_SYSTEM,
        user="\n".join(lines),
        temperature=0.0,
        images=images,
    )
