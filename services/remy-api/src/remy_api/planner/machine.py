"""The plan state machine (PRD §4): a plain, persisted, forward-only workflow.

There is exactly one active plan per user (a second create is a 409). Status only
advances (``discovering → selecting → reviewing_list → matching → reviewing_cart →
executing → done``) plus ``abandoned`` from anywhere. Each gate is a plain async
function that reads the ``plans`` row, does its work, and writes the next status.

Design decisions:

* **Locking.** A per-user in-process ``asyncio.Lock`` serializes mutating requests
  so two concurrent calls can't race the same row; combined with a status check at
  each gate, it also guards against double-invoking a step (a second ``approve``
  while ``matching`` is a 409). Reads (``GET /plan/state``) take no lock.
* **Background tasks.** The two long fan-out steps (discover, match) run as
  detached ``asyncio`` tasks with their own DB sessions, updating per-unit status
  in the JSON columns as they go, so ``GET /plan/state`` polls granular progress.
  Tests await :func:`drain` to run a launched task to completion deterministically.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.errors import ConflictError, NotFoundError
from remy_api.models import Plan, PlanStatus, User, UserSettings
from remy_api.observability import bind_observation_context
from remy_api.planner import deps, discover, execute, listing, matching, select_step
from remy_api.planner.schemas import (
    CartState,
    ExecutionState,
    ItemStatus,
    ListState,
    MatchStage,
    Meal,
    MealCandidates,
    PlanSnapshot,
    SelectionState,
)
from remy_api.prompts import meal_extraction

logger = logging.getLogger("remy.planner.machine")

_TERMINAL = {PlanStatus.DONE, PlanStatus.ABANDONED}

_locks: dict[str, asyncio.Lock] = {}
_tasks: dict[str, asyncio.Task] = {}


def _lock(user_id: str) -> asyncio.Lock:
    lock = _locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user_id] = lock
    return lock


def _launch(user_id: str, session_id: str, coro) -> None:  # noqa: ANN001
    """Run ``coro`` as a detached background task, one per user."""

    async def _runner() -> None:
        try:
            with bind_observation_context(user_id=user_id, session_id=session_id):
                await coro
        except Exception:  # noqa: BLE001 - background failures are logged, never crash the loop
            logger.exception("background step failed for user %s", user_id)

    task = asyncio.create_task(_runner())
    _tasks[user_id] = task
    task.add_done_callback(lambda t: _tasks.pop(user_id, None) if _tasks.get(user_id) is t else None)


async def drain(user_id: str) -> None:
    """Await the user's current background task if any (test/inspection helper)."""
    task = _tasks.get(user_id)
    if task is not None:
        await task


# --- plan lookup -------------------------------------------------------------


async def get_active_plan(session: AsyncSession, user_id: str) -> Plan | None:
    row = await session.execute(
        select(Plan)
        .where(Plan.user_id == user_id, Plan.status.notin_(list(_TERMINAL)))
        .order_by(Plan.created_at.desc())
    )
    return row.scalars().first()


async def _require_active(session: AsyncSession, user_id: str) -> Plan:
    plan = await get_active_plan(session, user_id)
    if plan is None:
        raise NotFoundError("No active plan.")
    return plan


def _require_status(plan: Plan, expected: PlanStatus) -> None:
    if plan.status != expected:
        raise ConflictError(
            f"Operation not valid in status '{plan.status}'.",
            code="wrong_state",
        )


# --- create / discover -------------------------------------------------------


async def _extract_meals(text: str) -> list[Meal]:
    out = await deps.get_llm_client().structured(
        meal_extraction.render(meal_extraction.MealExtractionInput(text=text)),
        meal_extraction.MealExtractionOutput,
    )
    return [
        Meal(id=uuid.uuid4().hex, query=m.query, verbatim=m.verbatim, is_specific=m.is_specific, url=m.url)
        for m in out.meals
    ]


def _needs_input(plan: Plan) -> bool:
    return plan.status == PlanStatus.DISCOVERING and not (plan.meals or [])


