import logging
import traceback
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mealie import MealieFetcher
from models.recipe import Recipe, RecipeIngredient, RecipeInstruction

logger = logging.getLogger("mealie-mcp")


def register_recipe_tools(mcp: FastMCP, mealie: MealieFetcher, get_client: Callable[[str | None], MealieFetcher]) -> None:
    """Register all recipe-related tools with the MCP server.

    Args:
        mcp: The FastMCP server instance
        mealie: The default MealieFetcher instance
        get_client: Function to get a MealieFetcher for a given API key (for multi-tenant support)
    """

    @mcp.tool()
    def get_recipes(
        search: str | None = None,
        page: int | None = None,
        per_page: int | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        mealie_api_key: str | None = None,
    ) -> dict[str, Any]:
        """Provides a paginated list of recipes with optional filtering.

        Args:
            search: Filters recipes by name or description.
            page: Page number for pagination.
            per_page: Number of items per page.
            categories: Filter by specific recipe categories.
            tags: Filter by specific recipe tags.
            mealie_api_key: Optional custom Mealie API key for multi-tenant support.

        Returns:
            Dict[str, Any]: Recipe summaries with details like ID, name, description, and image information.
        """
        try:
            client = get_client(mealie_api_key)
            logger.info(
                {
                    "message": "Fetching recipes",
                    "search": search,
                    "page": page,
                    "per_page": per_page,
                    "categories": categories,
                    "tags": tags,
                    "custom_api_key": mealie_api_key is not None,
                }
            )
            return client.get_recipes(
                search=search,
                page=page,
                per_page=per_page,
                categories=categories,
                tags=tags,
            )
        except Exception as e:
            error_msg = f"Error fetching recipes: {str(e)}"
            logger.error({"message": error_msg})
            logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
            raise ToolError(error_msg) from e

    @mcp.tool()
    def get_recipe_detailed(slug: str, mealie_api_key: str | None = None) -> dict[str, Any]:
        """Retrieve a specific recipe by its slug identifier. Use this when to get full recipe
        details for tasks like updating or displaying the recipe.

        Args:
            slug: The unique text identifier for the recipe, typically found in recipe URLs
                or from get_recipes results.
            mealie_api_key: Optional custom Mealie API key for multi-tenant support.

        Returns:
            Dict[str, Any]: Comprehensive recipe details including ingredients, instructions,
                nutrition information, notes, and associated metadata.
        """
        try:
            client = get_client(mealie_api_key)
            logger.info({"message": "Fetching recipe", "slug": slug, "custom_api_key": mealie_api_key is not None})
            return client.get_recipe(slug)
        except Exception as e:
            error_msg = f"Error fetching recipe with slug '{slug}': {str(e)}"
            logger.error({"message": error_msg})
            logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
            raise ToolError(error_msg) from e

    @mcp.tool()
    def get_recipe_concise(slug: str, mealie_api_key: str | None = None) -> dict[str, Any]:
        """Retrieve a concise version of a specific recipe by its slug identifier. Use this when you only
        need a summary of the recipe, such as for when mealplaning.

        Args:
            slug: The unique text identifier for the recipe, typically found in recipe URLs
                or from get_recipes results.
            mealie_api_key: Optional custom Mealie API key for multi-tenant support.

        Returns:
            Dict[str, Any]: Concise recipe summary with essential fields.
        """
        try:
            client = get_client(mealie_api_key)
            logger.info({"message": "Fetching recipe", "slug": slug, "custom_api_key": mealie_api_key is not None})
            recipe_json = client.get_recipe(slug)
            recipe = Recipe.model_validate(recipe_json)
            return recipe.model_dump(
                include={
                    "name",
                    "slug",
                    "recipeServings",
                    "recipeYieldQuantity",
                    "recipeYield",
                    "totalTime",
                    "rating",
                    "recipeIngredient",
                    "lastMade",
                },
                exclude_none=True,
            )
        except Exception as e:
            error_msg = f"Error fetching recipe with slug '{slug}': {str(e)}"
            logger.error({"message": error_msg})
            logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
            raise ToolError(error_msg) from e

    @mcp.tool()
    def create_recipe(name: str, ingredients: list[str], instructions: list[str]) -> dict[str, Any]:
        """Create a new recipe

        Args:
            name: The name of the new recipe to be created.
            ingredients: A list of ingredients for the recipe include quantities and units.
            instructions: A list of instructions for preparing the recipe.

        Returns:
            Dict[str, Any]: The created recipe details.
        """
        try:
            logger.info({"message": "Creating recipe", "name": name})
            slug = mealie.create_recipe(name)
            recipe_json = mealie.get_recipe(slug)
            recipe = Recipe.model_validate(recipe_json)
            recipe.recipeIngredient = [RecipeIngredient(note=i) for i in ingredients]
            recipe.recipeInstructions = [RecipeInstruction(text=i) for i in instructions]
            return mealie.update_recipe(slug, recipe.model_dump(exclude_none=True))
        except Exception as e:
            error_msg = f"Error creating recipe '{name}': {str(e)}"
            logger.error({"message": error_msg})
            logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
            raise ToolError(error_msg) from e

    @mcp.tool()
    def create_recipe_from_url(url: str, include_tags: bool = False) -> dict[str, Any]:
        """Create a new recipe by importing from a URL. Mealie will scrape the recipe
        data from the provided URL and create a new recipe in the database.

        Args:
            url: The URL of the recipe page to scrape (e.g., "https://www.allrecipes.com/recipe/123")
            include_tags: Whether to include tags parsed from the recipe page (default: False)

        Returns:
            Dict[str, Any]: The slug of the newly created recipe.
        """
        try:
            logger.info({"message": "Creating recipe from URL", "url": url})
            slug = mealie.create_recipe_from_url(url, include_tags)
            return {"slug": slug, "success": True}
        except Exception as e:
            error_msg = f"Error creating recipe from URL '{url}': {str(e)}"
            logger.error({"message": error_msg})
            logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
            raise ToolError(error_msg) from e

    @mcp.tool()
    def update_recipe(
        slug: str,
        ingredients: list[str],
        instructions: list[str],
    ) -> dict[str, Any]:
        """Replaces the ingredients and instructions of an existing recipe.

        Args:
            slug: The unique text identifier for the recipe to be updated.
            ingredients: A list of ingredients for the recipe include quantities and units.
            instructions: A list of instructions for preparing the recipe.

        Returns:
            Dict[str, Any]: The updated recipe details.
        """
        try:
            logger.info({"message": "Updating recipe", "slug": slug})
            recipe_json = mealie.get_recipe(slug)
            recipe = Recipe.model_validate(recipe_json)
            recipe.recipeIngredient = [RecipeIngredient(note=i) for i in ingredients]
            recipe.recipeInstructions = [RecipeInstruction(text=i) for i in instructions]
            return mealie.update_recipe(slug, recipe.model_dump(exclude_none=True))
        except Exception as e:
            error_msg = f"Error updating recipe '{slug}': {str(e)}"
            logger.error({"message": error_msg})
            logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
            raise ToolError(error_msg) from e
