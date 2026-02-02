"""
Shared utilities and client management for Kroger MCP server

Multi-tenant support: All user-specific data is stored in per-user directories
under data/users/{user_id}/. The user_id parameter should be passed to all
tools that need user-specific state.
"""

import json
import os

from kroger_api.kroger_api import KrogerAPI
from kroger_api.token_storage import load_token
from kroger_api.utils.env import get_zip_code, load_and_validate_env

# Load environment variables
# load_dotenv()

# Global state for clients - now keyed by user_id for multi-tenant support
_authenticated_clients: dict[str, KrogerAPI] = {}
_client_credentials_client: KrogerAPI | None = None

# Base data directory
DATA_DIR = "data"

# Default user ID for backwards compatibility (single-user mode)
DEFAULT_USER_ID = "default"


def get_user_data_dir(user_id: str | None = None) -> str:
    """Get the data directory for a specific user.

    Args:
        user_id: The user's unique identifier. If None, uses DEFAULT_USER_ID.

    Returns:
        Path to the user's data directory (e.g., data/users/{user_id}/)
    """
    if not user_id:
        user_id = DEFAULT_USER_ID
    return os.path.join(DATA_DIR, "users", user_id)


def _ensure_data_dir(user_id: str | None = None):
    """Ensure the data directory exists for a user.

    Args:
        user_id: The user's unique identifier. If None, ensures base data dir.
    """
    if user_id:
        os.makedirs(get_user_data_dir(user_id), exist_ok=True)
    else:
        os.makedirs(DATA_DIR, exist_ok=True)


def _save_token(token_file: str, token_info: dict, user_id: str | None = None) -> None:
    """Save token to file"""
    _ensure_data_dir(user_id)
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    with open(token_file, "w") as f:
        json.dump(token_info, f, indent=2)


def get_user_token_file(user_id: str | None = None) -> str:
    """Get the path to a user's token file.

    Args:
        user_id: The user's unique identifier.

    Returns:
        Path to the user's token file
    """
    return os.path.join(get_user_data_dir(user_id), ".kroger_token_user.json")


def get_user_preferences_file(user_id: str | None = None) -> str:
    """Get the path to a user's preferences file.

    Args:
        user_id: The user's unique identifier.

    Returns:
        Path to the user's preferences file
    """
    return os.path.join(get_user_data_dir(user_id), "kroger_preferences.json")


def get_client_credentials_client() -> KrogerAPI:
    """Get or create a client credentials authenticated client for public data.

    This is a shared client used for public API operations (locations, products).
    It does not contain user-specific data.
    """
    global _client_credentials_client

    if _client_credentials_client is not None and _client_credentials_client.test_current_token():
        return _client_credentials_client

    _client_credentials_client = None
    _ensure_data_dir()

    try:
        load_and_validate_env(["KROGER_CLIENT_ID", "KROGER_CLIENT_SECRET"])
        _client_credentials_client = KrogerAPI()

        # Try to load existing token first (use data/ directory for persistence)
        token_file = f"{DATA_DIR}/.kroger_token_client_product.compact.json"
        token_info = load_token(token_file)

        if token_info:
            # Test if the token is still valid
            _client_credentials_client.client.token_info = token_info
            if _client_credentials_client.test_current_token():
                # Token is valid, use it
                return _client_credentials_client

        # Token is invalid or not found, get a new one
        token_info = _client_credentials_client.authorization.get_token_with_client_credentials("product.compact")
        return _client_credentials_client
    except Exception as e:
        raise Exception(f"Failed to get client credentials: {str(e)}") from e


