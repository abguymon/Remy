"""
Integration tests for the remy-agent workflow.

These tests verify the end-to-end flow of the agent with mocked external services.
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
import remy_agent.nodes as nodes_module
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from remy_agent.graph import get_workflow

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for checkpointing."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        yield f.name
    if os.path.exists(f.name):
        os.unlink(f.name)


@pytest.fixture
def mock_external_services(mocker):
    """Mock all external services (LLM, MCP, search tool, pantry)."""
    llm_mock = MagicMock()
    llm_mock.ainvoke = AsyncMock()
    mocker.patch.object(nodes_module, "get_llm", return_value=llm_mock)

    search_mock = MagicMock()
    mocker.patch.object(nodes_module, "get_search_tool", return_value=search_mock)

    mcp_mock = AsyncMock()
    mocker.patch.object(nodes_module, "call_mcp_tool", mcp_mock)

    pantry_mock = MagicMock(return_value={"bypass_staples": ["salt", "pepper"]})
    mocker.patch.object(nodes_module, "load_pantry_config", pantry_mock)

    return {
        "llm": llm_mock,
        "search": search_mock,
        "mcp": mcp_mock,
        "pantry": pantry_mock,
    }


def make_mcp_result(data, is_error=False):
    """Helper to create mock MCP results."""
    result = MagicMock()
    result.isError = is_error
    result.content = [MagicMock(text=json.dumps(data))]
    return result


def make_llm_response(content):
    """Helper to create mock LLM responses."""
    response = MagicMock()
    response.content = content
    return response


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------


class TestWorkflowSearchPhase:
    """Test the search phase of the workflow."""

    @pytest.mark.asyncio
    async def test_search_finds_recipes_and_interrupts(self, temp_db_path, mock_external_services):
        """Test that search phase finds recipes and interrupts for selection."""
        mocks = mock_external_services

        # Setup mocks
        mocks["llm"].ainvoke.side_effect = [
            make_llm_response('["Chicken Parmesan"]'),
            make_llm_response("[]"),  # No web results
        ]
        mocks["mcp"].return_value = make_mcp_result(
            {"items": [{"name": "Chicken Parmesan", "slug": "chicken-parmesan", "description": "Classic dish"}]}
        )
        mocks["search"].run.return_value = ""

        workflow = get_workflow()

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as checkpointer:
            app = workflow.compile(
                checkpointer=checkpointer, interrupt_before=["fetch_selected_recipes", "execute_order"]
            )

            config = {"configurable": {"thread_id": "test-search-1"}}
            result = await app.ainvoke(
                {"messages": [HumanMessage(content="I want to make chicken parmesan")]}, config=config
            )

            # Should have recipe options
            assert "recipe_options" in result
            assert len(result["recipe_options"]) >= 1
            assert result["recipe_options"][0]["source"] == "mealie"

            # Should be interrupted before fetch_selected_recipes
            state = await app.aget_state(config)
            assert state.next == ("fetch_selected_recipes",)


class TestWorkflowFetchPhase:
    """Test the fetch phase of the workflow."""

    @pytest.mark.asyncio
    async def test_fetch_and_filter_flow(self, temp_db_path, mock_external_services, sample_mealie_recipe):
        """Test fetching selected recipes and filtering ingredients."""
        mocks = mock_external_services

        # Setup search phase mocks
        mocks["llm"].ainvoke.side_effect = [
            make_llm_response('["Shrimp Scampi"]'),
            make_llm_response("[]"),
        ]
        mocks["mcp"].return_value = make_mcp_result(
            {"items": [{"name": "Shrimp Scampi", "slug": "shrimp-scampi", "description": ""}]}
        )
        mocks["search"].run.return_value = ""

        workflow = get_workflow()

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as checkpointer:
            app = workflow.compile(
                checkpointer=checkpointer, interrupt_before=["fetch_selected_recipes", "execute_order"]
            )

            config = {"configurable": {"thread_id": "test-fetch-1"}}

            # Phase 1: Search
            await app.ainvoke({"messages": [HumanMessage(content="Make shrimp scampi")]}, config=config)

            # Phase 2: Select recipe and continue
            mocks["mcp"].return_value = make_mcp_result(sample_mealie_recipe)

            await app.aupdate_state(
                config,
                {
                    "selected_recipe_options": [
                        {
                            "name": "Shrimp Scampi",
                            "source": "mealie",
                            "url": "http://localhost/recipe/shrimp-scampi",
                            "slug": "shrimp-scampi",
                            "description": "",
                        }
                    ]
                },
            )

            result = await app.ainvoke(None, config=config)

            # Should have pending cart items (minus pantry staples)
            assert "pending_cart" in result
            assert len(result["pending_cart"]) > 0

            # Salt and pepper should be filtered to pantry
            pantry_names = [item["original"].lower() for item in result.get("pantry_items", [])]
            assert any("salt" in name for name in pantry_names)


class TestWorkflowOrderPhase:
    """Test the order phase of the workflow."""

    @pytest.mark.asyncio
    async def test_full_order_flow(self, temp_db_path, mock_external_services, sample_mealie_recipe):
        """Test the complete flow from search to order."""
        mocks = mock_external_services

        workflow = get_workflow()

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as checkpointer:
            app = workflow.compile(
                checkpointer=checkpointer, interrupt_before=["fetch_selected_recipes", "execute_order"]
            )

            config = {"configurable": {"thread_id": "test-order-1"}}

            # Phase 1: Search
            mocks["llm"].ainvoke.side_effect = [
                make_llm_response('["Shrimp Scampi"]'),
                make_llm_response("[]"),
            ]
            mocks["mcp"].return_value = make_mcp_result(
                {"items": [{"name": "Shrimp Scampi", "slug": "shrimp-scampi", "description": ""}]}
            )

            await app.ainvoke({"messages": [HumanMessage(content="Make shrimp scampi")]}, config=config)

            # Phase 2: Select recipe
            mocks["mcp"].return_value = make_mcp_result(sample_mealie_recipe)
            await app.aupdate_state(
                config,
                {
                    "selected_recipe_options": [
                        {
                            "name": "Shrimp Scampi",
                            "source": "mealie",
                            "slug": "shrimp-scampi",
                            "url": "",
                            "description": "",
                        }
                    ]
                },
            )

            result = await app.ainvoke(None, config=config)
            pending_cart = result.get("pending_cart", [])

            # Phase 3: Approve and order
            mocks["llm"].ainvoke.return_value = make_llm_response("shrimp")

            def mcp_order_handler(url, tool_name, args):
                if tool_name == "search_products":
                    return make_mcp_result({"success": True, "data": [{"upc": "123", "description": "Fresh Shrimp"}]})
                elif tool_name == "add_items_to_cart":
                    return make_mcp_result({"success": True})
                return make_mcp_result({})

            mocks["mcp"].side_effect = mcp_order_handler

            await app.aupdate_state(
                config,
                {
                    "approved_cart": pending_cart,
                    "fulfillment_method": "PICKUP",
                    "preferred_store_id": "12345",
                },
            )

            final_result = await app.ainvoke(None, config=config)

            # Should have order result
            assert "order_result" in final_result
            assert "items" in final_result["order_result"]


class TestWorkflowErrorHandling:
    """Test error handling in the workflow."""

    @pytest.mark.asyncio
    async def test_handles_no_recipes_found(self, temp_db_path, mock_external_services):
        """Test handling when no recipes are found."""
        mocks = mock_external_services

        mocks["llm"].ainvoke.side_effect = [
            make_llm_response('["Nonexistent Recipe"]'),
            make_llm_response("[]"),
        ]
        mocks["mcp"].return_value = make_mcp_result({"items": []})
        mocks["search"].run.return_value = ""

        workflow = get_workflow()

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as checkpointer:
            app = workflow.compile(
                checkpointer=checkpointer, interrupt_before=["fetch_selected_recipes", "execute_order"]
            )

            config = {"configurable": {"thread_id": "test-error-1"}}
            result = await app.ainvoke({"messages": [HumanMessage(content="Make nonexistent recipe")]}, config=config)

            assert result.get("recipe_options") == []
            messages = result.get("messages", [])
            ai_messages = [m for m in messages if isinstance(m, AIMessage)]
            assert any("couldn't find" in m.content.lower() for m in ai_messages)


class TestWorkflowStatePersistence:
    """Test state persistence across workflow invocations."""

    @pytest.mark.asyncio
    async def test_state_persists_between_invocations(self, temp_db_path, mock_external_services):
        """Test that state is properly persisted and resumed."""
        mocks = mock_external_services

        mocks["llm"].ainvoke.side_effect = [
            make_llm_response('["Pasta"]'),
            make_llm_response("[]"),
        ]
        mocks["mcp"].return_value = make_mcp_result(
            {"items": [{"name": "Pasta Carbonara", "slug": "pasta-carbonara", "description": ""}]}
        )
        mocks["search"].run.return_value = ""

        thread_id = "test-persist-1"
        config = {"configurable": {"thread_id": thread_id}}
        workflow = get_workflow()

        # First invocation
        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as checkpointer:
            app = workflow.compile(
                checkpointer=checkpointer, interrupt_before=["fetch_selected_recipes", "execute_order"]
            )
            await app.ainvoke({"messages": [HumanMessage(content="Make pasta")]}, config=config)

        # Second invocation - state should persist
        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as checkpointer:
            app = workflow.compile(
                checkpointer=checkpointer, interrupt_before=["fetch_selected_recipes", "execute_order"]
            )
            state = await app.aget_state(config)

            assert state.values.get("recipe_options") is not None
            assert len(state.values.get("recipe_options", [])) > 0

    @pytest.mark.asyncio
    async def test_separate_threads_have_separate_state(self, temp_db_path, mock_external_services):
        """Test that different thread IDs have independent state."""
        mocks = mock_external_services
        mocks["search"].run.return_value = ""

        workflow = get_workflow()

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as checkpointer:
            app = workflow.compile(
                checkpointer=checkpointer, interrupt_before=["fetch_selected_recipes", "execute_order"]
            )

            # Thread 1: Search for pizza
            mocks["llm"].ainvoke.side_effect = [
                make_llm_response('["Pizza"]'),
                make_llm_response("[]"),
            ]
            mocks["mcp"].return_value = make_mcp_result(
                {"items": [{"name": "Pizza", "slug": "pizza", "description": ""}]}
            )

            config1 = {"configurable": {"thread_id": "thread-1"}}
            await app.ainvoke({"messages": [HumanMessage(content="Make pizza")]}, config=config1)

            # Thread 2: Search for soup
            mocks["llm"].ainvoke.side_effect = [
                make_llm_response('["Soup"]'),
                make_llm_response("[]"),
            ]
            mocks["mcp"].return_value = make_mcp_result(
                {"items": [{"name": "Soup", "slug": "soup", "description": ""}]}
            )

            config2 = {"configurable": {"thread_id": "thread-2"}}
            await app.ainvoke({"messages": [HumanMessage(content="Make soup")]}, config=config2)

            # Verify states are independent
            state1 = await app.aget_state(config1)
            state2 = await app.aget_state(config2)

            assert state1.values["target_recipe_names"] == ["Pizza"]
            assert state2.values["target_recipe_names"] == ["Soup"]
