"""
Unit tests for remy_agent.graph module.
"""

from langgraph.graph import StateGraph
from remy_agent.graph import get_workflow
from remy_agent.state import AgentState


class TestGetWorkflow:
    """Tests for the get_workflow function."""

    def test_returns_state_graph(self):
        """Test that get_workflow returns a StateGraph."""
        workflow = get_workflow()
        assert isinstance(workflow, StateGraph)

    def test_contains_required_nodes(self):
        """Test that all required nodes are present."""
        workflow = get_workflow()
        nodes = workflow.nodes

        required_nodes = [
            "search_recipes",
            "fetch_selected_recipes",
            "filter_ingredients",
            "execute_order",
        ]

        for node_name in required_nodes:
            assert node_name in nodes, f"Missing node: {node_name}"

    def test_node_count(self):
        """Test the expected number of nodes."""
        workflow = get_workflow()
        assert len(workflow.nodes) == 4

    def test_workflow_compiles(self):
        """Test that the workflow compiles without errors."""
        workflow = get_workflow()
        app = workflow.compile()
        assert app is not None

    def test_workflow_compiles_with_interrupt_before(self):
        """Test that workflow compiles with interrupt_before configuration."""
        workflow = get_workflow()
        app = workflow.compile(interrupt_before=["fetch_selected_recipes", "execute_order"])
        assert app is not None


class TestWorkflowEdges:
    """Tests for workflow edge configuration."""

    def test_start_connects_to_search_recipes(self):
        """Test that START connects to search_recipes node."""
        workflow = get_workflow()
        app = workflow.compile()
        graph_dict = app.get_graph().to_json()

        edges = graph_dict.get("edges", [])
        start_edges = [e for e in edges if e.get("source") == "__start__"]
        assert len(start_edges) == 1
        assert start_edges[0]["target"] == "search_recipes"

    def test_linear_flow_structure(self):
        """Test the linear flow: search -> fetch -> filter -> execute -> end."""
        workflow = get_workflow()
        app = workflow.compile()
        graph_dict = app.get_graph().to_json()
        edges = graph_dict.get("edges", [])

        edge_map = {e["source"]: e["target"] for e in edges}

        assert edge_map.get("__start__") == "search_recipes"
        assert edge_map.get("search_recipes") == "fetch_selected_recipes"
        assert edge_map.get("fetch_selected_recipes") == "filter_ingredients"
        assert edge_map.get("filter_ingredients") == "execute_order"
        assert edge_map.get("execute_order") == "__end__"


class TestWorkflowState:
    """Tests for workflow state handling."""

    def test_workflow_uses_agent_state(self):
        """Test that workflow is configured with AgentState."""
        workflow = get_workflow()
        # StateGraph stores the state schema as a key in schemas dict
        assert AgentState in workflow.schemas

    def test_state_has_required_fields(self):
        """Test that AgentState has all required fields."""
        from typing import get_type_hints

        hints = get_type_hints(AgentState)

        required_fields = [
            "messages",
            "target_recipe_names",
            "recipe_options",
            "selected_recipe_options",
            "fetched_recipes",
            "raw_ingredients",
            "pantry_items",
            "pending_cart",
            "approved_cart",
            "fulfillment_method",
            "preferred_store_id",
            "order_result",
        ]

        for field in required_fields:
            assert field in hints, f"Missing state field: {field}"
