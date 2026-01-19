import os
from langgraph.graph import StateGraph, START, END
from .state import AgentState
from .nodes import fetch_recipes_node, web_search_node, filter_ingredients_node, execute_order_node

# Ensure data directory exists
os.makedirs("data", exist_ok=True)
DB_PATH = "data/checkpoints.sqlite"

def should_search_web(state: AgentState):
    """
    Decision function to check if we need to search the web.
    """
    if state.get("not_found_recipes"):
        return "web_search"
    return "filter_ingredients"

def get_workflow():
    """
    Constructs the LangGraph workflow (uncompiled).
    """
    # Define Graph
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("fetch_recipes", fetch_recipes_node)
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("filter_ingredients", filter_ingredients_node)
    workflow.add_node("execute_order", execute_order_node)

    # Define Edges
    workflow.add_edge(START, "fetch_recipes")
    
    # Conditional edge from fetch_recipes
    workflow.add_conditional_edges(
        "fetch_recipes",
        should_search_web,
        {
            "web_search": "web_search",
            "filter_ingredients": "filter_ingredients"
        }
    )
    
    workflow.add_edge("web_search", "filter_ingredients")
    workflow.add_edge("filter_ingredients", "execute_order")
    workflow.add_edge("execute_order", END)
    
    return workflow
