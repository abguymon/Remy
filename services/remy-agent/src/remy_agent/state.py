import operator
from typing import Annotated, TypedDict, List, Dict, Any, Union
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """
    Represents the state of the Remy agent workflow.
    """
    # Chat history
    messages: Annotated[List[BaseMessage], operator.add]
    
    # Node 1: Recipe Extraction
    target_recipe_names: List[str]  # e.g. ["Shrimp Scampi"]
    fetched_recipes: List[Dict[str, Any]] # Recipe data from Mealie
    not_found_recipes: List[str]   # Recipes to search on web
    
    # Node 2: Pantry Filtering
    raw_ingredients: List[Dict[str, Any]] # All ingredients from fetched recipes
    pantry_items: List[Dict[str, Any]]    # Items the user has (bypass)
    pending_cart: List[Dict[str, Any]]    # Items proposed to buy
    
    # Node 3: Human-in-the-Loop
    # (The pending_cart is presented to user, they modify it -> approved_cart)
    approved_cart: List[Dict[str, Any]]   # Final list to buy
    fulfillment_method: str               # "PICKUP" or "DELIVERY"
    
    # Node 4: Fulfillment
    order_result: Dict[str, Any]          # Output from Kroger add_to_cart
