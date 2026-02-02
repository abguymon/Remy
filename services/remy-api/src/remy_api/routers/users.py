"""Users router - profile and settings management"""

import json
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from remy_api.auth import get_current_user
from remy_api.database import InviteCode, KrogerToken, User, UserSettings, get_db
from remy_api.models import (
    InviteCodeCreate,
    InviteCodeResponse,
    KrogerStatusResponse,
    MealieConnect,
    UserResponse,
    UserSettingsResponse,
    UserSettingsUpdate,
)

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user's profile"""
    return current_user


@router.get("/me/settings", response_model=UserSettingsResponse)
async def get_user_settings(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get current user's settings"""

    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if settings is None:
        # Create default settings if they don't exist
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    # Parse JSON fields
    pantry_items = json.loads(settings.pantry_items) if settings.pantry_items else []
    recipe_sources = json.loads(settings.recipe_sources) if settings.recipe_sources else []

    return UserSettingsResponse(
        pantry_items=pantry_items,
        recipe_sources=recipe_sources,
        store_location_id=settings.store_location_id,
        store_name=settings.store_name,
        zip_code=settings.zip_code,
        fulfillment_method=settings.fulfillment_method,
        mealie_api_key=settings.mealie_api_key[:8] + "..." if settings.mealie_api_key else None,
        mealie_connected=settings.mealie_api_key is not None,
    )


@router.put("/me/settings", response_model=UserSettingsResponse)
async def update_user_settings(
    data: UserSettingsUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Update current user's settings"""

    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if settings is None:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    # Update fields if provided
    if data.pantry_items is not None:
        settings.pantry_items = json.dumps(data.pantry_items)

    if data.recipe_sources is not None:
        settings.recipe_sources = json.dumps(data.recipe_sources)

    if data.store_location_id is not None:
        settings.store_location_id = data.store_location_id

    if data.store_name is not None:
        settings.store_name = data.store_name

    if data.zip_code is not None:
        settings.zip_code = data.zip_code

    if data.fulfillment_method is not None:
        settings.fulfillment_method = data.fulfillment_method

    await db.commit()
    await db.refresh(settings)

    # Parse JSON fields for response
    pantry_items = json.loads(settings.pantry_items) if settings.pantry_items else []
    recipe_sources = json.loads(settings.recipe_sources) if settings.recipe_sources else []

    return UserSettingsResponse(
        pantry_items=pantry_items,
        recipe_sources=recipe_sources,
        store_location_id=settings.store_location_id,
        store_name=settings.store_name,
        zip_code=settings.zip_code,
        fulfillment_method=settings.fulfillment_method,
        mealie_api_key=settings.mealie_api_key[:8] + "..." if settings.mealie_api_key else None,
        mealie_connected=settings.mealie_api_key is not None,
    )


@router.put("/me/mealie", response_model=UserSettingsResponse)
async def connect_mealie(
    data: MealieConnect, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Connect Mealie account by saving API key"""

    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if settings is None:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    settings.mealie_api_key = data.api_key

    await db.commit()
    await db.refresh(settings)

    # Parse JSON fields for response
    pantry_items = json.loads(settings.pantry_items) if settings.pantry_items else []
    recipe_sources = json.loads(settings.recipe_sources) if settings.recipe_sources else []

    return UserSettingsResponse(
        pantry_items=pantry_items,
        recipe_sources=recipe_sources,
        store_location_id=settings.store_location_id,
        store_name=settings.store_name,
        zip_code=settings.zip_code,
        fulfillment_method=settings.fulfillment_method,
        mealie_api_key=settings.mealie_api_key[:8] + "..." if settings.mealie_api_key else None,
        mealie_connected=settings.mealie_api_key is not None,
    )


@router.delete("/me/mealie")
async def disconnect_mealie(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Disconnect Mealie account"""

    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    if settings:
        settings.mealie_api_key = None
        await db.commit()

    return {"status": "disconnected"}


@router.get("/me/kroger", response_model=KrogerStatusResponse)
async def get_kroger_status(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get Kroger connection status"""

    result = await db.execute(select(KrogerToken).where(KrogerToken.user_id == current_user.id))
    token = result.scalar_one_or_none()

    if token is None or token.access_token is None:
        return KrogerStatusResponse(connected=False)

    return KrogerStatusResponse(connected=True, expires_at=token.expires_at)


# Invite code management (for admin/owner)
@router.post("/invite-codes", response_model=InviteCodeResponse)
async def create_invite_code(
    data: InviteCodeCreate | None = None, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Create a new invite code (any authenticated user can create invites)"""

    code = secrets.token_urlsafe(16)

    invite = InviteCode(code=code, email=data.email if data else None)
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    return InviteCodeResponse(code=invite.code, email=invite.email, created_at=invite.created_at, used=False)


@router.get("/invite-codes", response_model=list[InviteCodeResponse])
async def list_invite_codes(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """List all invite codes (shows which are used)"""

    result = await db.execute(select(InviteCode).order_by(InviteCode.created_at.desc()))
    invites = result.scalars().all()

    return [
        InviteCodeResponse(code=inv.code, email=inv.email, created_at=inv.created_at, used=inv.used_by is not None)
        for inv in invites
    ]
