"""Current-user routes: profile, settings, and API tokens (FR-21–FR-26)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import select

from remy_api.deps import CurrentUser, SessionDep
from remy_api.errors import NotFoundError
from remy_api.models import ApiToken, UserSettings
from remy_api.schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenInfo,
    SettingsResponse,
    SettingsUpdate,
    UserProfile,
)
from remy_api.security import generate_api_token
from remy_api.seed import default_favorite_sites, default_pantry_items

router = APIRouter(prefix="/users/me", tags=["users"])


async def _get_settings(session: SessionDep, user_id: str) -> UserSettings:
    row = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    settings = row.scalar_one_or_none()
    if settings is None:
        # Self-heal: a user should always have settings, but seed if missing.
        settings = UserSettings(
            user_id=user_id,
            pantry_items=default_pantry_items(),
            favorite_sites=default_favorite_sites(),
        )
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings


@router.get("", response_model=UserProfile)
async def get_me(user: CurrentUser) -> UserProfile:
    return UserProfile.model_validate(user)


@router.get("/settings", response_model=SettingsResponse)
async def get_settings_endpoint(user: CurrentUser, session: SessionDep) -> SettingsResponse:
    settings = await _get_settings(session, user.id)
    return SettingsResponse.model_validate(settings)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(payload: SettingsUpdate, user: CurrentUser, session: SessionDep) -> SettingsResponse:
    settings = await _get_settings(session, user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    await session.commit()
    await session.refresh(settings)
    return SettingsResponse.model_validate(settings)


# --- API tokens (FR-26) ------------------------------------------------------


@router.post("/api-tokens", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
async def create_api_token(payload: ApiTokenCreate, user: CurrentUser, session: SessionDep) -> ApiTokenCreated:
    full_token, token_hash = generate_api_token()
    token = ApiToken(user_id=user.id, name=payload.name, token_hash=token_hash)
    session.add(token)
    await session.commit()
    await session.refresh(token)
    # Plaintext token is returned exactly once and never stored.
    return ApiTokenCreated(
        id=token.id,
        name=token.name,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        revoked_at=token.revoked_at,
        token=full_token,
    )


@router.get("/api-tokens", response_model=list[ApiTokenInfo])
async def list_api_tokens(user: CurrentUser, session: SessionDep) -> list[ApiTokenInfo]:
    rows = await session.execute(
        select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc())
    )
    return [ApiTokenInfo.model_validate(t) for t in rows.scalars().all()]


@router.delete("/api-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_token(token_id: str, user: CurrentUser, session: SessionDep) -> None:
    token = await session.get(ApiToken, token_id)
    if token is None or token.user_id != user.id:
        # 404 (not 403) so a token id belonging to another user is indistinguishable.
        raise NotFoundError("API token not found.")
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        await session.commit()
