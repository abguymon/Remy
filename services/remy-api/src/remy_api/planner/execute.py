"""Execute step (FR-16–FR-17): write the real Kroger cart, record the order.

Runs synchronously in ``POST /plan/cart/execute``. Kroger connection is checked
*before* any status change or write — an unconnected user gets a clean 409
(``kroger_not_connected``) and the plan stays in ``reviewing_cart`` so they can
connect and retry (never attempt a write without a connection). Per-item outcomes
are reported truthfully by merging the cart's match status with the real cart-add
result (added / substituted / stock_unknown / failed). An ``orders`` row is
persisted as the local shadow record (the API can't read the real cart back).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.kroger.errors import KrogerNotConnectedError
from remy_api.kroger.models import OutcomeStatus
from remy_api.models import KrogerToken, Order, Plan, PlanStatus, UserSettings
from remy_api.planner import deps
from remy_api.planner.schemas import (
    CartState,
    ExecItem,
    ExecStatus,
    ExecutionState,
    ItemStatus,
)

logger = logging.getLogger("remy.planner.execute")

# Cart statuses whose chosen product is eligible to be added to the real cart.
_ADDABLE = {ItemStatus.MATCHED, ItemStatus.SUBSTITUTED, ItemStatus.STOCK_UNKNOWN}


async def execute_plan(session: AsyncSession, plan: Plan) -> None:
    """Add the confirmed cart draft to the real Kroger cart and record the order."""
    cart = CartState(**(plan.matches or {}))
    addable = [it for it in cart.items if it.status in _ADDABLE and it.chosen]

    # Connection check FIRST — before any status change or write (§7.4, FR-16).
    token = (await session.execute(select(KrogerToken).where(KrogerToken.user_id == plan.user_id))).scalar_one_or_none()
    if token is None:
        raise KrogerNotConnectedError("Kroger not connected — visit Settings to connect your account.")

    settings = (
        await session.execute(select(UserSettings).where(UserSettings.user_id == plan.user_id))
    ).scalar_one_or_none()
    modality = settings.fulfillment_method.value if settings else "PICKUP"

    plan.status = PlanStatus.EXECUTING
    await session.commit()

    request_items = [{"upc": it.chosen.upc, "quantity": max(it.count, 1), "modality": modality} for it in addable]
    outcomes = await deps.kroger_add_items_to_cart(session, plan.user_id, request_items) if request_items else []
    outcome_by_upc = {o.upc: o for o in outcomes}

    exec_items: list[ExecItem] = []
    any_failed = False
    any_added = False
    for it in addable:
        outcome = outcome_by_upc.get(it.chosen.upc)
        if outcome is not None and outcome.status == OutcomeStatus.ADDED:
            any_added = True
            status = {
                ItemStatus.SUBSTITUTED: "substituted",
                ItemStatus.STOCK_UNKNOWN: "stock_unknown",
            }.get(it.status, "added")
            reason = None
        else:
            any_failed = True
            status = "failed"
            reason = outcome.reason if outcome else "Not submitted."
        exec_items.append(
            ExecItem(
                upc=it.chosen.upc,
                description=it.chosen.description,
                quantity=max(it.count, 1),
                price=it.chosen.price,
                status=status,
                reason=reason,
            )
        )
    # Surface not-found / dropped lines truthfully too.
    for it in cart.items:
        if it.status == ItemStatus.NOT_FOUND:
            exec_items.append(ExecItem(upc="", description=it.search_term, quantity=it.count, status="unavailable"))

    if any_failed and any_added:
        exec_status = ExecStatus.PARTIAL
    elif any_failed:
        exec_status = ExecStatus.FAILED
    else:
        exec_status = ExecStatus.DONE

    order = Order(
        user_id=plan.user_id,
        plan_id=plan.id,
        items=[ei.model_dump(mode="json") for ei in exec_items],
        estimated_total=cart.estimated_total,
    )
    session.add(order)
    await session.flush()

    plan.execution_results = ExecutionState(
        status=exec_status,
        items=exec_items,
        estimated_total=cart.estimated_total,
        order_id=order.id,
        warnings=cart.warnings,
    ).model_dump(mode="json")
    plan.status = PlanStatus.DONE
    await session.commit()