def get_authenticated_client(user_id: str | None = None) -> KrogerAPI:
    """Get or create a user-authenticated client for cart operations.

    This function attempts to load an existing token or prompts for authentication.
    In an MCP context, the user needs to explicitly call start_authentication and
    complete_authentication tools to authenticate.

    Args:
        user_id: The user's unique identifier for multi-tenant support.
                 If None, uses DEFAULT_USER_ID for backwards compatibility.

    Returns:
        KrogerAPI: Authenticated client

    Raises:
        Exception: If no valid token is available and authentication is required
    """
    global _authenticated_clients

    if not user_id:
        user_id = DEFAULT_USER_ID

    # Check if we have a cached client for this user that's still valid
    if user_id in _authenticated_clients and _authenticated_clients[user_id].test_current_token():
        return _authenticated_clients[user_id]

    # Clear the reference if token is invalid
    if user_id in _authenticated_clients:
        del _authenticated_clients[user_id]

    _ensure_data_dir(user_id)

    try:
        load_and_validate_env(["KROGER_CLIENT_ID", "KROGER_CLIENT_SECRET", "KROGER_REDIRECT_URI"])

        # Try to load existing user token first (per-user token file)
        token_file = get_user_token_file(user_id)
        print(f"[user:{user_id}] Looking for token file at: {token_file}", flush=True)
        token_info = load_token(token_file)
        print(
            f"[user:{user_id}] Loaded token info: {token_info is not None}, has refresh: {'refresh_token' in token_info if token_info else 'N/A'}",
            flush=True,
        )

        if token_info:
            # Create a new client with the loaded token
            client = KrogerAPI()
            client.client.token_info = token_info
            client.client.token_file = token_file

            if client.test_current_token():
                # Token is valid, cache and return it
                _authenticated_clients[user_id] = client
                return client

            # Token is invalid, try to refresh it
            if "refresh_token" in token_info:
                try:
                    print(f"[user:{user_id}] Attempting to refresh token...")
                    new_token_info = client.authorization.refresh_token(token_info["refresh_token"])
                    # Save the refreshed token to file
                    if new_token_info:
                        _save_token(token_file, new_token_info, user_id)
                        print(f"[user:{user_id}] Token refreshed and saved to {token_file}")
                    # If refresh was successful, cache and return the client
                    if client.test_current_token():
                        _authenticated_clients[user_id] = client
                        return client
                except Exception as e:
                    # Refresh failed, need to re-authenticate
                    print(f"[user:{user_id}] Token refresh failed: {e}")

        # No valid token available, need user-initiated authentication
        raise Exception(
            "Authentication required. Please use the start_authentication tool to begin the OAuth flow, "
            "then complete it with the complete_authentication tool."
        )
    except Exception as e:
        if "Authentication required" in str(e):
            # This is an expected error when authentication is needed
            raise
        else:
            # Other unexpected errors
            raise Exception(f"Authentication failed: {str(e)}") from e


def invalidate_authenticated_client(user_id: str | None = None):
    """Invalidate the authenticated client to force re-authentication.

    Args:
        user_id: The user's unique identifier. If None, invalidates for DEFAULT_USER_ID.
    """
    global _authenticated_clients
    if not user_id:
        user_id = DEFAULT_USER_ID
    if user_id in _authenticated_clients:
        del _authenticated_clients[user_id]


def invalidate_client_credentials_client():
    """Invalidate the client credentials client to force re-authentication"""
    global _client_credentials_client
    _client_credentials_client = None


def _load_preferences(user_id: str | None = None) -> dict:
    """Load preferences from file for a specific user.

    Args:
        user_id: The user's unique identifier.
    """
    preferences_file = get_user_preferences_file(user_id)
    try:
        if os.path.exists(preferences_file):
            with open(preferences_file) as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load preferences for user {user_id}: {e}")
    return {"preferred_location_id": None}


def _save_preferences(preferences: dict, user_id: str | None = None) -> None:
    """Save preferences to file for a specific user.

    Args:
        preferences: The preferences dictionary to save.
        user_id: The user's unique identifier.
    """
    _ensure_data_dir(user_id)
    preferences_file = get_user_preferences_file(user_id)
    try:
        with open(preferences_file, "w") as f:
            json.dump(preferences, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save preferences for user {user_id}: {e}")


def get_preferred_location_id(user_id: str | None = None) -> str | None:
    """Get the current preferred location ID from preferences file.

    Args:
        user_id: The user's unique identifier.
    """
    preferences = _load_preferences(user_id)
    return preferences.get("preferred_location_id")


def set_preferred_location_id(location_id: str, user_id: str | None = None) -> None:
    """Set the preferred location ID in preferences file.

    Args:
        location_id: The location ID to set as preferred.
        user_id: The user's unique identifier.
    """
    preferences = _load_preferences(user_id)
    preferences["preferred_location_id"] = location_id
    _save_preferences(preferences, user_id)


def format_currency(value: float | None) -> str:
    """Format a value as currency"""
    if value is None:
        return "N/A"
    return f"${value:.2f}"


def get_default_zip_code() -> str:
    """Get the default zip code from environment or fallback"""
    return get_zip_code(default="10001")
