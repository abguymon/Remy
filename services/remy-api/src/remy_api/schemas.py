"""Pydantic request/response models for the auth, user, and token endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from remy_api.kroger import banner_cart_url
from remy_api.models import FulfillmentMethod


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class InvitationRegister(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=1024)
    invitation_token: str = Field(min_length=32, max_length=512)


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime


# --- admin: user management --------------------------------------------------


class AdminUserInfo(BaseModel):
    """A user row for the admin console. Never carries password data."""

    id: str
    username: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    kroger_connected: bool


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=255)


class AdminUserCreated(BaseModel):
    """Returned once on creation — includes the server-generated temp password."""

    id: str
    username: str
    temp_password: str


class TempPasswordResponse(BaseModel):
    """A reset temp password, returned exactly once."""

    temp_password: str


class InvitationCreate(BaseModel):
    recipient_label: str | None = Field(default=None, max_length=255)
    expires_in_days: int = Field(default=7, ge=1, le=30)


class InvitationInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recipient_label: str | None
    created_at: datetime
    expires_at: datetime
    redeemed_at: datetime | None
    revoked_at: datetime | None


class InvitationCreated(InvitationInfo):
    """The raw token is returned once and is never persisted."""

    invitation_token: str


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pantry_items: list[str]
    favorite_sites: list[str]
    store_location_id: str | None
    store_name: str | None
    store_chain: str | None
    zip_code: str | None
    fulfillment_method: FulfillmentMethod

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cart_url(self) -> str:
        """Banner-aware Kroger cart handoff URL for this user's selected store."""
        return banner_cart_url(self.store_chain or self.store_name)


class SettingsUpdate(BaseModel):
    """All fields optional — only provided fields are updated (partial PUT)."""

    pantry_items: list[str] | None = None
    favorite_sites: list[str] | None = None
    store_location_id: str | None = None
    store_name: str | None = None
    store_chain: str | None = None
    zip_code: str | None = None
    fulfillment_method: FulfillmentMethod | None = None


class PasswordChange(BaseModel):
    """Change the current user's password (verify current, set new)."""

    current_password: str = Field(min_length=1)
    # Minimal sanity floor — a too-short new password is a 422 before any hashing.
    new_password: str = Field(min_length=12, max_length=1024)


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ApiTokenInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiTokenCreated(ApiTokenInfo):
    """Returned once on creation — includes the plaintext token."""

    token: str