async def create_plan(session: AsyncSession, user: User, text: str) -> Plan:
    """Create (or re-seed a needs-input) plan, extract meals (P1), start discover."""
    async with _lock(user.id):
        active = await get_active_plan(session, user.id)
        if active is not None and not _needs_input(active):
            raise ConflictError(
                f"You already have a plan in progress (status '{active.status}').",
                code="plan_active",
            )

        plan_id = active.id if active is not None else str(uuid.uuid4())
        with bind_observation_context(user_id=user.id, session_id=plan_id):
            meals = await _extract_meals(text)
        meals_json = [m.model_dump(mode="json") for m in meals]

        if active is not None:  # re-seed the needs-input plan in place
            plan = active
            plan.meals = meals_json
            plan.candidates = None
            plan.selections = None
            plan.list_lines = None
            plan.matches = None
            plan.execution_results = None
            plan.status = PlanStatus.DISCOVERING
        else:
            plan = Plan(id=plan_id, user_id=user.id, status=PlanStatus.DISCOVERING, meals=meals_json)
            session.add(plan)
        await session.commit()
        await session.refresh(plan)
        plan_id = plan.id

    if meals:
        _launch(user.id, plan_id, discover.run_discover(plan_id))
    return plan


# --- select ------------------------------------------------------------------


async def submit_selection(session: AsyncSession, user: User, choices: list) -> Plan:
    async with _lock(user.id):
        plan = await _require_active(session, user.id)
        _require_status(plan, PlanStatus.SELECTING)
        with bind_observation_context(user_id=plan.user_id, session_id=plan.id):
            await select_step.process_select(session, plan, choices)
        await session.refresh(plan)
        return plan


# --- list --------------------------------------------------------------------


async def list_edits(session: AsyncSession, user: User, ops: list) -> Plan:
    async with _lock(user.id):
        plan = await _require_active(session, user.id)
        _require_status(plan, PlanStatus.REVIEWING_LIST)
        with bind_observation_context(user_id=plan.user_id, session_id=plan.id):
            await listing.apply_list_edits(plan, ops)
        await session.commit()
        await session.refresh(plan)
        return plan


async def approve_list(session: AsyncSession, user: User) -> Plan:
    async with _lock(user.id):
        plan = await _require_active(session, user.id)
        _require_status(plan, PlanStatus.REVIEWING_LIST)
        settings = (
            await session.execute(select(UserSettings).where(UserSettings.user_id == user.id))
        ).scalar_one_or_none()
        if settings is None or not settings.store_location_id:
            raise ConflictError(
                "Select a preferred store in Settings before matching products.",
                code="no_store_selected",
            )
        plan.status = PlanStatus.MATCHING
        # Seed an empty matching cart so polling shows the transition immediately.
        # Mint the cart_draft_id here (MCP draft-id chain, PRD §7.4); run_match
        # preserves it, and a fresh match/approve re-mints a new one.
        plan.matches = CartState(status=MatchStage.MATCHING, cart_draft_id=uuid.uuid4().hex).model_dump(mode="json")
        await session.commit()
        plan_id = plan.id
    _launch(user.id, plan_id, matching.run_match(plan_id))
    return await session.get(Plan, plan_id)


# --- cart / execute ----------------------------------------------------------


async def cart_edits(session: AsyncSession, user: User, ops: list) -> Plan:
    async with _lock(user.id):
        plan = await _require_active(session, user.id)
        _require_status(plan, PlanStatus.REVIEWING_CART)
        await matching.apply_cart_edits(session, plan, ops)
        await session.refresh(plan)
        return plan


async def execute_cart(session: AsyncSession, user: User, *, cart_draft_id: str | None = None) -> Plan:
    """Write the confirmed cart to the real Kroger cart.

    ``cart_draft_id`` is the MCP draft-id safety check (PRD §7.4): the web UI
    calls with ``None`` (it is already bound to the caller's active plan via the
    JWT), while the MCP ``execute_cart`` tool passes the id it was handed by
    ``match_products``. When provided it must match the id currently on the plan
    row — an unknown, foreign, or stale (post-re-match) id is rejected before any
    cart write, so an agent can never fabricate a cart execution.
    """
    async with _lock(user.id):
        plan = await _require_active(session, user.id)
        _require_status(plan, PlanStatus.REVIEWING_CART)
        if cart_draft_id is not None:
            current = (plan.matches or {}).get("cart_draft_id")
            if not current or current != cart_draft_id:
                raise ConflictError(
                    "Unknown or stale cart_draft_id. Run match_products to get the current "
                    "cart draft for this plan before executing.",
                    code="invalid_cart_draft",
                )
        await execute.execute_plan(session, plan)
        await session.refresh(plan)
        return plan


