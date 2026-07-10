"""Kroger integration — internal module (no MCP service), PRD §7.2.

Public surface for the planner / router / MCP facade:

* Domain functions: :func:`search_products`, :func:`get_locations`,
  :func:`add_items_to_cart`.
* OAuth/token helpers: :func:`store_tokens`, :func:`get_client`,
  :func:`close_client`, :func:`generate_pkce`, :func:`generate_state`.
* Models: :class:`Product`, :class:`StoreLocation`, :class:`CartItemOutcome`, …
* Typed errors: :class:`KrogerError` and subclasses (never ``None`` on failure).

**Add-only cart:** the Kroger Public API exposes only ``PUT /cart/add`` — the
real cart cannot be read, cleared, or checked out via the API (FR-18).
"""

from .banners import DEFAULT_CART_URL, banner_cart_url
from .client import KrogerClient, generate_pkce, generate_state
from .errors import (
    KrogerAPIError,
    KrogerAuthError,
    KrogerError,
    KrogerNotConnectedError,
    KrogerRateLimitError,
)
from .fastapi_errors import register_kroger_error_handler
from .models import (
    CartItemOutcome,
    CartItemRequest,
    KrogerTokenBundle,
    Modality,
    OutcomeStatus,
    Price,
    Product,
    StockLevel,
    StoreLocation,
)
from .service import (
    add_items_to_cart,
    close_client,
    get_client,
    get_location,
    get_locations,
    search_products,
    store_tokens,
)

__all__ = [
    "DEFAULT_CART_URL",
    "CartItemOutcome",
    "CartItemRequest",
    "KrogerAPIError",
    "KrogerAuthError",
    "KrogerClient",
    "KrogerError",
    "KrogerNotConnectedError",
    "KrogerRateLimitError",
    "KrogerTokenBundle",
    "Modality",
    "OutcomeStatus",
    "Price",
    "Product",
    "StockLevel",
    "StoreLocation",
    "add_items_to_cart",
    "banner_cart_url",
    "close_client",
    "generate_pkce",
    "generate_state",
    "get_client",
    "get_location",
    "get_locations",
    "register_kroger_error_handler",
    "search_products",
    "store_tokens",
]
