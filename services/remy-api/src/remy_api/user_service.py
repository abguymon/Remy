"""User creation with default settings, shared by the CLI and API layers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.errors import ConflictError
from remy_api.models import User, UserSettings
from remy_api.security import hash_password
from remy_api.seed import default_favorite_sites, default_pantry_items


async def create_user(session: AsyncSession, username: str, password: str, *, is_admin: bool = False) -> User:
    """Create a user + seeded default settings. Raises on duplicate username.

    Shared by the CLI bootstrap, the ``import-mealie`` owner path, and the admin
    ``POST /admin/users`` endpoint so user creation + default-settings seeding
    lives in exactly one place.
    """
    existing = await session.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(f"User '{username}' already exists.", code="user_exists")

    user = User(username=username, password_hash=hash_password(password), is_admin=is_admin)
    user.settings = UserSettings(
        pantry_items=default_pantry_items(),
        favorite_sites=default_favorite_sites(),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
