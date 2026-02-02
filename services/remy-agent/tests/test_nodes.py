"""
Unit tests for remy_agent.nodes module.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import remy_agent.nodes as nodes_module
from langchain_core.messages import HumanMessage
from remy_agent.nodes import (
    _extract_ingredients,
    _import_web_recipe,
    _search_mealie,
    _search_web,
    execute_order_node,
    fetch_selected_recipes_node,
    filter_ingredients_node,
    search_recipes_node,
)

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_llm(mocker):
    """Mock the LLM returned by get_llm()."""
    mock = MagicMock()
    mock.ainvoke = AsyncMock()
    mocker.patch.object(nodes_module, "get_llm", return_value=mock)
    return mock


@pytest.fixture
def mock_search_tool(mocker):
    """Mock the search tool returned by get_search_tool()."""
    mock = MagicMock()
    mocker.patch.object(nodes_module, "get_search_tool", return_value=mock)
    return mock


@pytest.fixture
def mock_mcp(mocker):
    """Mock call_mcp_tool."""
    mock = AsyncMock()
    mocker.patch.object(nodes_module, "call_mcp_tool", mock)
    return mock


@pytest.fixture
def mock_pantry(mocker):
    """Mock load_pantry_config."""
    mock = MagicMock(return_value={"bypass_staples": ["salt", "pepper", "olive oil"]})
    mocker.patch.object(nodes_module, "load_pantry_config", mock)
    return mock


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
# Tests for search_recipes_node
# -----------------------------------------------------------------------------


class TestSearchRecipesNode:
    """Tests for the search_recipes_node function."""

    @pytest.fixture
    def state_with_message(self):
        return {
            "messages": [HumanMessage(content="I want to make shrimp scampi tonight")],
            "target_recipe_names": [],
        }

    @pytest.mark.asyncio
    async def test_extracts_recipe_names_from_message(self, state_with_message, mock_llm, mock_mcp, mock_search_tool):
        """Test that recipe names are extracted from user message via LLM."""
        mock_llm.ainvoke.side_effect = [
            make_llm_response('["Shrimp Scampi"]'),
            make_llm_response("[]"),
        ]
        mock_mcp.return_value = make_mcp_result(
            {"items": [{"name": "Shrimp Scampi", "slug": "shrimp-scampi", "description": "Classic dish"}]}
        )
        mock_search_tool.run.return_value = "Some search results"

        result = await search_recipes_node(state_with_message)

        assert "target_recipe_names" in result
        assert "Shrimp Scampi" in result["target_recipe_names"]

    @pytest.mark.asyncio
    async def test_returns_message_when_no_recipe_found(self, mock_llm):
        """Test that appropriate message is returned when no recipe names found."""
        state = {"messages": [HumanMessage(content="Hello, how are you?")], "target_recipe_names": []}
        mock_llm.ainvoke.return_value = make_llm_response("[]")

        result = await search_recipes_node(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert "couldn't find any recipe names" in result["messages"][0].content.lower()

    @pytest.mark.asyncio
    async def test_searches_mealie_and_web_in_parallel(self, state_with_message, mock_llm, mock_mcp, mock_search_tool):
        """Test that both Mealie and web are searched."""
        mock_llm.ainvoke.side_effect = [
            make_llm_response('["Shrimp Scampi"]'),
            make_llm_response(
                '[{"name": "Web Shrimp Scampi", "url": "https://example.com", "description": "Web recipe"}]'
            ),
        ]
        mock_mcp.return_value = make_mcp_result(
            {"items": [{"name": "Mealie Shrimp Scampi", "slug": "shrimp-scampi", "description": "Mealie recipe"}]}
        )
        mock_search_tool.run.return_value = "Web search results"

        result = await search_recipes_node(state_with_message)

        assert "recipe_options" in result
        sources = [opt["source"] for opt in result["recipe_options"]]
        assert "mealie" in sources
        assert "web" in sources

    @pytest.mark.asyncio
    async def test_uses_existing_target_names_if_set(self, mock_llm, mock_mcp, mock_search_tool):
        """Test that existing target_recipe_names are used if already set."""
        state = {
            "messages": [HumanMessage(content="Anything")],
            "target_recipe_names": ["Chicken Tikka"],
        }
        mock_mcp.return_value = make_mcp_result({"items": []})
        mock_search_tool.run.return_value = ""
        mock_llm.ainvoke.return_value = make_llm_response("[]")

        result = await search_recipes_node(state)

        assert result["target_recipe_names"] == ["Chicken Tikka"]

    @pytest.mark.asyncio
    async def test_handles_empty_search_results(self, state_with_message, mock_llm, mock_mcp, mock_search_tool):
        """Test handling when no recipes are found from any source."""
        mock_llm.ainvoke.side_effect = [
            make_llm_response('["Exotic Dish"]'),
            make_llm_response("[]"),
        ]
        mock_mcp.return_value = make_mcp_result({"items": []})
        mock_search_tool.run.return_value = ""

        result = await search_recipes_node(state_with_message)

        assert "recipe_options" in result
        assert result["recipe_options"] == []
        assert "couldn't find any recipes" in result["messages"][0].content.lower()


# -----------------------------------------------------------------------------
# Tests for _search_mealie helper
# -----------------------------------------------------------------------------


class TestSearchMealie:
    """Tests for the _search_mealie helper function."""

    @pytest.mark.asyncio
    async def test_returns_formatted_results(self, mock_mcp):
        """Test that Mealie results are properly formatted."""
        mock_mcp.return_value = make_mcp_result(
            {
                "items": [
                    {"name": "Shrimp Scampi", "slug": "shrimp-scampi", "description": "Classic dish"},
                    {"name": "Pasta Primavera", "slug": "pasta-primavera", "description": "Veggie pasta"},
                ]
            }
        )

        results = await _search_mealie("shrimp")

        assert len(results) == 2
        assert results[0]["name"] == "Shrimp Scampi"
        assert results[0]["source"] == "mealie"
        assert results[0]["slug"] == "shrimp-scampi"
        assert "recipe/shrimp-scampi" in results[0]["url"]

    @pytest.mark.asyncio
    async def test_handles_list_response_format(self, mock_mcp):
        """Test handling of list response format (legacy)."""
        mock_mcp.return_value = make_mcp_result([{"name": "Recipe 1", "slug": "recipe-1", "description": "Desc 1"}])

        results = await _search_mealie("recipe")

        assert len(results) == 1
        assert results[0]["name"] == "Recipe 1"

    @pytest.mark.asyncio
    async def test_limits_to_5_results(self, mock_mcp):
        """Test that results are limited to 5."""
        mock_mcp.return_value = make_mcp_result(
            {"items": [{"name": f"Recipe {i}", "slug": f"recipe-{i}", "description": ""} for i in range(10)]}
        )

        results = await _search_mealie("recipe")

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, mock_mcp):
        """Test that empty list is returned on error."""
        mock_mcp.return_value = None

        results = await _search_mealie("recipe")

        assert results == []

    @pytest.mark.asyncio
    async def test_handles_missing_description(self, mock_mcp):
        """Test handling of recipes without description."""
        mock_mcp.return_value = make_mcp_result({"items": [{"name": "Recipe", "slug": "recipe", "description": None}]})

        results = await _search_mealie("recipe")

        assert results[0]["description"] == "Recipe from your Mealie library"


# -----------------------------------------------------------------------------
# Tests for _search_web helper
# -----------------------------------------------------------------------------


class TestSearchWeb:
    """Tests for the _search_web helper function."""

    @pytest.mark.asyncio
    async def test_returns_formatted_results(self, mock_llm, mock_search_tool):
        """Test that web results are properly formatted."""
        mock_search_tool.run.return_value = "Some search results"
        mock_llm.ainvoke.return_value = make_llm_response(
            json.dumps([{"name": "Web Recipe", "url": "https://example.com/recipe", "description": "A great recipe"}])
        )

        results = await _search_web("shrimp scampi")

        assert len(results) == 1
        assert results[0]["name"] == "Web Recipe"
        assert results[0]["source"] == "web"
        assert results[0]["url"] == "https://example.com/recipe"
        assert results[0]["slug"] is None

    @pytest.mark.asyncio
    async def test_limits_to_5_results(self, mock_llm, mock_search_tool):
        """Test that results are limited to 5."""
        mock_search_tool.run.return_value = "Search results"
        mock_llm.ainvoke.return_value = make_llm_response(
            json.dumps(
                [{"name": f"Recipe {i}", "url": f"https://example.com/{i}", "description": ""} for i in range(10)]
            )
        )

        results = await _search_web("recipe")

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_filters_out_results_without_url(self, mock_llm, mock_search_tool):
        """Test that results without URL are filtered out."""
        mock_search_tool.run.return_value = "Search results"
        mock_llm.ainvoke.return_value = make_llm_response(
            json.dumps(
                [
                    {"name": "Has URL", "url": "https://example.com", "description": ""},
                    {"name": "No URL", "url": "", "description": ""},
                    {"name": "Null URL", "url": None, "description": ""},
                ]
            )
        )

        results = await _search_web("recipe")

        assert len(results) == 1
        assert results[0]["name"] == "Has URL"

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, mock_search_tool):
        """Test that empty list is returned on error."""
        mock_search_tool.run.side_effect = Exception("Search failed")

        results = await _search_web("recipe")

        assert results == []


# -----------------------------------------------------------------------------
# Tests for fetch_selected_recipes_node
# -----------------------------------------------------------------------------


class TestFetchSelectedRecipesNode:
    """Tests for the fetch_selected_recipes_node function."""

    @pytest.fixture
    def sample_mealie_recipe(self):
        return {
            "name": "Shrimp Scampi",
            "slug": "shrimp-scampi",
            "recipeIngredient": [
                {"note": "1 lb shrimp", "food": {"name": "shrimp"}},
                {"note": "4 tbsp butter", "food": {"name": "butter"}},
            ],
        }

    @pytest.fixture
    def state_with_mealie_selection(self):
        return {
            "selected_recipe_options": [
                {
                    "name": "Shrimp Scampi",
                    "source": "mealie",
                    "url": "http://localhost/recipe/shrimp-scampi",
                    "slug": "shrimp-scampi",
                    "description": "Classic dish",
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_fetches_mealie_recipes(self, state_with_mealie_selection, sample_mealie_recipe, mock_mcp):
        """Test fetching selected Mealie recipes."""
        mock_mcp.return_value = make_mcp_result(sample_mealie_recipe)

        result = await fetch_selected_recipes_node(state_with_mealie_selection)

        assert "fetched_recipes" in result
        assert len(result["fetched_recipes"]) == 1
        assert result["fetched_recipes"][0]["name"] == "Shrimp Scampi"

    @pytest.mark.asyncio
    async def test_extracts_ingredients_from_fetched_recipes(
        self, state_with_mealie_selection, sample_mealie_recipe, mock_mcp
    ):
        """Test that ingredients are extracted from fetched recipes."""
        mock_mcp.return_value = make_mcp_result(sample_mealie_recipe)

        result = await fetch_selected_recipes_node(state_with_mealie_selection)

        assert "raw_ingredients" in result
        assert len(result["raw_ingredients"]) == 2
        assert "original" in result["raw_ingredients"][0]
        assert "recipe" in result["raw_ingredients"][0]

    @pytest.mark.asyncio
    async def test_imports_web_recipes(self, sample_mealie_recipe, mock_mcp):
        """Test importing web recipes via Mealie URL scraper."""
        state = {
            "selected_recipe_options": [
                {
                    "name": "Web Recipe",
                    "source": "web",
                    "url": "https://example.com/recipe",
                    "slug": None,
                    "description": "A web recipe",
                }
            ],
        }
        mock_mcp.side_effect = [
            make_mcp_result({"slug": "web-recipe", "success": True}),
            make_mcp_result(sample_mealie_recipe),
        ]

        result = await fetch_selected_recipes_node(state)

        assert "fetched_recipes" in result
        assert any("imported" in msg.content.lower() for msg in result.get("messages", []))

    @pytest.mark.asyncio
    async def test_returns_error_when_no_recipes_selected(self):
        """Test error message when no recipes are selected."""
        state = {"selected_recipe_options": []}

        result = await fetch_selected_recipes_node(state)

        assert "messages" in result
        assert "no recipes were selected" in result["messages"][0].content.lower()

    @pytest.mark.asyncio
    async def test_handles_failed_fetch(self, state_with_mealie_selection, mock_mcp):
        """Test handling when recipe fetch fails."""
        mock_mcp.return_value = None

        result = await fetch_selected_recipes_node(state_with_mealie_selection)

        assert "messages" in result
        assert "couldn't fetch" in result["messages"][0].content.lower()


# -----------------------------------------------------------------------------
# Tests for _extract_ingredients helper
# -----------------------------------------------------------------------------


class TestExtractIngredients:
    """Tests for the _extract_ingredients helper function."""

    def test_extracts_ingredients_with_note(self):
        """Test extracting ingredients that have 'note' field."""
        recipe = {
            "name": "Test Recipe",
            "recipeIngredient": [
                {"note": "1 lb shrimp", "food": {"name": "shrimp"}},
                {"note": "2 tbsp butter", "food": {"name": "butter"}},
            ],
        }

        result = _extract_ingredients(recipe)

        assert len(result) == 2
        assert result[0]["original"] == "1 lb shrimp"
        assert result[0]["recipe"] == "Test Recipe"

    def test_falls_back_to_food_name(self):
        """Test fallback to food.name when note is empty."""
        recipe = {
            "name": "Test Recipe",
            "recipeIngredient": [
                {"note": "", "food": {"name": "chicken"}},
                {"note": None, "food": {"name": "rice"}},
            ],
        }

        result = _extract_ingredients(recipe)

        assert result[0]["original"] == "chicken"
        assert result[1]["original"] == "rice"

    def test_handles_missing_recipe_ingredient(self):
        """Test handling recipe without recipeIngredient field."""
        recipe = {"name": "Empty Recipe"}

        result = _extract_ingredients(recipe)

        assert result == []

    def test_handles_empty_ingredient_list(self):
        """Test handling empty ingredient list."""
        recipe = {"name": "Empty Recipe", "recipeIngredient": []}

        result = _extract_ingredients(recipe)

        assert result == []


# -----------------------------------------------------------------------------
# Tests for filter_ingredients_node
# -----------------------------------------------------------------------------


class TestFilterIngredientsNode:
    """Tests for the filter_ingredients_node function."""

    @pytest.mark.asyncio
    async def test_filters_pantry_items(self, mock_pantry):
        """Test that pantry staples are filtered out."""
        state = {
            "raw_ingredients": [
                {"original": "1 lb shrimp", "recipe": "Test"},
                {"original": "1/4 tsp salt", "recipe": "Test"},
                {"original": "black pepper to taste", "recipe": "Test"},
                {"original": "2 tbsp olive oil", "recipe": "Test"},
            ]
        }

        result = await filter_ingredients_node(state)

        # salt, pepper, olive oil should be in pantry_items
        assert len(result["pantry_items"]) == 3
        # only shrimp should be in pending_cart
        assert len(result["pending_cart"]) == 1
        assert "shrimp" in result["pending_cart"][0]["original"]

    @pytest.mark.asyncio
    async def test_handles_empty_ingredients(self, mock_pantry):
        """Test handling empty ingredients list."""
        state = {"raw_ingredients": []}

        result = await filter_ingredients_node(state)

        assert result["pantry_items"] == []
        assert result["pending_cart"] == []

    @pytest.mark.asyncio
    async def test_generates_summary_message(self, mock_pantry):
        """Test that summary message is generated for pending items."""
        state = {
            "raw_ingredients": [
                {"original": "1 lb shrimp", "recipe": "Test"},
                {"original": "2 cups rice", "recipe": "Test"},
            ]
        }

        result = await filter_ingredients_node(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert "prepared a list" in result["messages"][0].content.lower()

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self, mocker):
        """Test that pantry matching is case-insensitive."""
        mocker.patch.object(nodes_module, "load_pantry_config", return_value={"bypass_staples": ["salt"]})
        state = {
            "raw_ingredients": [
                {"original": "SALT", "recipe": "Test"},
                {"original": "Salt", "recipe": "Test"},
                {"original": "Kosher Salt", "recipe": "Test"},
            ]
        }

        result = await filter_ingredients_node(state)

        assert len(result["pantry_items"]) == 3
        assert len(result["pending_cart"]) == 0


# -----------------------------------------------------------------------------
# Tests for execute_order_node
# -----------------------------------------------------------------------------


class TestExecuteOrderNode:
    """Tests for the execute_order_node function."""

    @pytest.fixture
    def kroger_product(self):
        return {"success": True, "data": [{"upc": "0001234567890", "description": "Fresh Large Shrimp"}]}

    @pytest.mark.asyncio
    async def test_adds_items_to_cart(self, kroger_product, mock_llm, mock_mcp):
        """Test adding approved items to Kroger cart."""
        state = {
            "approved_cart": [{"original": "1 lb shrimp", "recipe": "Test"}],
            "fulfillment_method": "PICKUP",
            "preferred_store_id": "12345",
        }
        mock_llm.ainvoke.return_value = make_llm_response("shrimp")
        mock_mcp.side_effect = [
            make_mcp_result(kroger_product),
            make_mcp_result({"success": True}),
        ]

        result = await execute_order_node(state)

        assert "order_result" in result
        assert "items" in result["order_result"]
        assert result["order_result"]["items"][0]["status"] == "added"

    @pytest.mark.asyncio
    async def test_handles_product_not_found(self, mock_llm, mock_mcp):
        """Test handling when product is not found."""
        state = {
            "approved_cart": [{"original": "exotic ingredient", "recipe": "Test"}],
            "fulfillment_method": "PICKUP",
        }
        mock_llm.ainvoke.return_value = make_llm_response("exotic ingredient")
        mock_mcp.return_value = make_mcp_result({"success": True, "data": []})

        result = await execute_order_node(state)

        assert result["order_result"]["items"][0]["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_handles_add_to_cart_failure(self, kroger_product, mock_llm, mock_mcp):
        """Test handling when add to cart fails."""
        state = {
            "approved_cart": [{"original": "1 lb shrimp", "recipe": "Test"}],
            "fulfillment_method": "PICKUP",
        }
        mock_llm.ainvoke.return_value = make_llm_response("shrimp")
        mock_mcp.side_effect = [
            make_mcp_result(kroger_product),
            make_mcp_result({"success": False, "error": "Auth required"}),
        ]

        result = await execute_order_node(state)

        assert result["order_result"]["items"][0]["status"] == "failed"
        assert "error" in result["order_result"]["items"][0]

    @pytest.mark.asyncio
    async def test_handles_empty_approved_cart(self):
        """Test handling empty approved cart."""
        state = {"approved_cart": [], "fulfillment_method": "PICKUP"}

        result = await execute_order_node(state)

        assert result["order_result"]["items"] == []

    @pytest.mark.asyncio
    async def test_uses_fulfillment_method(self, kroger_product, mock_llm, mock_mcp):
        """Test that fulfillment method is passed to add_to_cart."""
        state = {
            "approved_cart": [{"original": "shrimp", "recipe": "Test"}],
            "fulfillment_method": "DELIVERY",
        }
        mock_llm.ainvoke.return_value = make_llm_response("shrimp")
        mock_mcp.side_effect = [
            make_mcp_result(kroger_product),
            make_mcp_result({"success": True}),
        ]

        await execute_order_node(state)

        # Verify add_to_cart was called with DELIVERY modality
        add_call = mock_mcp.call_args_list[1]
        assert add_call[0][2]["modality"] == "DELIVERY"


# -----------------------------------------------------------------------------
# Tests for _import_web_recipe helper
# -----------------------------------------------------------------------------


class TestImportWebRecipe:
    """Tests for the _import_web_recipe helper function."""

    @pytest.fixture
    def sample_recipe(self):
        return {
            "name": "Imported Recipe",
            "slug": "imported-recipe",
            "recipeIngredient": [{"note": "1 cup flour", "food": {"name": "flour"}}],
        }

    @pytest.mark.asyncio
    async def test_imports_via_mealie_url_scraper(self, sample_recipe, mock_mcp):
        """Test importing recipe via Mealie's URL scraper."""
        option = {
            "name": "Web Recipe",
            "source": "web",
            "url": "https://example.com/recipe",
            "slug": None,
        }
        mock_mcp.side_effect = [
            make_mcp_result({"slug": "web-recipe", "success": True}),
            make_mcp_result(sample_recipe),
        ]

        result = await _import_web_recipe(option)

        assert result is not None
        assert result["name"] == "Imported Recipe"
        # Verify create_recipe_from_url was called
        create_call = mock_mcp.call_args_list[0]
        assert create_call[0][1] == "create_recipe_from_url"
        assert create_call[0][2]["url"] == "https://example.com/recipe"

    @pytest.mark.asyncio
    async def test_returns_none_on_import_failure(self, mock_mcp):
        """Test that None is returned when import fails."""
        option = {
            "name": "Web Recipe",
            "source": "web",
            "url": "https://example.com/bad-recipe",
            "slug": None,
        }
        mock_mcp.return_value = None

        result = await _import_web_recipe(option)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self, mock_mcp):
        """Test that exceptions are handled gracefully."""
        option = {
            "name": "Web Recipe",
            "source": "web",
            "url": "https://example.com/recipe",
            "slug": None,
        }
        mock_mcp.side_effect = Exception("Network error")

        result = await _import_web_recipe(option)

        assert result is None
