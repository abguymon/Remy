"""MCP Client service for calling Kroger and Mealie MCP servers"""

import asyncio
import json
import logging
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from remy_api.config import get_settings

logger = logging.getLogger(__name__)

MCP_TIMEOUT = 30  # seconds
MCP_MAX_RETRIES = 2


async def call_mcp_tool(
    url: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> Any:
    """Call an MCP tool via SSE transport with timeout and retry."""
    last_error: Exception | None = None

    for attempt in range(MCP_MAX_RETRIES + 1):
        try:
            async with sse_client(url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await asyncio.wait_for(
                        session.call_tool(tool_name, arguments),
                        timeout=MCP_TIMEOUT,
                    )
                    return result
        except asyncio.TimeoutError:
            logger.warning("MCP timeout: %s/%s (attempt %d/%d)", url, tool_name, attempt + 1, MCP_MAX_RETRIES + 1)
            last_error = TimeoutError(f"Timeout calling {tool_name}")
        except (ConnectionError, OSError) as e:
            logger.warning("MCP connection error: %s/%s (attempt %d/%d): %s", url, tool_name, attempt + 1, MCP_MAX_RETRIES + 1, e)
            last_error = e
            if attempt < MCP_MAX_RETRIES:
                await asyncio.sleep(0.5 * (attempt + 1))
        except Exception as e:
            logger.error("MCP call failed: %s/%s: %s", url, tool_name, e)
            return None

    logger.error("MCP call failed after %d attempts: %s/%s: %s", MCP_MAX_RETRIES + 1, url, tool_name, last_error)
    return None


async def call_kroger_tool(tool_name: str, arguments: dict[str, Any] | None = None, user_id: str | None = None) -> Any:
    """Call a Kroger MCP tool."""
    settings = get_settings()
    if arguments is None:
        arguments = {}
    if user_id:
        arguments["user_id"] = user_id
    return await call_mcp_tool(settings.kroger_mcp_url, tool_name, arguments)


async def call_mealie_tool(
    tool_name: str, arguments: dict[str, Any] | None = None, mealie_api_key: str | None = None
) -> Any:
    """Call a Mealie MCP tool."""
    settings = get_settings()
    if arguments is None:
        arguments = {}
    if mealie_api_key:
        arguments["mealie_api_key"] = mealie_api_key
    return await call_mcp_tool(settings.mealie_mcp_url, tool_name, arguments)


def parse_mcp_result(result: Any) -> dict | list | None:
    """Parse MCP tool result to extract JSON content."""
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
