"""
Separate module for registering authentication tools to avoid circular imports
"""

from .auth import register_auth_tools


def register_tools(mcp):
    """Register authentication tools with the FastMCP server"""
    register_auth_tools(mcp)
