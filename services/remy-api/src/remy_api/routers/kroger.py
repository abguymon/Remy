"""Kroger router - OAuth and store management"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.auth import get_current_user
from remy_api.database import KrogerToken, User, UserSettings, get_db
from remy_api.models import KrogerAuthResponse, KrogerStatusResponse
from remy_api.services.mcp_client import call_kroger_tool, parse_mcp_result

router = APIRouter()


@router.get("/auth", response_model=KrogerAuthResponse)
async def start_kroger_auth(current_user: User = Depends(get_current_user)):
    """
    Start Kroger OAuth flow.
    Returns the authorization URL for the user to visit.
    """
    result = await call_kroger_tool("start_authentication", user_id=current_user.id)
    auth_data = parse_mcp_result(result)

    if auth_data is None or "auth_url" not in str(auth_data):
        # Try to extract from raw result
        if result and hasattr(result, "content"):
            try:
                import json

                data = json.loads(result.content[0].text)
                if "auth_url" in data:
                    return KrogerAuthResponse(auth_url=data["auth_url"])
            except Exception:
                pass

        raise HTTPException(status_code=500, detail="Failed to start Kroger authentication")

    return KrogerAuthResponse(auth_url=auth_data.get("auth_url", ""))


@router.get("/callback")
async def kroger_callback(
    code: str, state: str, request: Request, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Handle Kroger OAuth callback.
    Exchanges the authorization code for tokens.
    """
    result = await call_kroger_tool("complete_authentication", {"code": code, "state": state}, user_id=current_user.id)
    token_data = parse_mcp_result(result)

    if token_data is None:
        raise HTTPException(status_code=400, detail="Failed to complete Kroger authentication")

    # Store tokens in database
    existing = await db.execute(select(KrogerToken).where(KrogerToken.user_id == current_user.id))
    kroger_token = existing.scalar_one_or_none()

    if kroger_token is None:
        kroger_token = KrogerToken(user_id=current_user.id)
        db.add(kroger_token)

    kroger_token.access_token = token_data.get("access_token")
    kroger_token.refresh_token = token_data.get("refresh_token")

    # Parse expiry
    expires_in = token_data.get("expires_in", 1800)
    kroger_token.expires_at = datetime.utcnow() + __import__("datetime").timedelta(seconds=expires_in)

    await db.commit()

    return {"status": "connected", "message": "Successfully connected to Kroger!"}


@router.get("/status", response_model=KrogerStatusResponse)
async def get_kroger_status(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Check if the user is connected to Kroger"""
    result = await db.execute(select(KrogerToken).where(KrogerToken.user_id == current_user.id))
    token = result.scalar_one_or_none()

    if token is None or token.access_token is None:
        return KrogerStatusResponse(connected=False)

    return KrogerStatusResponse(connected=True, expires_at=token.expires_at)


@router.delete("/disconnect")
async def disconnect_kroger(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Disconnect Kroger account"""
    result = await db.execute(select(KrogerToken).where(KrogerToken.user_id == current_user.id))
    token = result.scalar_one_or_none()

    if token:
        await db.delete(token)
        await db.commit()

    return {"status": "disconnected"}


@router.get("/stores")
async def search_stores(
    zip_code: str | None = None, limit: int = 5, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Search for nearby Kroger stores"""
    # Get user's zip code if not provided
    if not zip_code:
        result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
        settings = result.scalar_one_or_none()
        if settings:
            zip_code = settings.zip_code

    if not zip_code:
        raise HTTPException(status_code=400, detail="Zip code required")

    result = await call_kroger_tool("search_locations", {"zip_code": zip_code, "limit": limit}, user_id=current_user.id)
    stores = parse_mcp_result(result)

    if stores is None:
        return {"stores": []}

    return {"stores": stores if isinstance(stores, list) else stores.get("data", [])}


@router.post("/stores/{location_id}/select")
async def select_store(
    location_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Set the user's preferred Kroger store"""
    # Get store details
    result = await call_kroger_tool("get_location_details", {"location_id": location_id}, user_id=current_user.id)
    store_data = parse_mcp_result(result)

    store_name = None
    if store_data:
        store_name = store_data.get("name", store_data.get("chain", "Kroger"))

    # Update user settings
    existing = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = existing.scalar_one_or_none()

    if settings is None:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    settings.store_location_id = location_id
    settings.store_name = store_name

    await db.commit()

    # Also set in Kroger MCP
    await call_kroger_tool("set_preferred_location", {"location_id": location_id}, user_id=current_user.id)

    return {"status": "selected", "location_id": location_id, "store_name": store_name}
