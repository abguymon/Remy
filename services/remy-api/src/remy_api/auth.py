"""Authentication utilities - JWT and password hashing"""

from datetime import datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.config import get_settings
from remy_api.database import User, get_db

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: str, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token"""
    settings = get_settings()

    if expires_delta is None:
        expires_delta = timedelta(hours=settings.jwt_expire_hours)

    expire = datetime.utcnow() + expires_delta
    to_encode = {"sub": user_id, "exp": expire, "type": "access"}

    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """Create a JWT refresh token (longer expiry)"""
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(days=30)
    to_encode = {"sub": user_id, "exp": expire, "type": "refresh"}

    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token"""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    """Get the current authenticated user from JWT token"""
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User | None:
    """Get current user if authenticated, None otherwise"""
    if token is None:
        return None
    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None
