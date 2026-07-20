"""Admin user-management routes (admin-only).

Every route is gated by the :func:`require_admin` dependency (403 ``admin_required``
otherwise). There is no user-delete in v1 — cascading a user would wipe their
recipes/plans/orders — so deactivation (which login and bearer auth already
enforce) is the off switch. Temp passwords are generated server-side and
returned exactly once, mirroring the API-token show-once contract.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, status
from sqlalchemy import select

from remy_api.deps import AdminUser, SessionDep
from remy_api.errors import NotFoundError, UnprocessableError
from remy_api.models import Invitation, KrogerToken, User
from remy_api.schemas import (
    AdminUserCreate,
    AdminUserCreated,
    AdminUserInfo,
    InvitationCreate,
    InvitationCreated,
    InvitationInfo,
    TempPasswordResponse,
)
from remy_api.security import generate_invitation_token, hash_password
from remy_api.user_service import create_user

router = APIRouter(prefix="/admin", tags=["admin"])

# 9 bytes → a 12-char url-safe temp password (secrets.token_urlsafe rounds up).
_TEMP_PASSWORD_BYTES = 9


def _temp_password() -> str:
    return secrets.token_urlsafe(_TEMP_PASSWORD_BYTES)


async def _kroger_connected(session: SessionDep, user_id: str) -> bool:
    row = await session.execute(select(KrogerToken.user_id).where(KrogerToken.user_id == user_id))
    return row.scalar_one_or_none() is not None


async def _load_user(session: SessionDep, user_id: str) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return user


async def _to_info(session: SessionDep, user: User) -> AdminUserInfo:
    return AdminUserInfo(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        kroger_connected=await _kroger_connected(session, user.id),
    )


@router.get("/users", response_model=list[AdminUserInfo])
async def list_users(_admin: AdminUser, session: SessionDep) -> list[AdminUserInfo]:
    users = (await session.execute(select(User).order_by(User.created_at))).scalars().all()
    connected = set((await session.execute(select(KrogerToken.user_id))).scalars().all())
    return [
        AdminUserInfo(
            id=u.id,
            username=u.username,
            is_admin=u.is_admin,
            is_active=u.is_active,
            created_at=u.created_at,
            kroger_connected=u.id in connected,
        )
        for u in users
    ]


@router.post("/users", response_model=AdminUserCreated, status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(payload: AdminUserCreate, _admin: AdminUser, session: SessionDep) -> AdminUserCreated:
    # Reuses the CLI/bootstrap create-user code path (user + seeded settings).
    temp_password = _temp_password()
    user = await create_user(session, payload.username, temp_password)
    return AdminUserCreated(id=user.id, username=user.username, temp_password=temp_password)


@router.post("/users/{user_id}/reset-password", response_model=TempPasswordResponse)
async def reset_password(user_id: str, _admin: AdminUser, session: SessionDep) -> TempPasswordResponse:
    user = await _load_user(session, user_id)
    temp_password = _temp_password()
    user.password_hash = hash_password(temp_password)
    user.auth_version += 1
    await session.commit()
    return TempPasswordResponse(temp_password=temp_password)


@router.post("/users/{user_id}/deactivate", response_model=AdminUserInfo)
async def deactivate_user(user_id: str, admin: AdminUser, session: SessionDep) -> AdminUserInfo:
    user = await _load_user(session, user_id)
    if user.id == admin.id:
        # Guard against an admin locking themselves out of the console.
        raise UnprocessableError("You cannot deactivate your own account.", code="cannot_deactivate_self")
    user.is_active = False
    await session.commit()
    return await _to_info(session, user)


@router.post("/users/{user_id}/activate", response_model=AdminUserInfo)
async def activate_user(user_id: str, _admin: AdminUser, session: SessionDep) -> AdminUserInfo:
    user = await _load_user(session, user_id)
    user.is_active = True
    await session.commit()
    return await _to_info(session, user)


@router.get("/invitations", response_model=list[InvitationInfo])
async def list_invitations(_admin: AdminUser, session: SessionDep) -> list[InvitationInfo]:
    rows = (await session.execute(select(Invitation).order_by(Invitation.created_at.desc()))).scalars().all()
    return [InvitationInfo.model_validate(inv) for inv in rows]


@router.post("/invitations", response_model=InvitationCreated, status_code=status.HTTP_201_CREATED)
async def create_invitation(payload: InvitationCreate, admin: AdminUser, session: SessionDep) -> InvitationCreated:
    token, token_hash = generate_invitation_token()
    invitation = Invitation(
        token_hash=token_hash,
        recipient_label=payload.recipient_label.strip() or None if payload.recipient_label else None,
        created_by_user_id=admin.id,
        expires_at=datetime.now(UTC) + timedelta(days=payload.expires_in_days),
    )
    session.add(invitation)
    await session.commit()
    await session.refresh(invitation)
    return InvitationCreated(
        id=invitation.id,
        recipient_label=invitation.recipient_label,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        redeemed_at=invitation.redeemed_at,
        revoked_at=invitation.revoked_at,
        invitation_token=token,
    )


@router.post("/invitations/{invitation_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(invitation_id: str, _admin: AdminUser, session: SessionDep) -> None:
    invitation = await session.get(Invitation, invitation_id)
    if invitation is None:
        raise NotFoundError("Invitation not found.")
    if invitation.redeemed_at is None and invitation.revoked_at is None:
        invitation.revoked_at = datetime.now(UTC)
        await session.commit()
