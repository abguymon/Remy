"""
Live integration tests against deployed services.

These tests require the actual MCP servers to be running:
- mealie-mcp-server on localhost:8000
- kroger-mcp on localhost:8001

Run with: pytest tests/test_live.py -v -s
"""

import json
import os
import tempfile

import pytest
from langchain_core.messages import HumanMessage

# Skip all tests if services aren't available
pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_LIVE_TESTS", "false").lower() == "true", reason="Live tests disabled via SKIP_LIVE_TESTS env var"
)

# Use localhost URLs for testing outside Docker
MEALIE_MCP_URL = os.getenv("MEALIE_MCP_URL", "http://localhost:8000/sse")
KROGER_MCP_URL = os.getenv("KROGER_MCP_URL", "http://localhost:8001/sse")


class TestMealieMCPConnection:
    """Test connectivity to Mealie MCP server."""

    @pytest.mark.asyncio
    async def test_can_connect_to_mealie_mcp(self):
        """Test that we can connect to Mealie MCP and call a tool."""
        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(MEALIE_MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # List available tools
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]

                assert "get_recipes" in tool_names
                assert "get_recipe_detailed" in tool_names
                assert "create_recipe_from_url" in tool_names

    @pytest.mark.asyncio
    async def test_can_search_recipes(self):
        """Test searching for recipes in Mealie."""
        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(MEALIE_MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool("get_recipes", {"per_page": 5})

                assert not result.isError
                assert result.content
                data = json.loads(result.content[0].text)
                # Should return items list (may be empty if no recipes)
                assert "items" in data or isinstance(data, list)


class TestKrogerMCPConnection:
    """Test connectivity to Kroger MCP server."""

    @pytest.mark.asyncio
    async def test_can_connect_to_kroger_mcp(self):
        """Test that we can connect to Kroger MCP and call a tool."""
        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(KROGER_MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # List available tools
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]

                assert "search_products" in tool_names
                assert "search_locations" in tool_names
                assert "add_items_to_cart" in tool_names

    @pytest.mark.asyncio
    async def test_can_search_locations(self):
        """Test searching for Kroger store locations."""
        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(KROGER_MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool("search_locations", {"zip_code": "45202"})

                assert not result.isError
                assert result.content
                data = json.loads(result.content[0].text)
                # Should return data list of locations
                assert "data" in data


class TestLiveWorkflow:
    """Test the actual workflow against live services."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for checkpointing."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            yield f.name
        if os.path.exists(f.name):
            os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_search_recipes_node_live(self, temp_db_path, mocker):
        """Test search_recipes_node against live Mealie."""
        from unittest.mock import AsyncMock, MagicMock

        # Only mock the LLM, let MCP calls go through
        import remy_agent.nodes as nodes_module
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from remy_agent.graph import get_workflow

        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(
            side_effect=[
                MagicMock(content='["Pasta"]'),  # Recipe extraction
                MagicMock(content="[]"),  # Web search (empty to avoid external calls)
            ]
        )
        mocker.patch.object(nodes_module, "get_llm", return_value=llm_mock)

        # Mock search tool to avoid external web calls
        search_mock = MagicMock()
        search_mock.run.return_value = ""
        mocker.patch.object(nodes_module, "get_search_tool", return_value=search_mock)

        workflow = get_workflow()

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as checkpointer:
            app = workflow.compile(
                checkpointer=checkpointer, interrupt_before=["fetch_selected_recipes", "execute_order"]
            )

            config = {"configurable": {"thread_id": "live-test-1"}}
            result = await app.ainvoke({"messages": [HumanMessage(content="I want to make pasta")]}, config=config)

            # Should have searched Mealie (may or may not find results)
            assert "recipe_options" in result
            assert "target_recipe_names" in result
            assert result["target_recipe_names"] == ["Pasta"]

            # Print what was found for debugging
            print(f"\nFound {len(result['recipe_options'])} recipe options from Mealie")
            for opt in result["recipe_options"]:
                print(f"  - {opt['name']} ({opt['source']}): {opt['url']}")

    @pytest.mark.asyncio
    async def test_full_search_with_known_recipe(self, temp_db_path, mocker):
        """Test searching for a recipe that likely exists in Mealie."""
        from unittest.mock import AsyncMock, MagicMock

        import remy_agent.nodes as nodes_module
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from mcp.client.session import ClientSession

        # First, let's see what recipes exist in Mealie
        from mcp.client.sse import sse_client
        from remy_agent.graph import get_workflow

        async with sse_client(MEALIE_MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("get_recipes", {"per_page": 10})
                data = json.loads(result.content[0].text)

                recipes = data.get("items", data) if isinstance(data, dict) else data
                if not recipes:
                    pytest.skip("No recipes in Mealie to test with")

                # Use the first recipe's name
                test_recipe_name = recipes[0]["name"]
                print(f"\nTesting with existing recipe: {test_recipe_name}")

        # Now test the workflow with this recipe
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(
            side_effect=[
                MagicMock(content=f'["{test_recipe_name}"]'),
                MagicMock(content="[]"),
            ]
        )
        mocker.patch.object(nodes_module, "get_llm", return_value=llm_mock)

        search_mock = MagicMock()
        search_mock.run.return_value = ""
        mocker.patch.object(nodes_module, "get_search_tool", return_value=search_mock)

        workflow = get_workflow()

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as checkpointer:
            app = workflow.compile(
                checkpointer=checkpointer, interrupt_before=["fetch_selected_recipes", "execute_order"]
            )

            config = {"configurable": {"thread_id": "live-test-2"}}
            result = await app.ainvoke(
                {"messages": [HumanMessage(content=f"I want to make {test_recipe_name}")]}, config=config
            )

            # Should find the recipe in Mealie
            assert "recipe_options" in result
            mealie_options = [r for r in result["recipe_options"] if r["source"] == "mealie"]
            assert len(mealie_options) > 0, f"Should find '{test_recipe_name}' in Mealie"

            print(f"\nFound {len(mealie_options)} Mealie results for '{test_recipe_name}'")

    @pytest.mark.asyncio
    async def test_fetch_recipe_details(self, temp_db_path, mocker):
        """Test fetching full recipe details from Mealie."""
        from unittest.mock import AsyncMock, MagicMock

        import remy_agent.nodes as nodes_module
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from mcp.client.session import ClientSession

        # First get a recipe from Mealie
        from mcp.client.sse import sse_client
        from remy_agent.graph import get_workflow

        async with sse_client(MEALIE_MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("get_recipes", {"per_page": 1})
                data = json.loads(result.content[0].text)

                recipes = data.get("items", data) if isinstance(data, dict) else data
                if not recipes:
                    pytest.skip("No recipes in Mealie to test with")

                test_recipe = recipes[0]
                print(f"\nTesting with recipe: {test_recipe['name']} (slug: {test_recipe['slug']})")

        # Mock LLM for recipe extraction
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(
            side_effect=[
                MagicMock(content=f'["{test_recipe["name"]}"]'),
                MagicMock(content="[]"),
            ]
        )
        mocker.patch.object(nodes_module, "get_llm", return_value=llm_mock)

        search_mock = MagicMock()
        search_mock.run.return_value = ""
        mocker.patch.object(nodes_module, "get_search_tool", return_value=search_mock)

        workflow = get_workflow()

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as checkpointer:
            app = workflow.compile(
                checkpointer=checkpointer, interrupt_before=["fetch_selected_recipes", "execute_order"]
            )

            config = {"configurable": {"thread_id": "live-test-3"}}

            # Phase 1: Search
            result = await app.ainvoke(
                {"messages": [HumanMessage(content=f"Make {test_recipe['name']}")]}, config=config
            )

            mealie_options = [r for r in result["recipe_options"] if r["source"] == "mealie"]
            if not mealie_options:
                pytest.skip("Recipe not found in search results")

            # Phase 2: Select the recipe and fetch details
            await app.aupdate_state(config, {"selected_recipe_options": [mealie_options[0]]})

            result = await app.ainvoke(None, config=config)

            # Should have fetched recipe and extracted ingredients
            assert "fetched_recipes" in result
            assert len(result["fetched_recipes"]) > 0
            assert "raw_ingredients" in result

            print(f"\nFetched recipe: {result['fetched_recipes'][0]['name']}")
            print(f"Found {len(result['raw_ingredients'])} ingredients")
            print(f"Pending cart: {len(result.get('pending_cart', []))} items")
            print(f"Pantry items: {len(result.get('pantry_items', []))} items")


class TestCreateRecipeFromUrl:
    """Test the new create_recipe_from_url functionality."""

    @pytest.mark.asyncio
    async def test_create_recipe_from_url_tool_exists(self):
        """Verify the create_recipe_from_url tool is available."""
        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(MEALIE_MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]

                assert "create_recipe_from_url" in tool_names

                # Find the tool and check its schema
                tool = next(t for t in tools.tools if t.name == "create_recipe_from_url")
                print(f"\nTool description: {tool.description}")
                print(f"Input schema: {tool.inputSchema}")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Creates a recipe in Mealie - run manually if needed")
    async def test_import_recipe_from_url(self):
        """Test importing a recipe from a URL (creates data in Mealie)."""
        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        test_url = "https://www.allrecipes.com/recipe/23891/grilled-cheese-sandwich/"

        async with sse_client(MEALIE_MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool("create_recipe_from_url", {"url": test_url, "include_tags": True})

                print(f"\nResult: {result}")
                if result.isError:
                    print(f"Error: {result.content[0].text}")
                else:
                    data = json.loads(result.content[0].text)
                    print(f"Created recipe with slug: {data.get('slug')}")
