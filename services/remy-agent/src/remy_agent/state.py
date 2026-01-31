import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    Represents the state of the Remy agent workflow.
    """

    # Chat history
    messages: Annotated[list[BaseMessage], operator.add]

    # Node 1: Recipe Search
    target_recipe_names: list[str]  # e.g. ["Shrimp Scampi"]
    recipe_options: list[dict[str, Any]]  # Options from Mealie and web with URLs
    # Structure: {"name": str, "source": "mealie"|"web", "url": str, "slug": str|None, "description": str}

    # Node 2: Recipe Selection (after user picks from options)
    selected_recipe_options: list[dict[str, Any]]  # User's selections from recipe_options
    fetched_recipes: list[dict[str, Any]]  # Recipe data from Mealie (after fetch/import)
    not_found_recipes: list[str]  # Recipes to search on web (deprecated, kept for compatibility)

    # Node 2: Pantry Filtering
    raw_ingredients: list[dict[str, Any]]  # All ingredients from fetched recipes
    pantry_items: list[dict[str, Any]]  # Items the user has (bypass)
    pending_cart: list[dict[str, Any]]  # Items proposed to buy

    # Node 3: Human-in-the-Loop
    # (The pending_cart is presented to user, they modify it -> approved_cart)
    approved_cart: list[dict[str, Any]]  # Final list to buy
    fulfillment_method: str  # "PICKUP" or "DELIVERY"
    preferred_store_id: str  # Kroger Location ID

    # Node 4: Fulfillment
    order_result: dict[str, Any]  # Output from Kroger add_to_cart
