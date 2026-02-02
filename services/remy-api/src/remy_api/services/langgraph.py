"""LangGraph workflow service for recipe planning and grocery ordering"""

import json
import operator
import os
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from remy_api.config import get_settings
from remy_api.services.mcp_client import call_mealie_tool, parse_mcp_result


class WorkflowState(TypedDict):
    """State for the recipe planning workflow"""

    # User context
    user_id: str
    mealie_api_key: str | None
    pantry_items: list[str]

    # Chat history
    messages: Annotated[list[BaseMessage], operator.add]

    # Recipe search
    target_recipe_names: list[str]
    recipe_options: list[dict[str, Any]]

    # Recipe selection
    selected_recipe_options: list[dict[str, Any]]
    fetched_recipes: list[dict[str, Any]]

    # Ingredients
    raw_ingredients: list[dict[str, Any]]
    pending_cart: list[dict[str, Any]]

    # Cart approval
    approved_cart: list[dict[str, Any]]
    fulfillment_method: str
    preferred_store_id: str

    # Order result
    order_result: dict[str, Any]


# Lazy-initialized LLM
_llm = None


def get_llm():
    """Get or create the LLM instance"""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(model="gpt-4o", temperature=0)
    return _llm


async def search_recipes_node(state: WorkflowState) -> dict[str, Any]:
    """
    Extract recipe names from messages and search Mealie.
    Returns recipe_options for user selection.
    """
    messages = state["messages"]
    if not messages:
        return {"messages": [AIMessage(content="What would you like to cook?")]}

    last_message = messages[-1].content
    mealie_api_key = state.get("mealie_api_key")

    # Extract recipe names via LLM
    extraction_prompt = f"""
    Extract the recipe names the user wants to cook from the following text.
    Return ONLY a JSON list of strings, e.g. ["Shrimp Scampi", "Chicken Tikka"].
    If no recipe is specified, return [].

    Text: {last_message}
    """
    response = await get_llm().ainvoke([HumanMessage(content=extraction_prompt)])
    try:
        content = response.content.replace("```json", "").replace("```", "").strip()
        target_names = json.loads(content)
    except Exception:
        target_names = []

    if not target_names:
        return {"messages": [AIMessage(content="I couldn't find any recipe names. What would you like to make?")]}

    recipe_options = []
    settings = get_settings()

    for name in target_names:
        # Search Mealie
        result = await call_mealie_tool("get_recipes", {"search": name, "per_page": 10}, mealie_api_key)
        recipes = parse_mcp_result(result)

        if recipes:
            if isinstance(recipes, dict):
                recipes = recipes.get("items", [])

            for recipe in recipes[:5]:
                slug = recipe.get("slug", "")
                recipe_id = recipe.get("id", "")
                image_url = None
                if recipe.get("image") and recipe_id:
                    image_url = f"{settings.mealie_external_url}/api/media/recipes/{recipe_id}/images/min-original.webp"

                recipe_options.append(
                    {
                        "name": recipe.get("name", ""),
                        "source": "mealie",
                        "url": f"{settings.mealie_external_url}/g/home/r/{slug}",
                        "slug": slug,
                        "description": recipe.get("description", "") or "Recipe from your library",
                        "image_url": image_url,
                    }
                )

    if not recipe_options:
        return {
            "target_recipe_names": target_names,
            "recipe_options": [],
            "messages": [AIMessage(content=f"No recipes found for: {', '.join(target_names)}. Try different names.")],
        }

    return {
        "target_recipe_names": target_names,
        "recipe_options": recipe_options,
        "messages": [AIMessage(content=f"Found {len(recipe_options)} recipes. Please select which ones to use.")],
    }


async def fetch_selected_recipes_node(state: WorkflowState) -> dict[str, Any]:
    """Fetch detailed recipe data for selected recipes"""
    selected = state.get("selected_recipe_options", [])
    mealie_api_key = state.get("mealie_api_key")

    if not selected:
        return {"messages": [AIMessage(content="No recipes selected. Please select at least one.")]}

    fetched_recipes = []
    raw_ingredients = []

    for option in selected:
        if option.get("source") == "mealie" and option.get("slug"):
            result = await call_mealie_tool("get_recipe_detailed", {"slug": option["slug"]}, mealie_api_key)
            recipe_data = parse_mcp_result(result)

            if recipe_data:
                fetched_recipes.append(recipe_data)

                # Extract ingredients
                for ing in recipe_data.get("recipeIngredient", []):
                    if isinstance(ing, dict):
                        raw_ingredients.append(
                            {
                                "name": ing.get("food", {}).get("name", ing.get("note", "")),
                                "quantity": ing.get("quantity"),
                                "unit": ing.get("unit", {}).get("name", ""),
                                "note": ing.get("note", ""),
                            }
                        )
                    elif isinstance(ing, str):
                        raw_ingredients.append({"name": ing, "quantity": None, "unit": "", "note": ""})

    if not fetched_recipes:
        return {"messages": [AIMessage(content="Couldn't fetch recipe details. Please try again.")]}

    return {"fetched_recipes": fetched_recipes, "raw_ingredients": raw_ingredients}


