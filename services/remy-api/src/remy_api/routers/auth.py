"""Authentication routes. Login only — no registration, no invite codes (§6)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from remy_api.config import get_settings
from remy_api.deps import SessionDep
from remy_api.errors import AuthenticationError
from remy_api.models import User
from remy_api.schemas import LoginRequest, TokenResponse
from remy_api.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    row = await session.execute(select(User).where(User.username == payload.username))
    user = row.scalar_one_or_none()
    # Uniform error + always run the hash verify path to avoid user enumeration.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AuthenticationError("Invalid username or password.")
    if not user.is_active:
        raise AuthenticationError("Account is disabled.")

    settings = get_settings()
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_in=settings.jwt_expire_hours * 3600)
