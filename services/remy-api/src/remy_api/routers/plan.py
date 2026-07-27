"""Plan flow API — the golden path gates + the polling state endpoint (T5).

Every route is authed via :data:`CurrentUser` and operates on the caller's single
active plan. ``GET /plan/state`` is the polling endpoint the web UI (DESIGN_BRIEF
§4.2–4.6) and the MCP facade (T6) read for granular per-unit progress. Wrong-state
operations return 409 with the current status; a second create is 409.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, status
from fastapi import Path as PathParam
from fastapi.responses import FileResponse

from remy_api.deps import CurrentUser, SessionDep
from remy_api.errors import NotFoundError
from remy_api.planner import machine
from remy_api.planner.schemas import (
    CartEditRequest,
    ListEditRequest,
    PlanCreate,
    PlanSnapshot,
    RetryRequest,
    SelectRequest,
)
from remy_api.search import thumbnail_cache_path

router = APIRouter(prefix="/plan", tags=["plan"])


@router.post("", response_model=PlanSnapshot, status_code=status.HTTP_201_CREATED)
async def create_plan(payload: PlanCreate, user: CurrentUser, session: SessionDep) -> PlanSnapshot:
    plan = await machine.create_plan(session, user, payload.text)
    return machine.snapshot(plan)


@router.get("/thumbnails/{cache_key}", response_class=FileResponse)
async def get_thumbnail(
    cache_key: Annotated[str, PathParam(pattern=r"^[0-9a-f]{64}$")],
    _user: CurrentUser,
) -> FileResponse:
    """Serve a cached public-web thumbnail through the authenticated API."""
    image_path = thumbnail_cache_path(cache_key)
    if not image_path.is_file():
        raise NotFoundError("Thumbnail not found.")
    return FileResponse(
        image_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/state", response_model=PlanSnapshot)
async def get_state(user: CurrentUser, session: SessionDep) -> PlanSnapshot:
    plan = await machine.get_active_plan(session, user.id)
    if plan is None:
        raise NotFoundError("No active plan.")
    return machine.snapshot(plan)


@router.post("/select", response_model=PlanSnapshot)
async def select(payload: SelectRequest, user: CurrentUser, session: SessionDep) -> PlanSnapshot:
    plan = await machine.submit_selection(session, user, payload.choices)
    return machine.snapshot(plan)


@router.post("/list/edits", response_model=PlanSnapshot)
async def list_edits(payload: ListEditRequest, user: CurrentUser, session: SessionDep) -> PlanSnapshot:
    plan = await machine.list_edits(session, user, payload.ops)
    return machine.snapshot(plan)


@router.post("/list/approve", response_model=PlanSnapshot)
async def approve_list(user: CurrentUser, session: SessionDep) -> PlanSnapshot:
    plan = await machine.approve_list(session, user)
    return machine.snapshot(plan)


@router.post("/cart/edits", response_model=PlanSnapshot)
async def cart_edits(payload: CartEditRequest, user: CurrentUser, session: SessionDep) -> PlanSnapshot:
    plan = await machine.cart_edits(session, user, payload.ops)
    return machine.snapshot(plan)


@router.post("/cart/execute", response_model=PlanSnapshot)
async def execute_cart(user: CurrentUser, session: SessionDep) -> PlanSnapshot:
    plan = await machine.execute_cart(session, user)
    return machine.snapshot(plan)


@router.post("/retry", response_model=PlanSnapshot)
async def retry(payload: RetryRequest, user: CurrentUser, session: SessionDep) -> PlanSnapshot:
    plan = await machine.retry(session, user, payload.scope, payload.id)
    return machine.snapshot(plan)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def abandon(user: CurrentUser, session: SessionDep) -> None:
    await machine.abandon(session, user)
