"""Kroger router - OAuth and store management"""

import json
import re
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.auth import get_current_user
from remy_api.config import get_settings
from remy_api.database import KrogerToken, OAuthState, User, UserSettings, get_db
from remy_api.models import KrogerAuthResponse, KrogerStatusResponse
from remy_api.services.mcp_client import call_kroger_tool, parse_mcp_result

router = APIRouter()


@router.get("/auth", response_model=KrogerAuthResponse)
async def start_kroger_auth(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Start Kroger OAuth flow.
    Returns the authorization URL for the user to visit.
    """
    result = await call_kroger_tool("start_authentication", user_id=current_user.id)
    auth_data = parse_mcp_result(result)

    auth_url = None
    if auth_data and isinstance(auth_data, dict):
        auth_url = auth_data.get("auth_url")

    if not auth_url:
        # Try to extract from raw result
        if result and hasattr(result, "content"):
            try:
                data = json.loads(result.content[0].text)
                auth_url = data.get("auth_url")
            except Exception:
                pass

    if not auth_url:
        raise HTTPException(status_code=500, detail="Failed to start Kroger authentication")

    # Extract the state parameter from the auth URL to map it to this user
    state_match = re.search(r"[?&]state=([^&]+)", auth_url)
    if state_match:
        state_value = state_match.group(1)

        # Clean up expired states (older than 10 minutes)
        cutoff = datetime.utcnow() - timedelta(minutes=10)
        expired = await db.execute(select(OAuthState).where(OAuthState.created_at < cutoff))
        for row in expired.scalars().all():
            await db.delete(row)

        # Save state → user_id mapping
        oauth_state = OAuthState(state=state_value, user_id=current_user.id)
        db.add(oauth_state)
        await db.commit()

    return KrogerAuthResponse(auth_url=auth_url)


@router.get("/callback")
async def kroger_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    """
    Handle Kroger OAuth callback.
    This is a browser redirect — no JWT auth required.
    Looks up the user from the OAuth state parameter.
    """
    settings = get_settings()

    # Look up user_id from the state parameter
    result = await db.execute(select(OAuthState).where(OAuthState.state == state))
    oauth_state = result.scalar_one_or_none()

    if oauth_state is None:
        return RedirectResponse(url=f"{settings.frontend_url}/settings?kroger=error&reason=invalid_state")

    # Check expiry (10 minute window)
    if datetime.utcnow() - oauth_state.created_at > timedelta(minutes=10):
        await db.delete(oauth_state)
        await db.commit()
        return RedirectResponse(url=f"{settings.frontend_url}/settings?kroger=error&reason=expired")

    user_id = oauth_state.user_id

    # Reconstruct the redirect URL as the MCP tool expects it
    redirect_url = f"{settings.kroger_redirect_uri}?code={quote(code)}&state={quote(state)}"
    mcp_result = await call_kroger_tool(
        "complete_authentication", {"redirect_url": redirect_url}, user_id=user_id
    )
    token_data = parse_mcp_result(mcp_result)

    if token_data is None:
        # Clean up state
        await db.delete(oauth_state)
        await db.commit()
        return RedirectResponse(url=f"{settings.frontend_url}/settings?kroger=error&reason=token_exchange_failed")

    # Store tokens in database
    existing = await db.execute(select(KrogerToken).where(KrogerToken.user_id == user_id))
    kroger_token = existing.scalar_one_or_none()

    if kroger_token is None:
        kroger_token = KrogerToken(user_id=user_id)
        db.add(kroger_token)

    kroger_token.access_token = token_data.get("access_token")
    kroger_token.refresh_token = token_data.get("refresh_token")

    # Parse expiry
    expires_in = token_data.get("expires_in", 1800)
    kroger_token.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Clean up the OAuth state record
    await db.delete(oauth_state)
    await db.commit()

    return RedirectResponse(url=f"{settings.frontend_url}/settings?kroger=connected")


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
