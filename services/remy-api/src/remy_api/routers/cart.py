"""Cart router - Kroger cart management"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.auth import get_current_user
from remy_api.database import User, UserSettings, get_db
from remy_api.models import AddToCartRequest, CartItem, CartResponse
from remy_api.services.mcp_client import call_kroger_tool, parse_mcp_result

router = APIRouter()


@router.get("", response_model=CartResponse)
async def get_cart(current_user: User = Depends(get_current_user)):
    """Get the current user's Kroger cart"""
    result = await call_kroger_tool("get_cart", user_id=current_user.id)
    cart_data = parse_mcp_result(result)

    if cart_data is None:
        return CartResponse(items=[], total=None)

    items = []
    for item in cart_data.get("items", []):
        items.append(
            CartItem(
                product_id=item.get("product_id", item.get("upc", "")),
                name=item.get("name", item.get("description", "")),
                quantity=item.get("quantity", 1),
                price=item.get("price"),
                image_url=item.get("image_url"),
            )
        )

    return CartResponse(items=items, total=cart_data.get("total"))


@router.post("/add")
async def add_to_cart(
    data: AddToCartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add an item to the Kroger cart"""
    # Get user's fulfillment settings
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    modality = "PICKUP"
    if settings and settings.fulfillment_method:
        modality = settings.fulfillment_method

    result = await call_kroger_tool(
        "add_items_to_cart",
        {"product_id": data.product_id, "quantity": data.quantity, "modality": modality},
        user_id=current_user.id,
    )

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to add item to cart")

    return {"status": "added", "product_id": data.product_id, "quantity": data.quantity}


@router.delete("/{product_id}")
async def remove_from_cart(product_id: str, current_user: User = Depends(get_current_user)):
    """Remove an item from the Kroger cart"""
    result = await call_kroger_tool("remove_from_cart", {"product_id": product_id}, user_id=current_user.id)

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to remove item from cart")

    return {"status": "removed", "product_id": product_id}


@router.post("/clear")
async def clear_cart(current_user: User = Depends(get_current_user)):
    """Clear all items from the Kroger cart"""
    result = await call_kroger_tool("clear_cart", user_id=current_user.id)

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to clear cart")

    return {"status": "cleared"}


@router.get("/search")
async def search_products(
    q: str, limit: int = 10, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Search for products in Kroger"""
    # Get user's store location
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    location_id = None
    if settings:
        location_id = settings.store_location_id

    search_args = {"search_term": q, "limit": limit}
    if location_id:
        search_args["location_id"] = location_id

    result = await call_kroger_tool("search_products", search_args, user_id=current_user.id)
    products = parse_mcp_result(result)

    if products is None:
        return {"products": []}

    return {"products": products if isinstance(products, list) else products.get("data", [])}
