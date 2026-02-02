"""Authentication router - login, register, token refresh"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from remy_api.config import get_settings
from remy_api.database import InviteCode, User, UserSettings, get_db
from remy_api.models import Token, TokenRefresh, UserLogin, UserRegister, UserResponse

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user with an invite code"""

    # Validate invite code
    result = await db.execute(select(InviteCode).where(InviteCode.code == data.invite_code))
    invite = result.scalar_one_or_none()

    if invite is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite code")

    if invite.used_by is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite code already used")

    if invite.email is not None and invite.email.lower() != data.email.lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite code is for a different email")

    # Check if username or email already exists
    result = await db.execute(select(User).where((User.username == data.username) | (User.email == data.email)))
    existing = result.scalar_one_or_none()

    if existing:
        if existing.username == data.username:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Create user
    user = User(
        username=data.username,
        email=data.email.lower(),
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()  # Get the user ID

    # Create default settings
    settings = UserSettings(user_id=user.id)
    db.add(settings)

    # Mark invite code as used
    invite.used_by = user.id
    invite.used_at = datetime.utcnow()

    await db.commit()
    await db.refresh(user)

    return user


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """Login with username and password, returns JWT tokens"""

    # Find user by username
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is disabled")

    settings = get_settings()
    access_token = create_access_token(user.id)

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expire_hours * 3600,
    )


@router.post("/login/json", response_model=Token)
async def login_json(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login with JSON body (alternative to form-based login)"""

    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is disabled")

    settings = get_settings()
    access_token = create_access_token(user.id)

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expire_hours * 3600,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    """Refresh an access token using a refresh token"""

    payload = decode_token(data.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = payload.get("sub")

    # Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    settings = get_settings()
    access_token = create_access_token(user.id)

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expire_hours * 3600,
    )
