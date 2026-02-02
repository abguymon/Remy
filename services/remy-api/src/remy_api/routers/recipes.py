"""Recipes router - recipe search and meal planning workflow"""

import json

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.auth import get_current_user
from remy_api.database import User, UserSettings, get_db
from remy_api.models import RecipeOption, RecipePlanRequest, RecipeSearchRequest
from remy_api.services.langgraph import run_workflow

router = APIRouter()


async def get_user_context(user: User, db: AsyncSession) -> tuple[str | None, list[str]]:
    """Get user's Mealie API key and pantry items"""
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    settings = result.scalar_one_or_none()

    mealie_api_key = None
    pantry_items = []

    if settings:
        mealie_api_key = settings.mealie_api_key
        if settings.pantry_items:
            pantry_items = json.loads(settings.pantry_items)

    return mealie_api_key, pantry_items


@router.post("/search", response_model=list[RecipeOption])
async def search_recipes(
    data: RecipeSearchRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Search for recipes based on a query.
    Returns recipe options from Mealie (and optionally web).
    """
    mealie_api_key, pantry_items = await get_user_context(current_user, db)

    # Run the workflow with the search query
    input_state = {"messages": [HumanMessage(content=data.query)]}

    result = await run_workflow(
        user_id=current_user.id,
        input_state=input_state,
        command="invoke",
        mealie_api_key=mealie_api_key,
        pantry_items=pantry_items,
    )

    recipe_options = result.get("recipe_options", [])

    return [
        RecipeOption(
            name=opt.get("name", ""),
            source=opt.get("source", "unknown"),
            url=opt.get("url"),
            image_url=opt.get("image_url"),
            slug=opt.get("slug"),
        )
        for opt in recipe_options
    ]


@router.post("/plan")
async def start_meal_plan(
    data: RecipePlanRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Start a meal planning workflow.
    This initiates the workflow and returns the current state.
    """
    mealie_api_key, pantry_items = await get_user_context(current_user, db)

    input_state = {"messages": [HumanMessage(content=data.message)]}

    result = await run_workflow(
        user_id=current_user.id,
        input_state=input_state,
        command="invoke",
        mealie_api_key=mealie_api_key,
        pantry_items=pantry_items,
    )

    # Extract relevant state for response
    return {
        "status": "in_progress",
        "recipe_options": result.get("recipe_options", []),
        "pending_cart": result.get("pending_cart", []),
        "messages": [msg.content for msg in result.get("messages", []) if hasattr(msg, "content")],
    }


@router.get("/plan/state")
async def get_plan_state(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Get the current state of the meal planning workflow.
    """
    mealie_api_key, pantry_items = await get_user_context(current_user, db)

    result = await run_workflow(
        user_id=current_user.id, command="get_state", mealie_api_key=mealie_api_key, pantry_items=pantry_items
    )

    return {
        "recipe_options": result.get("recipe_options", []),
        "selected_recipe_options": result.get("selected_recipe_options", []),
        "fetched_recipes": result.get("fetched_recipes", []),
        "pending_cart": result.get("pending_cart", []),
        "approved_cart": result.get("approved_cart", []),
        "order_result": result.get("order_result"),
        "messages": [msg.content for msg in result.get("messages", []) if hasattr(msg, "content")],
    }


@router.post("/plan/select")
async def select_recipes(
    selected: list[dict], current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Select recipes from the options and continue the workflow.
    """
    mealie_api_key, pantry_items = await get_user_context(current_user, db)

    # Update state with selection
    await run_workflow(
        user_id=current_user.id,
        input_state={"selected_recipe_options": selected},
        command="update_state",
        mealie_api_key=mealie_api_key,
        pantry_items=pantry_items,
    )

    # Continue workflow
    result = await run_workflow(
        user_id=current_user.id, command="invoke", mealie_api_key=mealie_api_key, pantry_items=pantry_items
    )

    return {
        "status": "recipes_fetched",
        "fetched_recipes": result.get("fetched_recipes", []),
        "pending_cart": result.get("pending_cart", []),
        "messages": [msg.content for msg in result.get("messages", []) if hasattr(msg, "content")],
    }


@router.post("/plan/approve")
async def approve_cart(
    approved_items: list[dict], current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Approve cart items and execute the order.
    """
    mealie_api_key, pantry_items = await get_user_context(current_user, db)

    # Get user settings for fulfillment
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = result.scalar_one_or_none()

    fulfillment_method = "PICKUP"
    store_id = None
    if settings:
        fulfillment_method = settings.fulfillment_method or "PICKUP"
        store_id = settings.store_location_id

    # Update state with approval
    await run_workflow(
        user_id=current_user.id,
        input_state={
            "approved_cart": approved_items,
            "fulfillment_method": fulfillment_method,
            "preferred_store_id": store_id,
        },
        command="update_state",
        mealie_api_key=mealie_api_key,
        pantry_items=pantry_items,
    )

    # Continue workflow to execute order
    result = await run_workflow(
        user_id=current_user.id, command="invoke", mealie_api_key=mealie_api_key, pantry_items=pantry_items
    )

    return {
        "status": "completed",
        "order_result": result.get("order_result"),
        "messages": [msg.content for msg in result.get("messages", []) if hasattr(msg, "content")],
    }


@router.delete("/plan")
async def reset_plan(current_user: User = Depends(get_current_user)):
    """
    Reset the meal planning workflow for the user.
    This clears the checkpoint and starts fresh.
    """
    import os

    checkpoint_path = f"data/checkpoints/{current_user.id}.sqlite"
    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)

    return {"status": "reset", "message": "Meal plan cleared. Start fresh with a new search."}
