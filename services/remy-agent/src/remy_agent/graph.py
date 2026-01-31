import os

from langgraph.graph import END, START, StateGraph

from .nodes import execute_order_node, fetch_selected_recipes_node, filter_ingredients_node, search_recipes_node
from .state import AgentState

# Ensure data directory exists
os.makedirs("data", exist_ok=True)
DB_PATH = "data/checkpoints.sqlite"


def get_workflow():
    """
    Constructs the LangGraph workflow (uncompiled).

    Flow:
    START → search_recipes → [interrupt for user selection] → fetch_selected_recipes → filter_ingredients → [interrupt for approval] → execute_order → END
    """
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("search_recipes", search_recipes_node)
    workflow.add_node("fetch_selected_recipes", fetch_selected_recipes_node)
    workflow.add_node("filter_ingredients", filter_ingredients_node)
    workflow.add_node("execute_order", execute_order_node)

    # Define Edges - Linear flow with interrupts handled by compile()
    workflow.add_edge(START, "search_recipes")
    workflow.add_edge("search_recipes", "fetch_selected_recipes")
    workflow.add_edge("fetch_selected_recipes", "filter_ingredients")
    workflow.add_edge("filter_ingredients", "execute_order")
    workflow.add_edge("execute_order", END)

    return workflow
