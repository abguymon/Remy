"""Pydantic models for API request/response schemas"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# Auth schemas
class UserRegister(BaseModel):
    """Registration request"""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    invite_code: str


class UserLogin(BaseModel):
    """Login request"""

    username: str
    password: str


class Token(BaseModel):
    """JWT token response"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefresh(BaseModel):
    """Token refresh request"""

    refresh_token: str


# User schemas
class UserResponse(BaseModel):
    """User profile response"""

    id: str
    username: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserSettingsResponse(BaseModel):
    """User settings response"""

    pantry_items: list[str] = []
    recipe_sources: list[dict] = []
    store_location_id: str | None = None
    store_name: str | None = None
    zip_code: str | None = None
    fulfillment_method: str = "PICKUP"
    mealie_api_key: str | None = None
    mealie_connected: bool = False

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    """User settings update request"""

    pantry_items: list[str] | None = None
    recipe_sources: list[dict] | None = None
    store_location_id: str | None = None
    store_name: str | None = None
    zip_code: str | None = None
    fulfillment_method: str | None = None


class MealieConnect(BaseModel):
    """Connect Mealie account request"""

    api_key: str


# Kroger schemas
class KrogerAuthResponse(BaseModel):
    """Kroger OAuth initiation response"""

    auth_url: str


class KrogerStatusResponse(BaseModel):
    """Kroger connection status"""

    connected: bool
    expires_at: datetime | None = None


# Recipe schemas
class RecipeSearchRequest(BaseModel):
    """Recipe search request"""

    query: str


class RecipeOption(BaseModel):
    """Recipe search result"""

    name: str
    source: str
    url: str | None = None
    image_url: str | None = None
    slug: str | None = None


class RecipePlanRequest(BaseModel):
    """Start meal planning request"""

    message: str


# Cart schemas
class CartItem(BaseModel):
    """Cart item"""

    product_id: str
    name: str
    quantity: int
    price: float | None = None
    image_url: str | None = None


class CartResponse(BaseModel):
    """Cart contents response"""

    items: list[CartItem]
    total: float | None = None


class AddToCartRequest(BaseModel):
    """Add item to cart request"""

    product_id: str
    quantity: int = 1


# Invite code schemas
class InviteCodeCreate(BaseModel):
    """Create invite code request (admin)"""

    email: str | None = None


class InviteCodeResponse(BaseModel):
    """Invite code response"""

    code: str
    email: str | None = None
    created_at: datetime
    used: bool
