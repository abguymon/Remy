"""Database models and session management"""

import os
import uuid
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from remy_api.config import get_settings


class Base(DeclarativeBase):
    """Base class for all models"""

    pass


class User(Base):
    """User account model"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    settings: Mapped["UserSettings"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    kroger_token: Mapped["KrogerToken"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserSettings(Base):
    """User settings and preferences"""

    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    pantry_items: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    recipe_sources: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    store_location_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    store_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fulfillment_method: Mapped[str] = mapped_column(String(50), default="PICKUP")
    mealie_api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationship
    user: Mapped["User"] = relationship(back_populates="settings")


class KrogerToken(Base):
    """Kroger OAuth tokens per user"""

    __tablename__ = "kroger_tokens"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationship
    user: Mapped["User"] = relationship(back_populates="kroger_token")


class InviteCode(Base):
    """Invite codes for registration"""

    __tablename__ = "invite_codes"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Optional: restrict to specific email
    used_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# Database engine and session
_engine = None
_async_session_maker = None


async def init_db():
    """Initialize database and create tables"""
    global _engine, _async_session_maker

    settings = get_settings()
    _engine = create_async_engine(settings.database_url, echo=settings.debug)
    _async_session_maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create initial invite code if configured via environment variable
    initial_code = os.environ.get("INITIAL_INVITE_CODE")
    if initial_code:
        async with _async_session_maker() as session:
            from sqlalchemy import select

            result = await session.execute(select(InviteCode).where(InviteCode.code == initial_code))
            existing = result.scalar_one_or_none()

            if not existing:
                invite = InviteCode(code=initial_code)
                session.add(invite)
                await session.commit()
                print(f"Created initial invite code: {initial_code}")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency"""
    if _async_session_maker is None:
        await init_db()

    async with _async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
