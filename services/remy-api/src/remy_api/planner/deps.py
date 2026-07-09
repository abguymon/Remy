"""External collaborators for the planner, in one place.

Every step reaches its LLM client, search provider, recipe store/scraper, image
downloader, and Kroger functions through attributes on *this* module. That gives
tests a single, stable set of patch points (``monkeypatch.setattr(deps, ...)``)
instead of chasing the same callable across five step modules, and keeps the
production wiring to the real implementations trivial.
"""

from __future__ import annotations

from remy_api.kroger import add_items_to_cart as kroger_add_items_to_cart
from remy_api.kroger import search_products as kroger_search_products
from remy_api.llm import get_llm_client
from remy_api.llm.registry import get_prompt_id_llm
from remy_api.recipes.images import download_recipe_image
from remy_api.recipes.scraper import scrape_recipe
from remy_api.recipes.store import create_recipe, get_recipe, search_recipes
from remy_api.search import fetch_thumbnails, get_search_provider

__all__ = [
    "get_llm_client",
    "get_prompt_id_llm",
    "get_search_provider",
    "fetch_thumbnails",
    "search_recipes",
    "create_recipe",
    "get_recipe",
    "scrape_recipe",
    "download_recipe_image",
    "kroger_search_products",
    "kroger_add_items_to_cart",
]
