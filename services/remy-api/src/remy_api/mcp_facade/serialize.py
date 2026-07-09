"""Compact JSON shaping for MCP tool returns (PRD §7.4 "rich structured returns").

Every shape here is derived from the same :class:`PlanSnapshot` the web UI and
``GET /plan/state`` use — the facade never computes anything itself, it only
projects the persisted plan state into the compact form an agent renders in
chat. Candidates carry title/source/url/thumbnail; matched items carry the
product's name/size/price/stock plus a substitution flag and up to 3
alternatives (each with a stable ``alternative_id`` so a swap is a reference,
not a re-search).
"""

from __future__ import annotations

from remy_api.planner.schemas import (
    CartState,
    ItemStatus,
    ListState,
    MatchItem,
    PlanSnapshot,
    ProductRef,
)

# Cart-line statuses that represent a chosen product still in the draft.
_LIVE = {ItemStatus.MATCHED, ItemStatus.SUBSTITUTED, ItemStatus.STOCK_UNKNOWN}


def candidates_view(snapshot: PlanSnapshot) -> dict:
    """Per-meal candidate lists for ``find_recipes`` (FR-2/FR-4)."""
    meals = []
    for meal in snapshot.meals:
        block = snapshot.candidates.get(meal.id)
        cands = []
        if block is not None:
            for c in block.candidates:
                cands.append(
                    {
                        "candidate_id": c.id,
                        "title": c.title,
                        "source": c.source_domain,
                        "url": c.url,
                        "saved_recipe_id": c.saved_recipe_id,
                        "thumbnail": c.thumbnail,
                        "total_time": c.total_time,
                        "origin": str(c.origin),
                        "preselected": c.preselected,
                    }
                )
        meals.append(
            {
                "meal_id": meal.id,
                "meal": meal.verbatim,
                "query": meal.query,
                "status": str(block.status) if block else "pending",
                "source_errors": list(block.source_errors) if block else [],
                "candidates": cands,
            }
        )
    return {
        "plan_draft_id": snapshot.plan_id,
        "plan_status": str(snapshot.status),
        "needs_input": snapshot.needs_input,
        "meals": meals,
    }


def selections_view(snapshot: PlanSnapshot) -> dict:
    """Parsed-recipe summary after ``select_recipes`` (FR-6–FR-8)."""
    sels = []
    for meal in snapshot.meals:
        s = snapshot.selections.get(meal.id)
        if s is None:
            sels.append({"meal_id": meal.id, "meal": meal.verbatim, "status": "pending"})
            continue
        sels.append(
            {
                "meal_id": meal.id,
                "meal": meal.verbatim,
                "status": str(s.status),
                "recipe_id": s.recipe_id,
                "recipe_title": s.recipe_title,
                "error": s.error,
            }
        )
    return {
        "plan_draft_id": snapshot.plan_id,
        "plan_status": str(snapshot.status),
        "selections": sels,
    }


def _line_view(line) -> dict:  # noqa: ANN001
    return {
        "line_id": line.id,
        "food": line.food,
        "display": line.display,
        "quantity": line.quantity,
        "unit": line.unit,
        "note": line.note,
        "included": line.included,
        "conflict": line.conflict,
        "from_recipes": [c.recipe_title for c in line.contributing],
    }


def shopping_list_view(snapshot: PlanSnapshot) -> dict:
    """Consolidated list grouped to-buy / pantry-skipped / excluded (FR-9–FR-12)."""
    ls: ListState = snapshot.shopping_list
    to_buy, pantry, excluded = [], [], []
    for line in ls.lines:
        group = line.group.value
        if not line.included and group != "pantry_skipped":
            excluded.append(_line_view(line))
        elif group == "pantry_skipped":
            pantry.append(_line_view(line))
        else:
            to_buy.append(_line_view(line))
    return {
        "plan_draft_id": snapshot.plan_id,
        "plan_status": str(snapshot.status),
        "list_status": str(ls.status),
        "to_buy": to_buy,
        "pantry_skipped": pantry,
        "excluded": excluded,
    }


def _product_view(p: ProductRef | None) -> dict | None:
    if p is None:
        return None
    return {
        "upc": p.upc,
        "name": p.description,
        "brand": p.brand,
        "size": p.size,
        "price": p.price,
        "stock": p.stock_level,
        "department": p.department,
        "image": p.image_url,
        "pickup": p.pickup,
        "delivery": p.delivery,
    }


def _match_item_view(item: MatchItem) -> dict:
    chosen = _product_view(item.chosen)
    alternatives = []
    for alt in item.alternatives[:3]:
        view = _product_view(alt)
        if view is not None:
            view["alternative_id"] = alt.alternative_id
            alternatives.append(view)
    return {
        "line_id": item.id,
        "search_term": item.search_term,
        "status": str(item.status),
        "count": item.count,
        "is_substitution": item.status == ItemStatus.SUBSTITUTED,
        "confidence": item.confidence,
        "error": item.error,
        "product": chosen,
        "alternatives": alternatives,
    }


def cart_view(snapshot: PlanSnapshot) -> dict:
    """Matched cart draft for ``match_products``/``swap_product`` (FR-13–FR-15)."""
    cart: CartState = snapshot.cart
    return {
        "cart_draft_id": cart.cart_draft_id,
        "plan_draft_id": snapshot.plan_id,
        "plan_status": str(snapshot.status),
        "match_status": str(cart.status),
        "estimated_total": cart.estimated_total,
        "estimated_total_note": "Estimate from current prices; the real cart total is set at checkout on kroger.com.",
        "warnings": list(cart.warnings),
        "items": [_match_item_view(it) for it in cart.items],
    }


def execution_view(snapshot: PlanSnapshot) -> dict:
    """Truthful per-item outcome report for ``execute_cart`` (FR-16–FR-17)."""
    ex = snapshot.execution
    if ex is None:
        return {"plan_draft_id": snapshot.plan_id, "status": str(snapshot.status), "items": []}
    return {
        "plan_draft_id": snapshot.plan_id,
        "status": str(ex.status),
        "estimated_total": ex.estimated_total,
        "kroger_cart_url": ex.kroger_cart_url,
        "checkout_note": "Items were added to your real Kroger cart. Open the link to schedule pickup and pay.",
        "warnings": list(ex.warnings),
        "items": [
            {
                "name": i.description,
                "upc": i.upc or None,
                "quantity": i.quantity,
                "price": i.price,
                "status": i.status,
                "reason": i.reason,
            }
            for i in ex.items
        ],
    }
