"""Usuals API (post-launch purchase memory).

The user-facing surface over ``product_memory``: the Settings "Usuals" list, the
manual pin flow, hide/unhide/remove, and the receipt / order-history import
(extract line items → search Kroger at the user's store → review → confirm-seed).

All routes are authed via :data:`CurrentUser` and user-scoped. The LLM and Kroger
calls go through ``planner.deps`` so tests patch one place. Product search uses
the shared app token but needs a selected store (a 409 ``no_store_selected``
otherwise) — the same gate the plan approve step uses.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from remy_api import memory
from remy_api.deps import CurrentUser, SessionDep
from remy_api.errors import ConflictError, NotFoundError, UnprocessableError
from remy_api.kroger.errors import KrogerError
from remy_api.kroger.models import Product
from remy_api.models import ProductMemory, UserSettings
from remy_api.planner import deps
from remy_api.prompts import receipt_items
from remy_api.recipes.documents import RawUpload, build_extraction

router = APIRouter(prefix="/users/me/usuals", tags=["usuals"])

# Bound how many extracted lines we search Kroger for (a defensive cap on a
# pasted mega-history); the concurrency limit is separate.
_MAX_IMPORT_ITEMS = 40
_IMPORT_SEARCH_CONCURRENCY = 5


# --- schemas -----------------------------------------------------------------


class UsualOut(BaseModel):
    upc: str
    description: str | None
    size: str | None
    image_url: str | None
    last_price: float | None
    food_key: str
    source: str
    times_ordered: int
    preferred: bool

    @classmethod
    def from_row(cls, row: ProductMemory) -> UsualOut:
        return cls(
            upc=row.upc,
            description=row.description,
            size=row.size,
            image_url=row.image_url,
            last_price=row.last_price,
            food_key=row.food_key,
            source=row.source,
            times_ordered=row.times_ordered,
            preferred=row.preferred,
        )


class UsualPin(BaseModel):
    upc: str = Field(min_length=1)
    description: str | None = None
    size: str | None = None
    image_url: str | None = None
    price: float | None = None
    food_key: str = Field(min_length=1)


class ImportProductMatch(BaseModel):
    upc: str
    description: str | None = None
    brand: str | None = None
    size: str | None = None
    price: float | None = None
    image_url: str | None = None

    @classmethod
    def from_product(cls, p: Product) -> ImportProductMatch:
        price = (p.price.promo or p.price.regular) if p.price else None
        return cls(
            upc=p.upc,
            description=p.description,
            brand=p.brand,
            size=p.size,
            price=price,
            image_url=p.image_url,
        )


class ImportReviewItem(BaseModel):
    extracted_name: str
    food_key: str
    quantity: int | None = None
    matched: ImportProductMatch | None = None
    alternatives: list[ImportProductMatch] = Field(default_factory=list)


class ImportReviewResponse(BaseModel):
    found_items: bool
    items: list[ImportReviewItem] = Field(default_factory=list)


class ImportConfirmSelection(BaseModel):
    food_key: str = Field(min_length=1)
    upc: str = Field(min_length=1)
    description: str | None = None
    size: str | None = None
    image_url: str | None = None
    price: float | None = None


class ImportConfirmRequest(BaseModel):
    selections: list[ImportConfirmSelection] = Field(default_factory=list)


class ImportConfirmResponse(BaseModel):
    seeded: int


# --- helpers -----------------------------------------------------------------


async def _require_store(session: SessionDep, user_id: str) -> tuple[str, str]:
    """Return (location_id, fulfillment) for a user with a selected store, else 409."""
    row = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    settings = row.scalar_one_or_none()
    location_id = settings.store_location_id if settings else None
    if not location_id:
        raise ConflictError("Select a preferred store in Settings first.", code="no_store_selected")
    fulfillment = (settings.fulfillment_method.lower() if settings else "pickup") or "pickup"
    return location_id, fulfillment


# --- list / pin / hide / remove ----------------------------------------------


@router.get("", response_model=list[UsualOut])
async def list_usuals(
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=12, ge=1, le=100),
) -> list[UsualOut]:
    rows = await memory.list_usuals(session, user.id, limit)
    return [UsualOut.from_row(r) for r in rows]


@router.post("", response_model=UsualOut, status_code=status.HTTP_201_CREATED)
async def pin_usual(payload: UsualPin, user: CurrentUser, session: SessionDep) -> UsualOut:
    row = await memory.pin(
        session,
        user.id,
        food_key=payload.food_key,
        upc=payload.upc,
        description=payload.description,
        size=payload.size,
        image_url=payload.image_url,
        price=payload.price,
        source="pinned",
    )
    await session.commit()
    await session.refresh(row)
    return UsualOut.from_row(row)


@router.delete("/{upc}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_usual(upc: str, user: CurrentUser, session: SessionDep) -> None:
    """Remove a usual by UPC: hard-delete pinned/import rows, hide order/swap rows."""
    affected = await memory.remove(session, user.id, upc)
    if affected == 0:
        raise NotFoundError("Usual not found.")
    await session.commit()


@router.post("/{upc}/hide", status_code=status.HTTP_204_NO_CONTENT)
async def hide_usual(upc: str, user: CurrentUser, session: SessionDep) -> None:
    affected = await memory.set_hidden(session, user.id, upc, True)
    if affected == 0:
        raise NotFoundError("Usual not found.")
    await session.commit()


@router.post("/{upc}/unhide", status_code=status.HTTP_204_NO_CONTENT)
async def unhide_usual(upc: str, user: CurrentUser, session: SessionDep) -> None:
    affected = await memory.set_hidden(session, user.id, upc, False)
    if affected == 0:
        raise NotFoundError("Usual not found.")
    await session.commit()


# --- receipt / order-history import ------------------------------------------


@router.post("/import", response_model=ImportReviewResponse)
async def import_usuals(
    user: CurrentUser,
    session: SessionDep,
    files: list[UploadFile] | None = File(default=None, description="1..6 receipt images and/or a PDF."),
    text: str | None = Form(default=None, description="Pasted order-history / receipt text."),
) -> ImportReviewResponse:
    """Extract line items from a receipt/order history, then search Kroger at the
    user's store for each — returns a REVIEW payload (nothing is saved yet)."""
    location_id, fulfillment = await _require_store(session, user.id)

    real_files = [f for f in (files or []) if f is not None and f.filename]
    pasted = (text or "").strip()
    if not real_files and not pasted:
        raise UnprocessableError("Upload a receipt or paste your order history.", code="no_import_content")

    if real_files:
        uploads = [
            RawUpload(filename=f.filename or "upload", content_type=f.content_type, data=await f.read())
            for f in real_files
        ]
        extraction = build_extraction(uploads)  # raises UploadRejectedError (422) on bad files
        if extraction.mode == "text":
            prompt_in = receipt_items.ReceiptItemsInput(text=extraction.text or "")
        else:
            prompt_in = receipt_items.ReceiptItemsInput(images=extraction.images)
    else:
        prompt_in = receipt_items.ReceiptItemsInput(text=pasted)

    extracted = await deps.get_llm_client().structured(
        receipt_items.render(prompt_in), receipt_items.ReceiptItemsOutput
    )
    if not extracted.found_items or not extracted.items:
        return ImportReviewResponse(found_items=False, items=[])

    line_items = extracted.items[:_MAX_IMPORT_ITEMS]
    sem = asyncio.Semaphore(_IMPORT_SEARCH_CONCURRENCY)

    async def _lookup(line: receipt_items.ReceiptLineItem) -> ImportReviewItem:
        async with sem:
            try:
                products = await deps.kroger_search_products(
                    session, line.name, location_id, limit=3, fulfillment=fulfillment
                )
            except KrogerError:
                products = []
        return ImportReviewItem(
            extracted_name=line.name,
            food_key=memory.food_key(line.name),
            quantity=line.quantity,
            matched=ImportProductMatch.from_product(products[0]) if products else None,
            alternatives=[ImportProductMatch.from_product(p) for p in products[1:3]],
        )

    items = await asyncio.gather(*(_lookup(li) for li in line_items))
    return ImportReviewResponse(found_items=True, items=list(items))


@router.post("/import/confirm", response_model=ImportConfirmResponse)
async def confirm_import(
    payload: ImportConfirmRequest, user: CurrentUser, session: SessionDep
) -> ImportConfirmResponse:
    """Seed the reviewed selections into purchase memory (source='import')."""
    seeded = 0
    for sel in payload.selections:
        await memory.pin(
            session,
            user.id,
            food_key=sel.food_key,
            upc=sel.upc,
            description=sel.description,
            size=sel.size,
            image_url=sel.image_url,
            price=sel.price,
            source="import",
        )
        seeded += 1
    await session.commit()
    return ImportConfirmResponse(seeded=seeded)
