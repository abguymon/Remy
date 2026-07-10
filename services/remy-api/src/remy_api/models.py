"""SQLAlchemy ORM models (PRD §5, §6).

Every user-owned table carries ``user_id`` with ``ON DELETE CASCADE`` so the
schema is multi-user-ready from day one (single-user UX in v1). Enums are stored
as strings (``native_enum=False``) and JSON via the portable ``JSON`` type so
Postgres remains a config swap. UUID string PKs avoid dialect-specific UUID
types.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from remy_api.crypto import EncryptedString
from remy_api.db import Base

OAUTH_STATE_TTL = timedelta(minutes=10)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class FulfillmentMethod(enum.StrEnum):
    PICKUP = "PICKUP"
    DELIVERY = "DELIVERY"


class PlanStatus(enum.StrEnum):
    DISCOVERING = "discovering"
    SELECTING = "selecting"
    REVIEWING_LIST = "reviewing_list"
    MATCHING = "matching"
    REVIEWING_CART = "reviewing_cart"
    EXECUTING = "executing"
    DONE = "done"
    ABANDONED = "abandoned"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    settings: Mapped[UserSettings | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    kroger_token: Mapped[KrogerToken | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    api_tokens: Mapped[list[ApiToken]] = relationship(back_populates="user", cascade="all, delete-orphan")
    recipes: Mapped[list[Recipe]] = relationship(back_populates="user", cascade="all, delete-orphan")
    plans: Mapped[list[Plan]] = relationship(back_populates="user", cascade="all, delete-orphan")
    orders: Mapped[list[Order]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    # Per-user pantry staples and favorite recipe-site domains (JSON arrays).
    pantry_items: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    favorite_sites: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    store_location_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    store_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Kroger banner chain code (e.g. "FRED", "QFC") — drives the banner-aware cart
    # handoff URL. Persisted on store select; nullable for stores chosen before
    # this column existed (the cart URL then falls back to the store name).
    store_chain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fulfillment_method: Mapped[FulfillmentMethod] = mapped_column(
        Enum(FulfillmentMethod, native_enum=False, length=16),
        nullable=False,
        default=FulfillmentMethod.PICKUP,
    )

    user: Mapped[User] = relationship(back_populates="settings")


class KrogerToken(Base):
    """The single Kroger token store (PRD §6). Tokens encrypted at rest."""

    __tablename__ = "kroger_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    access_token: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="kroger_token")


class OAuthState(Base):
    """Short-lived OAuth/PKCE state for the Kroger connect flow (10-min TTL)."""

    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pkce_verifier: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    def is_expired(self, now: datetime | None = None) -> bool:
        """True if this state is older than the TTL and must be rejected."""
        current = now or _now()
        created = self.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return current - created > OAUTH_STATE_TTL


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    slug: Mapped[str] = mapped_column(String(512), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Mealie slug for the one-shot import CLI (T3): dedicated dedupe key so a
    # re-run skips recipes already imported. Null for web-scraped/manual recipes.
    mealie_slug: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    recipe_yield: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prep_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cook_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Ordered list of instruction step strings.
    instructions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    last_cooked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="recipes")
    ingredients: Mapped[list[RecipeIngredient]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeIngredient.position",
        lazy="selectin",  # always eager-load: recipe reads need lines in async context
    )

    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_recipe_user_slug"),)


class RecipeIngredient(Base):
    """A single ingredient line: the raw text plus parsed components (FR-7/§6)."""

    __tablename__ = "recipe_ingredients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recipe_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw: Mapped[str] = mapped_column(Text, nullable=False)
    # Parsed {quantity, unit, food, note}; food is normalized singular lowercase.
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    food: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")


class Plan(Base):
    """Persisted workflow state — the checkpoint for the golden path (PRD §4)."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[PlanStatus] = mapped_column(
        Enum(PlanStatus, native_enum=False, length=32), nullable=False, default=PlanStatus.DISCOVERING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    # Per-step JSON blobs; child tables are unnecessary at household scale.
    meals: Mapped[list | None] = mapped_column(JSON, nullable=True)
    candidates: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    selections: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    list_lines: Mapped[list | None] = mapped_column(JSON, nullable=True)
    matches: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    execution_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user: Mapped[User] = relationship(back_populates="plans")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Per-item outcome + price snapshot (local shadow record; §6, FR-17).
    items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    estimated_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    user: Mapped[User] = relationship(back_populates="orders")


class ApiToken(Base):
    """Per-user bearer token for MCP clients (FR-26). Only the hash is stored."""

    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="api_tokens")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
