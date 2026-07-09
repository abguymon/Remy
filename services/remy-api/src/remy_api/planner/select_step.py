"""Select step (FR-6–FR-8): resolve per-meal choices into saved recipes.

Runs synchronously in the ``POST /plan/select`` request. Each choice is a
candidate id, a pasted URL, or skip. Web/URL choices are scraped (recipe-scrapers
→ LLM fallback) and saved to the cookbook with a downloaded image (§1.1-8); saved
choices are loaded. A parse failure surfaces on that meal with the plan staying in
``selecting`` so the user can retry. Once every meal is resolved (and at least one
recipe is saved), the shopping list is built and the plan advances to
``reviewing_list``.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.models import Plan, PlanStatus
from remy_api.planner import deps, listing
from remy_api.planner.schemas import (
    Candidate,
    MealChoice,
    SelectionState,
    SelectionStatus,
)
from remy_api.recipes.llm_fallback import RecipeParseError

logger = logging.getLogger("remy.planner.select")


def _find_candidate(plan: Plan, meal_id: str, candidate_id: str) -> Candidate | None:
    meal_block = (plan.candidates or {}).get(meal_id)
    if not meal_block:
        return None
    for c in meal_block.get("candidates", []):
        if c.get("id") == candidate_id:
            return Candidate(**c)
    return None


async def _save_web_recipe(session: AsyncSession, user_id: str, url: str) -> tuple[str, str]:
    """Scrape ``url``, save to cookbook with image; return (recipe_id, title)."""
    parsed = await deps.scrape_recipe(url, llm=deps.get_prompt_id_llm())
    recipe = await deps.create_recipe(session, user_id, parsed)
    if parsed.image_url:
        stored = await deps.download_recipe_image(recipe.id, parsed.image_url)
        if stored:
            recipe.image_path = stored
            await session.commit()
            await session.refresh(recipe)
    return recipe.id, recipe.title


async def _process_choice(session: AsyncSession, plan: Plan, choice: MealChoice) -> SelectionState:
    sel = SelectionState(meal_id=choice.meal_id, choice=choice.choice)
    if choice.choice == "skip":
        sel.status = SelectionStatus.SKIPPED
        return sel

    # Resolve the target URL / saved recipe.
    url: str | None = choice.url
    saved_recipe_id: str | None = None
    if choice.choice == "candidate" and choice.candidate_id:
        cand = _find_candidate(plan, choice.meal_id, choice.candidate_id)
        if cand is None:
            sel.status = SelectionStatus.ERROR
            sel.error = "Unknown candidate for this meal."
            return sel
        sel.candidate_id = cand.id
        if cand.saved_recipe_id:
            saved_recipe_id = cand.saved_recipe_id
        else:
            url = cand.url

    try:
        if saved_recipe_id:
            recipe = await deps.get_recipe(session, plan.user_id, saved_recipe_id)
            sel.recipe_id, sel.recipe_title = recipe.id, recipe.title
        elif url:
            sel.url = url
            sel.recipe_id, sel.recipe_title = await _save_web_recipe(session, plan.user_id, url)
        else:
            sel.status = SelectionStatus.ERROR
            sel.error = "No candidate, URL, or skip provided."
            return sel
    except RecipeParseError as exc:
        sel.status = SelectionStatus.ERROR
        sel.error = exc.message
        return sel
    except Exception as exc:  # noqa: BLE001 - surface, never silently drop (§9.1)
        logger.warning("select failed for meal %s: %s", choice.meal_id, exc)
        sel.status = SelectionStatus.ERROR
        sel.error = str(exc)
        return sel

    sel.status = SelectionStatus.SAVED
    return sel


async def process_select(session: AsyncSession, plan: Plan, choices: list[MealChoice]) -> None:
    """Apply ``choices``, persist selections, and advance when fully resolved."""
    selections = dict(plan.selections or {})
    for choice in choices:
        sel = await _process_choice(session, plan, choice)
        selections[choice.meal_id] = sel.model_dump(mode="json")
    plan.selections = selections

    # Advance only when every meal is resolved (saved/skipped) with no errors,
    # and at least one recipe was actually saved.
    meal_ids = [m["id"] for m in (plan.meals or [])]
    states = {mid: SelectionState(**selections[mid]) for mid in meal_ids if mid in selections}
    all_resolved = len(states) == len(meal_ids) and all(
        s.status in (SelectionStatus.SAVED, SelectionStatus.SKIPPED) for s in states.values()
    )
    any_saved = any(s.status == SelectionStatus.SAVED for s in states.values())

    if all_resolved and any_saved:
        await listing.build_list(session, plan)
        plan.status = PlanStatus.REVIEWING_LIST
    await session.commit()