# --- retry -------------------------------------------------------------------


async def retry(session: AsyncSession, user: User, scope: str, target_id: str) -> Plan:
    async with _lock(user.id):
        plan = await _require_active(session, user.id)
        if scope == "meal":
            await _retry_meal(session, plan, target_id)
        elif scope == "item":
            await _retry_item(session, plan, target_id)
        else:
            raise ConflictError(f"Unknown retry scope '{scope}'.", code="bad_retry_scope")
        await session.refresh(plan)
        return plan


async def _retry_meal(session: AsyncSession, plan: Plan, meal_id: str) -> None:
    if plan.status != PlanStatus.SELECTING:
        raise ConflictError(f"Cannot retry a meal in status '{plan.status}'.", code="wrong_state")
    meal_dict = next((m for m in (plan.meals or []) if m["id"] == meal_id), None)
    if meal_dict is None:
        raise NotFoundError("Meal not found in this plan.")
    settings = (
        await session.execute(select(UserSettings).where(UserSettings.user_id == plan.user_id))
    ).scalar_one_or_none()
    favorite_sites = list(settings.favorite_sites) if settings else []
    with bind_observation_context(user_id=plan.user_id, session_id=plan.id):
        mc = await discover.discover_meal(Meal(**meal_dict), favorite_sites, plan.user_id)
    current = dict(plan.candidates or {})
    current[meal_id] = mc.model_dump(mode="json")
    plan.candidates = current
    await session.commit()


async def _retry_item(session: AsyncSession, plan: Plan, item_id: str) -> None:
    if plan.status != PlanStatus.REVIEWING_CART:
        raise ConflictError(f"Cannot retry an item in status '{plan.status}'.", code="wrong_state")
    cart = CartState(**(plan.matches or {}))
    item = next((it for it in cart.items if it.id == item_id), None)
    if item is None:
        raise NotFoundError("Cart item not found.")
    settings = (
        await session.execute(select(UserSettings).where(UserSettings.user_id == plan.user_id))
    ).scalar_one_or_none()
    location_id = settings.store_location_id if settings else None
    fulfillment = (settings.fulfillment_method.lower() if settings else "pickup") or "pickup"
    if location_id:
        item.status = ItemStatus.MATCHING
        item.chosen = None
        item.alternatives = []
        with bind_observation_context(user_id=plan.user_id, session_id=plan.id):
            await matching._match_one(item, location_id, fulfillment)
        cart.items = [item if it.id == item.id else it for it in cart.items]
        cart.estimated_total = matching._estimated_total(cart.items)
        plan.matches = cart.model_dump(mode="json")
        await session.commit()


# --- abandon -----------------------------------------------------------------


async def abandon(session: AsyncSession, user: User) -> None:
    async with _lock(user.id):
        plan = await get_active_plan(session, user.id)
        if plan is None:
            raise NotFoundError("No active plan to abandon.")
        plan.status = PlanStatus.ABANDONED
        await session.commit()
    task = _tasks.get(user.id)
    if task is not None:
        task.cancel()


# --- snapshot ----------------------------------------------------------------


def snapshot(plan: Plan) -> PlanSnapshot:
    """Assemble the full ``GET /plan/state`` snapshot from the persisted columns."""
    meals = [Meal(**m) for m in (plan.meals or [])]
    candidates = {mid: MealCandidates(**block) for mid, block in (plan.candidates or {}).items()}
    selections = {mid: SelectionState(**s) for mid, s in (plan.selections or {}).items()}
    list_state = ListState(**plan.list_lines) if plan.list_lines else ListState()
    cart_state = CartState(**plan.matches) if plan.matches else CartState()
    execution = ExecutionState(**plan.execution_results) if plan.execution_results else None
    return PlanSnapshot(
        plan_id=plan.id,
        status=plan.status,
        created_at=plan.created_at.isoformat(),
        updated_at=plan.updated_at.isoformat(),
        needs_input=_needs_input(plan),
        meals=meals,
        candidates=candidates,
        selections=selections,
        shopping_list=list_state,
        cart=cart_state,
        execution=execution,
    )
