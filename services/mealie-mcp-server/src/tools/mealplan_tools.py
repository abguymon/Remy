import logging
import traceback
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mealie import MealieFetcher
from models.mealplan import MealPlanEntry

logger = logging.getLogger("mealie-mcp")


def register_mealplan_tools(mcp: FastMCP, mealie: MealieFetcher, get_client: Callable[[str | None], MealieFetcher]) -> None:
    """Register all mealplan-related tools with the MCP server.

    Args:
        mcp: The FastMCP server instance
        mealie: The default MealieFetcher instance
        get_client: Function to get a MealieFetcher for a given API key (for multi-tenant support)
    """

    @mcp.tool()
    def get_all_mealplans(
        start_date: str | None = None,
        end_date: str | None = None,
        page: int | None = None,
        per_page: int | None = None,
        mealie_api_key: str | None = None,
    ) -> dict[str, Any]:
        """Get all meal plans for the current household with pagination.

        Args:
            start_date: Start date for filtering meal plans (ISO format YYYY-MM-DD)
            end_date: End date for filtering meal plans (ISO format YYYY-MM-DD)
            page: Page number to retrieve
            per_page: Number of items per page
            mealie_api_key: Optional custom Mealie API key for multi-tenant support.

        Returns:
            Dict[str, Any]: JSON response containing mealplan items and pagination information
        """
        try:
            client = get_client(mealie_api_key)
            logger.info(
                {
                    "message": "Fetching mealplans",
                    "start_date": start_date,
                    "end_date": end_date,
                    "page": page,
                    "per_page": per_page,
                    "custom_api_key": mealie_api_key is not None,
                }
            )
            return client.get_mealplans(
                start_date=start_date,
                end_date=end_date,
                page=page,
                per_page=per_page,
            )
        except Exception as e:
            error_msg = f"Error fetching mealplans: {str(e)}"
            logger.error({"message": error_msg})
            logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
            raise ToolError(error_msg) from e

    @mcp.tool()
    def create_mealplan(
        date: str,
        recipe_id: str | None = None,
        title: str | None = None,
        entry_type: str = "breakfast",
        mealie_api_key: str | None = None,
    ) -> dict[str, Any]:
        """Create a new meal plan entry.

        Args:
            date: Date for the mealplan in ISO format (YYYY-MM-DD)
            recipe_id: UUID of the recipe to add to the mealplan (optional)
            title: Title for the mealplan entry if not using a recipe (optional)
            entry_type: Type of mealplan entry (breakfast, lunch, dinner, side)
            mealie_api_key: Optional custom Mealie API key for multi-tenant support.

        Returns:
            Dict[str, Any]: JSON response containing the created mealplan entry
        """
        try:
            client = get_client(mealie_api_key)
            logger.info(
                {
                    "message": "Creating mealplan entry",
                    "date": date,
                    "recipe_id": recipe_id,
                    "title": title,
                    "entry_type": entry_type,
                    "custom_api_key": mealie_api_key is not None,
                }
            )
            return client.create_mealplan(
                date=date,
                recipe_id=recipe_id,
                title=title,
                entry_type=entry_type,
            )
        except Exception as e:
            error_msg = f"Error creating mealplan entry: {str(e)}"
            logger.error({"message": error_msg})
            logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
            raise ToolError(error_msg) from e

    @mcp.tool()
    def create_mealplan_bulk(
        entries: list[dict[str, Any]],
        mealie_api_key: str | None = None,
    ) -> dict[str, Any]:
        """Create multiple meal plan entries in bulk.

        Args:
            entries: List of mealplan entries, each containing:
                - date (str): Date in ISO format (YYYY-MM-DD)
                - recipe_id (str, optional): UUID of the recipe
                - title (str, optional): Title for the entry
                - entry_type (str, optional): Type of entry (breakfast, lunch, dinner, side)
            mealie_api_key: Optional custom Mealie API key for multi-tenant support.

        Returns:
            Dict[str, Any]: JSON response with success message
        """
        try:
            client = get_client(mealie_api_key)
            logger.info(
                {
                    "message": "Creating bulk mealplan entries",
                    "entries_count": len(entries),
                    "custom_api_key": mealie_api_key is not None,
                }
            )
            for entry in entries:
                entry_obj = MealPlanEntry.model_validate(entry)
                client.create_mealplan(**entry_obj.model_dump())
            return {"message": f"Successfully created {len(entries)} mealplan entries"}
        except Exception as e:
            error_msg = f"Error creating bulk mealplan entries: {str(e)}"
            logger.error({"message": error_msg})
            logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
            raise ToolError(error_msg) from e

    @mcp.tool()
    def get_todays_mealplan(mealie_api_key: str | None = None) -> list[dict[str, Any]]:
        """Get the mealplan entries for today.

        Args:
            mealie_api_key: Optional custom Mealie API key for multi-tenant support.

        Returns:
            List[Dict[str, Any]]: List of today's mealplan entries
        """
        try:
            client = get_client(mealie_api_key)
            logger.info({"message": "Fetching today's mealplan", "custom_api_key": mealie_api_key is not None})
            return client.get_todays_mealplan()
        except Exception as e:
            error_msg = f"Error fetching today's mealplan: {str(e)}"
            logger.error({"message": error_msg})
            logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
            raise ToolError(error_msg) from e