async def filter_ingredients_node(state: WorkflowState) -> dict[str, Any]:
    """Filter out pantry items from ingredients"""
    raw_ingredients = state.get("raw_ingredients", [])
    pantry_items = state.get("pantry_items", [])

    # Normalize pantry items for comparison
    pantry_lower = [p.lower().strip() for p in pantry_items]

    pending_cart = []
    pantry_skipped = []

    for ing in raw_ingredients:
        ing_name = ing.get("name", "").lower().strip()

        # Check if ingredient is in pantry
        is_pantry = any(p in ing_name or ing_name in p for p in pantry_lower)

        if is_pantry:
            pantry_skipped.append(ing)
        else:
            pending_cart.append(ing)

    msg = f"Found {len(pending_cart)} items to add to cart"
    if pantry_skipped:
        msg += f" ({len(pantry_skipped)} pantry items skipped)"

    return {
        "pending_cart": pending_cart,
        "pantry_items": [{"name": ing.get("name", "")} for ing in pantry_skipped],
        "messages": [AIMessage(content=msg + ". Please review and approve the cart.")],
    }


async def execute_order_node(state: WorkflowState) -> dict[str, Any]:
    """Add approved items to Kroger cart"""
    approved_cart = state.get("approved_cart", [])

    if not approved_cart:
        return {"messages": [AIMessage(content="No items approved. Cart not updated.")]}

    # TODO: Call Kroger MCP to add items to cart
    # For now, return a placeholder result
    return {
        "order_result": {"status": "success", "items_added": len(approved_cart)},
        "messages": [AIMessage(content=f"Added {len(approved_cart)} items to your Kroger cart!")],
    }


def create_workflow() -> StateGraph:
    """Create the recipe planning workflow graph"""
    workflow = StateGraph(WorkflowState)

    # Add nodes
    workflow.add_node("search_recipes", search_recipes_node)
    workflow.add_node("fetch_selected_recipes", fetch_selected_recipes_node)
    workflow.add_node("filter_ingredients", filter_ingredients_node)
    workflow.add_node("execute_order", execute_order_node)

    # Define edges
    workflow.add_edge(START, "search_recipes")
    workflow.add_edge("search_recipes", "fetch_selected_recipes")
    workflow.add_edge("fetch_selected_recipes", "filter_ingredients")
    workflow.add_edge("filter_ingredients", "execute_order")
    workflow.add_edge("execute_order", END)

    return workflow


async def run_workflow(
    user_id: str,
    input_state: dict[str, Any] | None = None,
    command: str = "invoke",
    mealie_api_key: str | None = None,
    pantry_items: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run the workflow for a specific user.

    Args:
        user_id: User ID for checkpoint isolation
        input_state: Input state or state updates
        command: "invoke", "get_state", or "update_state"
        mealie_api_key: User's Mealie API key
        pantry_items: User's pantry items

    Returns:
        Workflow result state
    """
    # Ensure checkpoints directory exists
    os.makedirs("data/checkpoints", exist_ok=True)
    db_path = f"data/checkpoints/{user_id}.sqlite"

    workflow = create_workflow()

    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        app = workflow.compile(
            checkpointer=checkpointer, interrupt_before=["fetch_selected_recipes", "execute_order"]
        )

        config = {"configurable": {"thread_id": user_id}}

        if command == "get_state":
            state = await app.aget_state(config)
            return state.values if state else {}

        elif command == "update_state":
            await app.aupdate_state(config, input_state)
            return await app.aget_state(config)

        else:  # invoke
            # Initialize state with user context
            if input_state is None:
                input_state = {}

            input_state["user_id"] = user_id
            input_state["mealie_api_key"] = mealie_api_key
            input_state["pantry_items"] = pantry_items or []

            result = await app.ainvoke(input_state, config=config)
            return result
