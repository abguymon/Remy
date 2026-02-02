"""MCP Client service for calling Kroger and Mealie MCP servers"""

import json
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from remy_api.config import get_settings


async def call_mcp_tool(url: str, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    """
    Call an MCP tool via SSE transport.

    Args:
        url: MCP server SSE endpoint URL
        tool_name: Name of the tool to call
        arguments: Optional arguments for the tool

    Returns:
        The tool result, or None if an error occurred
    """
    try:
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return result
    except Exception as e:
        print(f"Error calling {tool_name} at {url}: {e}")
        return None


async def call_kroger_tool(tool_name: str, arguments: dict[str, Any] | None = None, user_id: str | None = None) -> Any:
    """
    Call a Kroger MCP tool.

    Args:
        tool_name: Name of the Kroger tool
        arguments: Tool arguments
        user_id: User ID for multi-tenant isolation

    Returns:
        Tool result or None
    """
    settings = get_settings()

    # Add user_id to arguments for multi-tenant support
    if arguments is None:
        arguments = {}
    if user_id:
        arguments["user_id"] = user_id

    return await call_mcp_tool(settings.kroger_mcp_url, tool_name, arguments)


async def call_mealie_tool(
    tool_name: str, arguments: dict[str, Any] | None = None, mealie_api_key: str | None = None
) -> Any:
    """
    Call a Mealie MCP tool.

    Args:
        tool_name: Name of the Mealie tool
        arguments: Tool arguments
        mealie_api_key: User's Mealie API key for multi-tenant support

    Returns:
        Tool result or None
    """
    settings = get_settings()

    # Add API key to arguments for multi-tenant support
    if arguments is None:
        arguments = {}
    if mealie_api_key:
        arguments["mealie_api_key"] = mealie_api_key

    return await call_mcp_tool(settings.mealie_mcp_url, tool_name, arguments)


def parse_mcp_result(result: Any) -> dict | list | None:
    """
    Parse MCP tool result to extract JSON content.

    Args:
        result: Raw MCP tool result

    Returns:
        Parsed JSON data or None
    """
    if result is None:
        return None

    if hasattr(result, "isError") and result.isError:
        return None

    if hasattr(result, "content") and result.content:
        try:
            return json.loads(result.content[0].text)
        except (json.JSONDecodeError, IndexError, AttributeError):
            pass

    return None
