import logging
from typing import Any

from utils import format_api_params

logger = logging.getLogger("mealie-mcp")


class MealplanMixin:
    """Mixin class for mealplan-related API endpoints"""

    def get_mealplans(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int | None = None,
        per_page: int | None = None,
    ) -> dict[str, Any]:
        """Get all mealplans for the current household with pagination.

        Args:
            start_date: Start date for filtering meal plans (ISO format YYYY-MM-DD)
            end_date: End date for filtering meal plans (ISO format YYYY-MM-DD)
            page: Page number to retrieve
            per_page: Number of items per page

        Returns:
            JSON response containing mealplan items and pagination information

        Raises:
            MealieApiError: If the API request fails
        """
        param_dict = {
            "startDate": start_date,
            "endDate": end_date,
            "page": page,
            "perPage": per_page,
        }

        params = format_api_params(param_dict)

        logger.info({"message": "Retrieving mealplans", "parameters": params})
        response = self._handle_request("GET", "/api/households/mealplans", params=params)
        return response

    def create_mealplan(
        self,
        date: str,
        recipe_id: str | None = None,
        title: str | None = None,
        entry_type: str = "breakfast",
    ) -> dict[str, Any]:
        """Create a new mealplan entry.

        Args:
            date: Date for the mealplan in ISO format (YYYY-MM-DD)
            recipe_id: UUID of the recipe to add to the mealplan (optional)
            title: Title for the mealplan entry if not using a recipe (optional)
            entry_type: Type of mealplan entry (breakfast, lunch, dinner, etc.)

        Returns:
            JSON response containing the created mealplan entry

        Raises:
            ValueError: If neither recipe_id nor title is provided
            MealieApiError: If the API request fails
        """
        if not recipe_id and not title:
            raise ValueError("Either recipe_id or title must be provided")
        if not date:
            raise ValueError("Date cannot be empty")

        # Build the request payload
        payload = {
            "date": date,
            "entryType": entry_type,
        }

        if recipe_id:
            payload["recipeId"] = recipe_id
        if title:
            payload["title"] = title

        logger.info(
            {
                "message": "Creating mealplan entry",
                "date": date,
                "entry_type": entry_type,
            }
        )
        return self._handle_request("POST", "/api/households/mealplans", json=payload)

    def get_todays_mealplan(self) -> list[dict[str, Any]]:
        """Get the mealplan entries for today.

        Returns:
            List of today's mealplan entries

        Raises:
            MealieApiError: If the API request fails
        """
        logger.info({"message": "Retrieving today's mealplan"})
        return self._handle_request("GET", "/api/households/mealplans/today")
