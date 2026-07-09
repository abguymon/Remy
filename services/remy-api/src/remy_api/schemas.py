"""Pydantic request/response models for the auth, user, and token endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from remy_api.models import FulfillmentMethod


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    is_active: bool
    created_at: datetime


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pantry_items: list[str]
    favorite_sites: list[str]
    store_location_id: str | None
    store_name: str | None
    zip_code: str | None
    fulfillment_method: FulfillmentMethod


class SettingsUpdate(BaseModel):
    """All fields optional — only provided fields are updated (partial PUT)."""

    pantry_items: list[str] | None = None
    favorite_sites: list[str] | None = None
    store_location_id: str | None = None
    store_name: str | None = None
    zip_code: str | None = None
    fulfillment_method: FulfillmentMethod | None = None


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
