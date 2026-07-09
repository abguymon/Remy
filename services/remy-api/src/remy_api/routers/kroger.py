"""Kroger OAuth connect flow + store selection endpoints (PRD §7.2, FR-21/22).

* ``GET  /kroger/auth``            authed — build authorize URL (state + PKCE S256)
* ``GET  /kroger/callback``        UNauthenticated browser redirect — exchange code
* ``GET  /kroger/status``          authed — connection status
* ``DELETE /kroger/disconnect``    authed — drop the stored token
* ``GET  /kroger/stores``          authed — search stores by ZIP
* ``POST /kroger/stores/{id}/select`` authed — persist preferred store

The callback is the only unauthenticated route: the browser arrives from
Kroger with no app JWT, so CSRF protection rests entirely on the opaque
``state`` (validated + single-use, 10-min TTL) tied to the user who started the
flow.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select

from remy_api.config import get_settings
from remy_api.deps import CurrentUser, SessionDep
from remy_api.errors import NotFoundError
from remy_api.kroger import (
    KrogerError,
    StoreLocation,
    generate_pkce,
    generate_state,
    get_client,
    get_location,
    get_locations,
    store_tokens,
)
from remy_api.models import FulfillmentMethod, KrogerToken, OAuthState, UserSettings

router = APIRouter(prefix="/kroger", tags=["kroger"])


def _settings_redirect(**params: str) -> RedirectResponse:
    # Where the browser lands after the OAuth round-trip. Relative by default so
    # it resolves to the deployed origin (Traefik serves web + /api on one host,
    # PRD §8); WEB_APP_URL overrides for split-origin dev (web :3000, api :8080).
    base = get_settings().web_app_url.rstrip("/")
    return RedirectResponse(url=f"{base}/settings?{urlencode(params)}", status_code=status.HTTP_302_FOUND)


class AuthUrlResponse(BaseModel):
    auth_url: str


class StatusResponse(BaseModel):
    connected: bool
    expires_at: datetime | None = None
    expired: bool = False


class StoreSelectResponse(BaseModel):
    store_location_id: str
    store_name: str | None
    zip_code: str | None


@router.get("/auth", response_model=AuthUrlResponse)
async def kroger_auth(user: CurrentUser, session: SessionDep) -> AuthUrlResponse:
    verifier, challenge = generate_pkce()
    state = generate_state()
    session.add(OAuthState(state=state, user_id=user.id, pkce_verifier=verifier))
    await session.commit()
    auth_url = get_client().build_authorize_url(state=state, code_challenge=challenge)
    return AuthUrlResponse(auth_url=auth_url)


@router.get("/callback")
async def kroger_callback(
    session: SessionDep,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    if error:
        return _settings_redirect(kroger="error", reason=error)
    if not code or not state:
        return _settings_redirect(kroger="error", reason="missing_code_or_state")

    oauth_state = await session.get(OAuthState, state)
    if oauth_state is None:
        return _settings_redirect(kroger="error", reason="invalid_state")
    user_id = oauth_state.user_id
    verifier = oauth_state.pkce_verifier
    expired = oauth_state.is_expired()
    # Single-use: delete the state whether or not it was valid.
    await session.execute(delete(OAuthState).where(OAuthState.state == state))
    await session.commit()
    if expired:
        return _settings_redirect(kroger="error", reason="state_expired")

    try:
        bundle = await get_client().exchange_code(code, verifier)
        await store_tokens(session, user_id, bundle)
    except KrogerError:
        return _settings_redirect(kroger="error", reason="exchange_failed")
    return _settings_redirect(kroger="connected")


@router.get("/status", response_model=StatusResponse)
async def kroger_status(user: CurrentUser, session: SessionDep) -> StatusResponse:
    row = await session.execute(select(KrogerToken).where(KrogerToken.user_id == user.id))
    token = row.scalar_one_or_none()
    if token is None:
        return StatusResponse(connected=False)
    from remy_api.kroger.service import _is_expired  # local import: internal helper

    return StatusResponse(connected=True, expires_at=token.expires_at, expired=_is_expired(token, skew=0))


@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def kroger_disconnect(user: CurrentUser, session: SessionDep) -> None:
    await session.execute(delete(KrogerToken).where(KrogerToken.user_id == user.id))
    await session.commit()


@router.get("/stores", response_model=list[StoreLocation])
async def kroger_stores(
    user: CurrentUser,  # noqa: ARG001 — auth-gated; store search uses the app token
    zip: str = Query(min_length=3, max_length=10),
    limit: int = Query(default=8, ge=1, le=50),
) -> list[StoreLocation]:
    return await get_locations(zip, limit=limit)


@router.post("/stores/{location_id}/select", response_model=StoreSelectResponse)
async def kroger_select_store(location_id: str, user: CurrentUser, session: SessionDep) -> StoreSelectResponse:
    store = await get_location(location_id)
    if store is None:
        raise NotFoundError("Kroger store not found.")

    row = await session.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    settings = row.scalar_one_or_none()
    if settings is None:
        settings = UserSettings(user_id=user.id, fulfillment_method=FulfillmentMethod.PICKUP)
        session.add(settings)
    settings.store_location_id = store.id
    settings.store_name = store.name
    if store.zip_code:
        settings.zip_code = store.zip_code
    await session.commit()
    return StoreSelectResponse(store_location_id=store.id, store_name=store.name, zip_code=settings.zip_code)
