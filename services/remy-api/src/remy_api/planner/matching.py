"""Match step (FR-13–FR-15): product-term extraction, search, rank, substitute.

Background step. First one batched P4 call turns approved list lines into
grocery search terms + package quantities (per-item P4-single fallback if the
batch fails validation). Then, per extracted product (bounded concurrency), search
Kroger at the preferred store, LLM-rank the results (P5, price + target_size
aware), and run the deterministic stock/fulfillment substitution walk (A.8) to
pick the best obtainable product with up to 3 alternatives. Produces a cart draft
with per-line status, chosen product, alternatives, and a live estimated total.
Results persist incrementally so ``GET /plan/state`` streams per-item progress.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select

from remy_api.kroger.errors import KrogerError, KrogerNotConnectedError
from remy_api.kroger.models import Product
from remy_api.llm.errors import LLMError
from remy_api.models import KrogerToken, Plan, PlanStatus, UserSettings
from remy_api.planner import deps
from remy_api.planner.schemas import (
    Alternative,
    CartState,
    ItemStatus,
    ListLine,
    ListState,
    MatchItem,
    MatchStage,
    ProductRef,
)
from remy_api.planner.substitution import MatchStatus, select_product
from remy_api.prompts import product_extraction, product_ranking

logger = logging.getLogger("remy.planner.matching")

_ITEM_CONCURRENCY = 6
_SEARCH_LIMIT = 10

_STATUS_MAP = {
    MatchStatus.MATCHED: ItemStatus.MATCHED,
    MatchStatus.SUBSTITUTED: ItemStatus.SUBSTITUTED,
    MatchStatus.STOCK_UNKNOWN: ItemStatus.STOCK_UNKNOWN,
    MatchStatus.NOT_FOUND: ItemStatus.NOT_FOUND,
}


def _effective_price(product: Product) -> float | None:
    if product.price is None:
        return None
    return product.price.promo or product.price.regular


def _product_ref(product: Product) -> ProductRef:
    return ProductRef(
        upc=product.upc,
        description=product.description,
        brand=product.brand,
        size=product.size,
        price=_effective_price(product),
        image_url=product.image_url,
        stock_level=str(product.stock_level),
        department=product.department,
        pickup=product.pickup,
        delivery=product.delivery,
    )


def _line_to_parsed(line: ListLine) -> product_extraction.ParsedLine:
    return product_extraction.ParsedLine(quantity=line.quantity, unit=line.unit, food=line.food, note=line.note)


async def _extract_products(lines: list[ListLine]) -> dict[str, list[product_extraction.ExtractedProduct]]:
    """P4 batch extraction with a per-item P4-single fallback (A.4)."""
    client = deps.get_llm_client()
    result: dict[str, list[product_extraction.ExtractedProduct]] = {ln.id: [] for ln in lines}
    parsed_lines = [_line_to_parsed(ln) for ln in lines]
    try:
        out = await client.structured(
            product_extraction.render_batch(product_extraction.ProductExtractionInput(lines=parsed_lines)),
            product_extraction.ProductExtractionOutput,
        )
        for item in out.items:
            if 0 <= item.index < len(lines):
                result[lines[item.index].id] = item.products
        # Fill any line the batch skipped via the single fallback.
        missing = [ln for ln in lines if not result[ln.id]]
    except LLMError as exc:
        logger.info("batch product extraction failed, falling back per-item: %s", exc)
        missing = list(lines)

    for ln in missing:
        try:
            single = await client.structured(
                product_extraction.render_single(_line_to_parsed(ln)),
                product_extraction.ProductExtractionSingleOutput,
            )
            result[ln.id] = single.products or [
                product_extraction.ExtractedProduct(search_term=ln.food, package_quantity=1, confidence=0.3)
            ]
        except LLMError:
            # Never drop the line: search on the food name at low confidence.
            result[ln.id] = [
                product_extraction.ExtractedProduct(search_term=ln.food, package_quantity=1, confidence=0.2)
            ]
    return result


async def _rank(term: str, target_size: str | None, package_qty: int, products: list[Product]) -> list[Product]:
    """LLM-rank products (P5); returns products best-first, or [] if none acceptable."""
    if not products:
        return []
    ranking_in = product_ranking.ProductRankingInput(
        search_term=term,
        target_size=target_size,
        package_quantity=package_qty,
        products=[
            product_ranking.RankableProduct(
                description=p.description or "",
                size=p.size,
                price=p.price.regular if p.price else None,
                sale_price=p.price.promo if p.price else None,
                department=p.department,
            )
            for p in products
        ],
    )
    try:
        out = await deps.get_llm_client().structured(
            product_ranking.render(ranking_in), product_ranking.ProductRankingOutput
        )
    except LLMError as exc:
        logger.info("product ranking failed for %r; using search order: %s", term, exc)
        return products
    if out.none_acceptable or not out.ranked:
        return []
    ordered = [products[r.index] for r in out.ranked if 0 <= r.index < len(products)]
    return ordered or products


async def _match_one(item: MatchItem, location_id: str, fulfillment: str | None) -> MatchItem:
    """Search + rank + substitute for one extracted product."""
    try:
        products = await deps.kroger_search_products(
            None, item.search_term, location_id, limit=_SEARCH_LIMIT, fulfillment=fulfillment
        )
    except KrogerError as exc:
        item.status = ItemStatus.FAILED
        item.error = getattr(exc, "message", str(exc))
        return item

    ranked = await _rank(item.search_term, item.target_size, item.count, products)
    if not ranked:
        item.status = ItemStatus.NOT_FOUND
        return item

    selection = select_product(ranked, fulfillment=fulfillment)
    item.status = _STATUS_MAP[selection.status]
    if selection.chosen is not None:
        item.chosen = _product_ref(selection.chosen)
        item.alternatives = [
            Alternative(alternative_id=alt.upc, **_product_ref(alt).model_dump()) for alt in selection.alternatives
        ]
    return item


def _estimated_total(items: list[MatchItem]) -> float:
    total = 0.0
    for it in items:
        if it.status in (ItemStatus.MATCHED, ItemStatus.SUBSTITUTED, ItemStatus.STOCK_UNKNOWN) and it.chosen:
            if it.chosen.price is not None:
                total += it.chosen.price * max(it.count, 1)
    return round(total, 2)


async def run_match(plan_id: str) -> None:
    """Background entrypoint: build the cart draft, then open the review gate."""
    from remy_api.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        plan = await session.get(Plan, plan_id)
        if plan is None or plan.status != PlanStatus.MATCHING:
            return
        user_id = plan.user_id
        settings_row = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        settings = settings_row.scalar_one_or_none()
        location_id = settings.store_location_id if settings else None
        fulfillment = (settings.fulfillment_method.lower() if settings else "pickup") or "pickup"
        list_state = ListState(**(plan.list_lines or {}))
        approved = [ln for ln in list_state.lines if ln.included and ln.group.value == "to_buy"]

        warnings: list[str] = []
        # Kroger connection is only needed to *execute*; warn early (A/§7.4).
        token = (await session.execute(select(KrogerToken).where(KrogerToken.user_id == user_id))).scalar_one_or_none()
        if token is None:
            warnings.append("kroger_not_connected")

        if not location_id:
            plan.matches = CartState(
                status=MatchStage.ERROR, warnings=warnings, error="No preferred store selected."
            ).model_dump(mode="json")
            plan.status = PlanStatus.REVIEWING_CART
            await session.commit()
            return

    # Extract search terms (own session-less LLM work).
    extraction = await _extract_products(approved)
    items: list[MatchItem] = []
    line_by_id = {ln.id: ln for ln in approved}
    for line_id, products in extraction.items():
        line = line_by_id[line_id]
        for prod in products:
            items.append(
                MatchItem(
                    id=uuid.uuid4().hex,
                    line_id=line_id,
                    search_term=prod.search_term,
                    target_size=prod.target_size,
                    count=max(prod.package_quantity, 1),
                    confidence=prod.confidence,
                    status=ItemStatus.MATCHING,
                )
            )
        # A line the extractor returned nothing for still needs a visible row.
        if not products:
            items.append(
                MatchItem(
                    id=uuid.uuid4().hex,
                    line_id=line_id,
                    search_term=line.food,
                    count=1,
                    status=ItemStatus.MATCHING,
                )
            )

    async with factory() as session:
        plan = await session.get(Plan, plan_id)
        if plan is None or plan.status != PlanStatus.MATCHING:
            return
        plan.matches = CartState(status=MatchStage.MATCHING, items=items, warnings=warnings).model_dump(mode="json")
        await session.commit()

    write_lock = asyncio.Lock()
    sem = asyncio.Semaphore(_ITEM_CONCURRENCY)

    async def _do(item: MatchItem) -> None:
        async with sem:
            try:
                resolved = await _match_one(item, location_id, fulfillment)
            except KrogerNotConnectedError:
                raise
            except Exception as exc:  # noqa: BLE001 - never let one item sink the run
                logger.warning("match item %s crashed: %s", item.id, exc)
                item.status = ItemStatus.FAILED
                item.error = str(exc)
                resolved = item
        async with write_lock, factory() as s:
            plan = await s.get(Plan, plan_id)
            if plan is None or plan.status == PlanStatus.ABANDONED:
                return
            cart = CartState(**(plan.matches or {}))
            cart.items = [resolved if it.id == resolved.id else it for it in cart.items]
            cart.estimated_total = _estimated_total(cart.items)
            plan.matches = cart.model_dump(mode="json")
            await s.commit()

    await asyncio.gather(*(_do(it) for it in items))

    async with factory() as session:
        plan = await session.get(Plan, plan_id)
        if plan is None or plan.status != PlanStatus.MATCHING:
            return
        cart = CartState(**(plan.matches or {}))
        cart.status = MatchStage.READY
        cart.estimated_total = _estimated_total(cart.items)
        plan.matches = cart.model_dump(mode="json")
        plan.status = PlanStatus.REVIEWING_CART
        await session.commit()


# --- cart edit operations (FR-15) --------------------------------------------


async def apply_cart_edits(session, plan: Plan, ops: list) -> None:  # noqa: ANN001
    """Apply swap/drop/set_count/manual_search to the cart draft (reviewing_cart)."""
    cart = CartState(**(plan.matches or {}))
    by_id = {it.id: it for it in cart.items}

    location_id = None
    fulfillment = "pickup"
    needs_kroger = any(op.op == "manual_search" for op in ops)
    if needs_kroger:
        settings = (
            await session.execute(select(UserSettings).where(UserSettings.user_id == plan.user_id))
        ).scalar_one_or_none()
        location_id = settings.store_location_id if settings else None
        fulfillment = (settings.fulfillment_method.lower() if settings else "pickup") or "pickup"

    for op in ops:
        item = by_id.get(op.item_id)
        if item is None:
            continue
        if op.op == "drop":
            item.status = ItemStatus.DROPPED
            item.chosen = None
        elif op.op == "set_count" and op.count is not None:
            item.count = max(int(op.count), 1)
        elif op.op == "swap" and op.alternative_id:
            alt = next((a for a in item.alternatives if a.alternative_id == op.alternative_id), None)
            if alt is not None:
                previous = item.chosen
                item.alternatives = [a for a in item.alternatives if a.alternative_id != op.alternative_id]
                if previous is not None:
                    item.alternatives.insert(0, Alternative(alternative_id=previous.upc, **previous.model_dump()))
                item.chosen = ProductRef(**alt.model_dump(exclude={"alternative_id"}))
                item.status = ItemStatus.MATCHED
        elif op.op == "manual_search" and op.term and location_id:
            item.search_term = op.term
            item.status = ItemStatus.MATCHING
            item.chosen = None
            item.alternatives = []
            try:
                await _match_one(item, location_id, fulfillment)
            except KrogerError as exc:
                item.status = ItemStatus.FAILED
                item.error = getattr(exc, "message", str(exc))

    cart.estimated_total = _estimated_total(cart.items)
    plan.matches = cart.model_dump(mode="json")
    await session.commit()
