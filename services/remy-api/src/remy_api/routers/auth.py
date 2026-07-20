"""Authentication and invitation-redemption routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, update

from remy_api.config import get_settings
from remy_api.deps import SessionDep
from remy_api.errors import AuthenticationError, UnprocessableError
from remy_api.models import Invitation, User
from remy_api.rate_limit import check_login_rate_limit, check_registration_rate_limit
from remy_api.schemas import InvitationRegister, LoginRequest, TokenResponse, UserProfile
from remy_api.security import create_access_token, hash_invitation_token, verify_password
from remy_api.user_service import create_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, session: SessionDep, _rate: None = Depends(check_login_rate_limit)
) -> TokenResponse:
    row = await session.execute(select(User).where(User.username == payload.username))
    user = row.scalar_one_or_none()
    # Uniform error + always run the hash verify path to avoid user enumeration.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AuthenticationError("Invalid username or password.")
    if not user.is_active:
        raise AuthenticationError("Account is disabled.")

    settings = get_settings()
    token = create_access_token(user.id, user.auth_version)
    return TokenResponse(access_token=token, expires_in=settings.jwt_expire_hours * 3600)


@router.post("/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
async def register_with_invitation(
    payload: InvitationRegister,
    session: SessionDep,
    _rate: None = Depends(check_registration_rate_limit),
) -> UserProfile:
    """Consume a one-time invite atomically, then create a normal user account."""
    now = datetime.now(UTC)
    consumed = await session.execute(
        update(Invitation)
        .where(
            Invitation.token_hash == hash_invitation_token(payload.invitation_token),
            Invitation.redeemed_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > now,
        )
        .values(redeemed_at=now)
        .returning(Invitation.id)
    )
    if consumed.scalar_one_or_none() is None:
        raise UnprocessableError(
            "This invitation is invalid, expired, or has already been used.", code="invalid_invitation"
        )

    # The same DB transaction includes consuming the invite and creating the
    # account. Any duplicate-user failure rolls back the consumption as well.
    user = await create_user(session, payload.username, payload.password, commit=False)
    await session.commit()
    await session.refresh(user)
    return UserProfile.model_validate(user)
