"""List step (FR-9–FR-12): ingredient parsing, consolidation, pantry bypass.

Runs synchronously inside the request that finishes selection (a handful of
recipes; not a long-running background step). For each selected recipe, parse its
raw ingredient lines with P4a (persisting the parse back onto the stored recipe so
the cookbook and future consolidations benefit), consolidate across all recipes
deterministically (FR-10), and split lines into to-buy vs pantry-skipped by
word-boundary match against the user's pantry staples (FR-11).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.llm.errors import LLMError
from remy_api.models import Plan, RecipeIngredient, UserSettings
from remy_api.planner import deps
from remy_api.planner.consolidation import ConsolidatedLine, ParsedContribution, classify_pantry, consolidate
from remy_api.planner.schemas import (
    ContributingRef,
    ListGroup,
    ListLine,
    ListState,
    ListStatus,
    SegmentModel,
    SelectionState,
    SelectionStatus,
)
from remy_api.prompts import ingredient_parsing

logger = logging.getLogger("remy.planner.listing")


async def _parse_recipe_lines(session: AsyncSession, recipe_id: str, recipe_title: str) -> list[ParsedContribution]:
    """Load a recipe's ingredient rows, parse with P4a, persist the parse."""
    rows = (
        (
            await session.execute(
                select(RecipeIngredient)
                .where(RecipeIngredient.recipe_id == recipe_id)
                .order_by(RecipeIngredient.position)
            )
        )
        .scalars()
        .all()
    )
    raw_lines = [r.raw for r in rows]
    if not raw_lines:
        return []

    parsed_by_index: dict[int, ingredient_parsing.ParsedIngredient] = {}
    try:
        out = await deps.get_llm_client().structured(
            ingredient_parsing.render(ingredient_parsing.IngredientParsingInput(lines=raw_lines)),
            ingredient_parsing.IngredientParsingOutput,
        )
        parsed_by_index = {p.index: p for p in out.ingredients if 0 <= p.index < len(raw_lines)}
    except LLMError as exc:
        # Never silent-empty: fall back to raw-as-food so the line still appears.
        logger.info("ingredient parsing failed for recipe %s: %s", recipe_id, exc)

    contributions: list[ParsedContribution] = []
    for i, row in enumerate(rows):
        parsed = parsed_by_index.get(i)
        if parsed is not None:
            # Persist the parse back onto the stored recipe line (enriches cookbook/FTS).
            row.quantity = parsed.quantity
            row.unit = parsed.unit
            row.food = parsed.food
            row.note = parsed.note
            food = parsed.food
            quantity = parsed.quantity
            unit = parsed.unit
            note = parsed.note
        else:
            food = (row.food or row.raw).strip().lower()
            quantity, unit, note = row.quantity, row.unit, row.note
        contributions.append(
            ParsedContribution(
                recipe_id=recipe_id,
                recipe_title=recipe_title,
                raw=row.raw,
                food=food,
                quantity=quantity,
                unit=unit,
                note=note,
            )
        )
    return contributions


def _to_list_line(line: ConsolidatedLine, is_pantry: bool) -> ListLine:
    return ListLine(
        id=uuid.uuid4().hex,
        food=line.food,
        display=line.display,
        quantity=line.quantity,
        unit=line.unit,
        note=line.note,
        group=ListGroup.PANTRY_SKIPPED if is_pantry else ListGroup.TO_BUY,
        included=not is_pantry,
        conflict=line.conflict,
        segments=[SegmentModel(unit=s.unit, quantity=s.quantity, display=s.display) for s in line.segments],
        contributing=[
            ContributingRef(
                recipe_id=c.recipe_id,
                recipe_title=c.recipe_title,
                raw=c.raw,
                quantity=c.quantity,
                unit=c.unit,
            )
            for c in line.contributing
        ],
    )


async def build_list(session: AsyncSession, plan: Plan) -> None:
    """Build ``plan.list_lines`` from the selected recipes (mutates + persists)."""
    selections = {mid: SelectionState(**s) for mid, s in (plan.selections or {}).items()}
    recipe_refs: list[tuple[str, str]] = []
    for sel in selections.values():
        if sel.status == SelectionStatus.SAVED and sel.recipe_id:
            recipe_refs.append((sel.recipe_id, sel.recipe_title or "recipe"))

    contributions: list[ParsedContribution] = []
    for recipe_id, title in recipe_refs:
        contributions.extend(await _parse_recipe_lines(session, recipe_id, title))
    # Persist the P4a enrichment written onto RecipeIngredient rows.
    await session.flush()

    consolidated = consolidate(contributions)
    settings_row = await session.execute(select(UserSettings).where(UserSettings.user_id == plan.user_id))
    settings = settings_row.scalar_one_or_none()
    pantry_items = list(settings.pantry_items) if settings else []
    pantry_map = classify_pantry([c.food for c in consolidated], pantry_items)

    lines = [_to_list_line(c, pantry_map.get(c.food, False)) for c in consolidated]
    plan.list_lines = ListState(status=ListStatus.READY, lines=lines).model_dump(mode="json")


# --- edit operations (FR-12) -------------------------------------------------


def _load_list(plan: Plan) -> ListState:
    return ListState(**(plan.list_lines or {"status": ListStatus.READY.value, "lines": []}))


def _display_for(food: str, quantity: float | None, unit: str | None) -> str:
    from remy_api.planner.consolidation import _fmt_number  # local: formatting helper

    if quantity is None:
        return food
    qty = _fmt_number(quantity)
    return f"{qty} {unit} {food}".replace("  ", " ").strip() if unit else f"{qty} {food}"


async def _parse_free_text(text: str) -> tuple[str, float | None, str | None, str | None]:
    """Parse a single free-text line via P4a; fall back to raw-as-food."""
    try:
        out = await deps.get_llm_client().structured(
            ingredient_parsing.render(ingredient_parsing.IngredientParsingInput(lines=[text])),
            ingredient_parsing.IngredientParsingOutput,
        )
        if out.ingredients:
            p = out.ingredients[0]
            return p.food, p.quantity, p.unit, p.note
    except LLMError as exc:
        logger.info("free-text parse failed for %r: %s", text, exc)
    return text.strip().lower(), None, None, None


async def apply_list_edits(plan: Plan, ops: list) -> None:
    """Apply include/exclude/set_quantity/add/delete ops to the plan's list."""
    state = _load_list(plan)
    by_id = {ln.id: ln for ln in state.lines}
    for op in ops:
        if op.op == "add" and op.text:
            food, quantity, unit, note = await _parse_free_text(op.text)
            state.lines.append(
                ListLine(
                    id=uuid.uuid4().hex,
                    food=food,
                    display=_display_for(food, quantity, unit),
                    quantity=quantity,
                    unit=unit,
                    note=note,
                    group=ListGroup.TO_BUY,
                    included=True,
                    free_text=True,
                )
            )
            continue
        line = by_id.get(op.line_id or "")
        if line is None:
            continue
        if op.op == "include":
            line.included = True
            line.group = ListGroup.TO_BUY
        elif op.op == "exclude":
            line.included = False
            line.group = ListGroup.USER_EXCLUDED
        elif op.op == "set_quantity":
            line.quantity = op.quantity
            if op.unit is not None:
                line.unit = op.unit
            line.conflict = False
            line.segments = [SegmentModel(unit=line.unit, quantity=line.quantity, display="")]
            line.display = _display_for(line.food, line.quantity, line.unit)
        elif op.op == "delete":
            state.lines = [ln for ln in state.lines if ln.id != line.id]
    plan.list_lines = state.model_dump(mode="json")
