"""Order history — the local shadow record of what Remy added to Kroger (FR-17).

Orders are written by the planner's execute step (see ``planner/execute.py``); no
endpoint creates them. This router only exposes the user-scoped, newest-first
list that the Cart-as-record screen (DESIGN_BRIEF §4.9) reads. It never touches
Kroger — the real cart lives on kroger.com (FR-18).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from remy_api.deps import CurrentUser, SessionDep
from remy_api.models import Order

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderRecord(BaseModel):
    """One past execution: per-item outcomes + estimated total snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    plan_id: str | None
    items: list
    estimated_total: float | None
    created_at: datetime


@router.get("", response_model=list[OrderRecord])
async def list_orders(
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[OrderRecord]:
    rows = await session.execute(
        select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(limit).offset(offset)
    )
    return [OrderRecord.model_validate(o) for o in rows.scalars().all()]
