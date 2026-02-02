import logging
import os
import traceback

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mealie import MealieFetcher
from prompts import register_prompts
from tools import register_all_tools

# Load environment variables first
load_dotenv()

# Get log level from environment variable with INFO as default
log_level_name = os.getenv("LOG_LEVEL", "INFO")
log_level = getattr(logging, log_level_name.upper(), logging.INFO)

# Configure logging
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("mealie_mcp_server.log")],
)
logger = logging.getLogger("mealie-mcp")

mcp = FastMCP("mealie")

MEALIE_BASE_URL = os.getenv("MEALIE_BASE_URL")
MEALIE_API_KEY = os.getenv("MEALIE_API_KEY")
if not MEALIE_BASE_URL or not MEALIE_API_KEY:
    raise ValueError("MEALIE_BASE_URL and MEALIE_API_KEY must be set in environment variables.")

# Cache for per-user MealieFetcher instances
_mealie_clients: dict[str, MealieFetcher] = {}


def get_mealie_client(api_key: str | None = None) -> MealieFetcher:
    """Get a MealieFetcher client, optionally using a custom API key.

    For multi-tenant support, allows each user to use their own Mealie API key.

    Args:
        api_key: Optional custom API key. If None, uses the default client.

    Returns:
        MealieFetcher client instance
    """
    global _mealie_clients

    # Use default client if no custom API key provided
    if not api_key or api_key == MEALIE_API_KEY:
        return mealie

    # Check cache for existing client with this API key
    if api_key in _mealie_clients:
        return _mealie_clients[api_key]

    # Create new client for this API key
    try:
        logger.info({"message": "Creating new MealieFetcher for custom API key"})
        client = MealieFetcher(
            base_url=MEALIE_BASE_URL,
            api_key=api_key,
        )
        _mealie_clients[api_key] = client
        return client
    except Exception as e:
        logger.error({"message": "Failed to initialize Mealie client with custom API key", "error": str(e)})
        logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
        raise


try:
    mealie = MealieFetcher(
        base_url=MEALIE_BASE_URL,
        api_key=MEALIE_API_KEY,
    )
except Exception as e:
    logger.error({"message": "Failed to initialize Mealie client", "error": str(e)})
    logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
    raise

register_prompts(mcp)
register_all_tools(mcp, mealie, get_mealie_client)

if __name__ == "__main__":
    try:
        logger.info({"message": "Starting Mealie MCP Server"})
        mcp.run(transport="stdio")
    except Exception as e:
        logger.critical({"message": "Fatal error in Mealie MCP Server", "error": str(e)})
        logger.debug({"message": "Error traceback", "traceback": traceback.format_exc()})
        raise
