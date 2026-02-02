from typing import Callable

from mealie import MealieFetcher

from .mealplan_tools import register_mealplan_tools
from .recipe_tools import register_recipe_tools


def register_all_tools(mcp, mealie: MealieFetcher, get_client: Callable[[str | None], MealieFetcher]):
    """Register all tools with the MCP server.

    Args:
        mcp: The FastMCP server instance
        mealie: The default MealieFetcher instance
        get_client: Function to get a MealieFetcher for a given API key (for multi-tenant support)
    """
    register_recipe_tools(mcp, mealie, get_client)
    register_mealplan_tools(mcp, mealie, get_client)


__all__ = [
    "register_all_tools",
    "register_recipe_tools",
    "register_mealplan_tools",
]
