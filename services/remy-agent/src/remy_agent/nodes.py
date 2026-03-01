import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from .state import AgentState
from .utils import load_pantry_config, load_recipe_sources

logger = logging.getLogger(__name__)

MCP_TIMEOUT = 30  # seconds
MCP_MAX_RETRIES = 2

MEALIE_MCP_URL = os.getenv("MEALIE_MCP_URL", "http://localhost:8000/sse")
KROGER_MCP_URL = os.getenv("KROGER_MCP_URL", "http://localhost:8001/sse")
# Internal URL for API calls (Docker network)
MEALIE_BASE_URL = os.getenv("MEALIE_BASE_URL", "http://localhost:9925")
# External URL for browser-facing links (host machine)
MEALIE_EXTERNAL_URL = os.getenv("MEALIE_EXTERNAL_URL", "http://localhost:9925")

# Lazy-initialized LLM and search tool (for testability)
_llm = None
_search_tool = None


def get_llm():
    """Get or create the LLM instance."""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(model="gpt-4o", temperature=0)
    return _llm


def get_search_tool():
    """Get or create the search tool instance."""
    global _search_tool
    if _search_tool is None:
        _search_tool = DuckDuckGoSearchResults(num_results=5)
    return _search_tool


async def fetch_og_image(url: str, timeout: float = 5.0) -> str | None:
    """Fetch og:image meta tag from a URL. Returns image URL or None."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=headers) as client:
            # Fetch up to 200KB - some sites have og:image late in the HTML
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    return None

                content = b""
                async for chunk in response.aiter_bytes():
                    content += chunk
                    # Stop once we have enough (200KB should cover most sites)
                    if len(content) > 200000:
                        break

                html = content.decode("utf-8", errors="ignore")

                # Look for og:image meta tag
                og_match = re.search(
                    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                    html,
                    re.IGNORECASE,
                )
                if og_match:
                    return og_match.group(1)

                # Try alternate format: content before property
                og_match = re.search(
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                    html,
                    re.IGNORECASE,
                )
                if og_match:
                    return og_match.group(1)

    except Exception as e:
        logger.debug("Failed to fetch og:image from %s: %s", url, e)
    return None


async def fetch_thumbnails_parallel(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fetch og:image thumbnails for all results in parallel."""
    if not results:
        return results

    urls = [r["url"] for r in results]
    logger.debug("Fetching og:image for %d URLs in parallel...", len(urls))

    thumbnails = await asyncio.gather(*[fetch_og_image(url) for url in urls])

    for i, thumbnail in enumerate(thumbnails):
        if thumbnail:
            results[i]["image_url"] = thumbnail

    found = sum(1 for t in thumbnails if t)
    logger.debug("Found %d/%d og:image thumbnails", found, len(urls))

    return results


async def filter_web_results(results: list[dict[str, Any]], recipe_name: str) -> list[dict[str, Any]]:
    """Filter web results to remove roundups, listicles, and non-recipe pages."""
    if not results:
        return results

    titles = [r["name"] for r in results]
    filter_prompt = f"""I searched for "{recipe_name}" and got these results:
{json.dumps(titles, indent=2)}

Return a JSON array of titles that are ACTUAL SINGLE RECIPES (not roundups or collections).

EXCLUDE:
- Recipe roundups ("15 Best...", "20 Easy...", "10 Delicious...")
- Listicles ("X Recipes to Try", "X Ways to Cook...")
- Category/collection pages
- Non-recipe content (reviews, articles about food)

INCLUDE:
- Single recipe pages ("Pesto Pasta Recipe", "Easy Chicken Tikka Masala")
- Recipe titles without numbers at the start

Return ONLY the JSON array of titles to keep. No explanation."""

    try:
        response = await get_llm().ainvoke([HumanMessage(content=filter_prompt)])
        content = response.content.strip().replace("```json", "").replace("```", "").strip()
        valid_titles = json.loads(content)
        valid_titles_lower = [t.lower() for t in valid_titles]

        filtered = [r for r in results if r["name"].lower() in valid_titles_lower]
        logger.info("Web filter kept %d/%d results after filtering roundups", len(filtered), len(results))
        return filtered
    except Exception as e:
        logger.warning("Error filtering web results: %s", e)
        return results


async def _call_mcp_tool_inner(url: str, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Inner function that makes the actual MCP call via SSE transport."""
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return result


async def call_mcp_tool(url: str, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Helper to call an MCP tool via SSE with timeout and retry logic."""
    last_error: Exception | None = None

    for attempt in range(MCP_MAX_RETRIES + 1):
        try:
            result = await asyncio.wait_for(
                _call_mcp_tool_inner(url, tool_name, arguments),
                timeout=MCP_TIMEOUT,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(
                "MCP call timed out: %s/%s (attempt %d/%d)",
                url, tool_name, attempt + 1, MCP_MAX_RETRIES + 1,
            )
            last_error = TimeoutError(
                f"Timeout calling {tool_name} after {MCP_TIMEOUT}s"
            )
        except (ConnectionError, OSError) as e:
            logger.warning(
                "MCP connection error: %s/%s (attempt %d/%d): %s",
                url, tool_name, attempt + 1, MCP_MAX_RETRIES + 1, e,
            )
            last_error = e
            if attempt < MCP_MAX_RETRIES:
                await asyncio.sleep(0.5 * (attempt + 1))  # brief backoff
        except Exception as e:
            logger.error("MCP call failed: %s/%s: %s", url, tool_name, e)
            return None

    # All retries exhausted
    logger.error(
        "MCP call failed after %d attempts: %s/%s: %s",
        MCP_MAX_RETRIES + 1, url, tool_name, last_error,
    )
    return None


def _extract_urls(text: str) -> list[str]:
    """Extract URLs from text."""
    import re

    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    return re.findall(url_pattern, text)


async def search_recipes_node(state: AgentState) -> dict[str, Any]:
    """
    Extracts recipe names from messages and searches both Mealie and web in parallel.
    If URLs are provided, offers to import them directly.
    Returns recipe_options for user to select from.
    """
    messages = state["messages"]
    last_message = messages[-1].content

    # Check for URLs in the message
    urls = _extract_urls(last_message)
    if urls:
        recipe_options = []
        for url in urls:
            # Extract domain for display
            from urllib.parse import urlparse

            domain = urlparse(url).netloc.replace("www.", "")

            # Try to get a title from the URL path
            path = urlparse(url).path
            name_from_path = path.split("/")[-1].replace("-", " ").replace("_", " ").title()
            if not name_from_path or name_from_path == "/":
                name_from_path = f"Recipe from {domain}"

            recipe_options.append(
                {
                    "name": name_from_path,
                    "source": "web",
                    "url": url,
                    "slug": None,
                    "description": f"Import recipe from {domain}",
                    "image_url": None,
                }
            )

        return {
            "target_recipe_names": ["Recipe from URL"],
            "recipe_options": recipe_options,
            "messages": [AIMessage(content=f"I found {len(urls)} recipe URL(s). Select the one you'd like to import:")],
        }

    # Extract recipe names via LLM if not already set
    target_names = state.get("target_recipe_names", [])
    if not target_names:
        extraction_prompt = f"""
        Extract the recipe names the user wants to cook from the following text.
        Return ONLY a JSON list of strings, e.g. ["Shrimp Scampi", "Chicken Tikka"].
        If no recipe is specified, return [].

        Text: {last_message}
        """
        response = await get_llm().ainvoke([HumanMessage(content=extraction_prompt)])
        try:
            content = response.content.replace("```json", "").replace("```", "").strip()
            target_names = json.loads(content)
        except Exception:
            logger.warning("Failed to parse recipe names from LLM response")
            return {}

    if not target_names:
        return {
            "messages": [
                AIMessage(content="I couldn't find any recipe names in your request. What would you like to make?")
            ]
        }

    recipe_options = []

    for name in target_names:
        # Search Mealie, favorite sites, and general web in parallel
        mealie_task = _search_mealie(name)
        favorites_task = _search_favorite_sites(name)
        web_task = _search_web(name)
        mealie_results, favorites_results, web_results = await asyncio.gather(mealie_task, favorites_task, web_task)

        recipe_options.extend(mealie_results)
        recipe_options.extend(favorites_results)
        recipe_options.extend(web_results)

    # Deduplicate by URL and name (prefer earlier sources: mealie > favorites > web)
    seen_urls: set[str] = set()
    seen_names: set[str] = set()
    deduped = []
    for opt in recipe_options:
        url = opt.get("url", "")
        name_lower = opt.get("name", "").lower().strip()
        if url and url in seen_urls:
            continue
        if name_lower and name_lower in seen_names:
            continue
        if url:
            seen_urls.add(url)
        if name_lower:
            seen_names.add(name_lower)
        deduped.append(opt)
    recipe_options = deduped

    if not recipe_options:
        return {
            "target_recipe_names": target_names,
            "recipe_options": [],
            "messages": [
                AIMessage(
                    content=f"I couldn't find any recipes for: {', '.join(target_names)}. Try different recipe names."
                )
            ],
        }

    # Build summary message
    mealie_count = len([r for r in recipe_options if r["source"] == "mealie"])
    web_count = len([r for r in recipe_options if r["source"] == "web"])
    msg = f"I found {len(recipe_options)} recipe options"
    if mealie_count and web_count:
        msg += f" ({mealie_count} from your Mealie library, {web_count} from the web)"
    elif mealie_count:
        msg += " from your Mealie library"
    else:
        msg += " from the web"
    msg += ". Please select which recipes you'd like to use."

    return {"target_recipe_names": target_names, "recipe_options": recipe_options, "messages": [AIMessage(content=msg)]}


async def _search_mealie(recipe_name: str) -> list[dict[str, Any]]:
    """Search Mealie for recipes matching the name, filtered by LLM for relevance."""
    results = []
    try:
        # Search with more results to filter down
        search_result = await call_mcp_tool(MEALIE_MCP_URL, "get_recipes", {"search": recipe_name, "per_page": 15})
        if search_result and not search_result.isError and search_result.content:
            search_data = json.loads(search_result.content[0].text)
            recipes_list = []
            if isinstance(search_data, list):
                recipes_list = search_data
            elif isinstance(search_data, dict):
                recipes_list = search_data.get("items", [])

            if not recipes_list:
                return results

            # Use LLM to filter for actually relevant recipes
            recipe_names = [r.get("name", "") for r in recipes_list]
            filter_prompt = f"""I'm looking for recipes matching: "{recipe_name}"

Here are the search results from my recipe database:
{json.dumps(recipe_names, indent=2)}

Return a JSON array of the recipe names that are ACTUALLY relevant matches for what I'm looking for.
Only include recipes that are the same dish or very similar. Be strict - partial word matches don't count.

For example:
- If looking for "farro tomato mozzarella bake", "Coconut Fish and Tomato Bake" is NOT a match (different dish)
- If looking for "chicken tikka masala", "Chicken Tikka Masala" IS a match
- If looking for "pasta carbonara", "Spaghetti Carbonara" IS a match (same dish, different pasta)

Return ONLY the JSON array of matching recipe names, or [] if none match. No explanation."""

            response = await get_llm().ainvoke([HumanMessage(content=filter_prompt)])
            try:
                content = response.content.strip().replace("```json", "").replace("```", "").strip()
                relevant_names = json.loads(content)
                relevant_names_lower = [n.lower() for n in relevant_names]
            except Exception:
                # If parsing fails, fall back to returning top results
                relevant_names_lower = [r.get("name", "").lower() for r in recipes_list[:3]]

            for recipe in recipes_list:
                if recipe.get("name", "").lower() in relevant_names_lower:
                    slug = recipe.get("slug", "")
                    recipe_id = recipe.get("id", "")
                    image_name = recipe.get("image")
                    image_url = None
                    if image_name and recipe_id:
                        image_url = f"{MEALIE_EXTERNAL_URL}/api/media/recipes/{recipe_id}/images/min-original.webp"
                    results.append(
                        {
                            "name": recipe.get("name", ""),
                            "source": "mealie",
                            "url": f"{MEALIE_EXTERNAL_URL}/g/home/r/{slug}",
                            "slug": slug,
                            "description": recipe.get("description", "") or "Recipe from your Mealie library",
                            "image_url": image_url,
                        }
                    )
    except Exception as e:
        logger.error("Error searching Mealie for %s: %s", recipe_name, e)
    return results


async def _search_favorite_sites(recipe_name: str) -> list[dict[str, Any]]:
    """Search configured favorite recipe sites for matching recipes."""
    results = []
    config = load_recipe_sources()
    favorite_sources = config.get("favorite_sources", [])

    if not favorite_sources:
        return results

    for source in favorite_sources:
        domain = source.get("domain", "")
        site_name = source.get("name", domain)
        if not domain:
            continue

        try:
            search_query = f"site:{domain} {recipe_name} recipe"
            logger.debug("Searching favorite site %s: %s", site_name, search_query)
            search_results = get_search_tool().run(search_query)

            if not search_results:
                continue

            # Parse results
            links = re.findall(r"link:\s*(https?://[^\s,]+)", search_results)
            titles = re.findall(r"title:\s*([^,]+),\s*link:", search_results)
            snippets = re.findall(r"snippet:\s*([^,]+(?:,(?!\s*title:)[^,]*)*),\s*title:", search_results)

            for i, link in enumerate(links[:2]):  # Max 2 per site
                title = titles[i] if i < len(titles) else recipe_name
                snippet = snippets[i] if i < len(snippets) else f"Recipe from {site_name}"

                results.append(
                    {
                        "name": title.strip(),
                        "source": "web",
                        "url": link.strip(),
                        "slug": None,
                        "description": snippet.strip()[:200],
                        "image_url": None,
                    }
                )

            logger.debug("Found %d results from favorite site %s", min(len(links), 2), site_name)
        except Exception as e:
            logger.warning("Error searching favorite site %s: %s", site_name, e)

    # Filter out roundups and listicles, then fetch thumbnails
    if results:
        results = await filter_web_results(results, recipe_name)
        results = await fetch_thumbnails_parallel(results)

    return results


async def _search_web(recipe_name: str) -> list[dict[str, Any]]:
    """Search the web for recipes matching the name."""
    results = []
    try:
        search_query = f"{recipe_name} recipe"
        logger.info("Web search: %s", search_query)
        search_results = get_search_tool().run(search_query)
        logger.debug("Web search raw results length: %d", len(search_results) if search_results else 0)

        if not search_results:
            logger.info("No web search results from DuckDuckGo")
            return results

        # Parse the DuckDuckGoSearchResults format: "snippet: ..., title: ..., link: ..."
        # Find all link entries
        links = re.findall(r"link:\s*(https?://[^\s,]+)", search_results)
        titles = re.findall(r"title:\s*([^,]+),\s*link:", search_results)
        snippets = re.findall(r"snippet:\s*([^,]+(?:,(?!\s*title:)[^,]*)*),\s*title:", search_results)

        logger.debug("Web search found %d links, %d titles", len(links), len(titles))

        for i, link in enumerate(links[:5]):
            title = titles[i] if i < len(titles) else recipe_name
            snippet = snippets[i] if i < len(snippets) else "Recipe from the web"

            results.append(
                {
                    "name": title.strip(),
                    "source": "web",
                    "url": link.strip(),
                    "slug": None,
                    "description": snippet.strip()[:200],
                    "image_url": None,
                }
            )

        logger.info("Parsed %d web recipe options", len(results))

        # Filter out roundups and listicles
        results = await filter_web_results(results, recipe_name)

        # Fetch thumbnails in parallel
        results = await fetch_thumbnails_parallel(results)

    except Exception as e:
        logger.error("Error searching web for %s: %s", recipe_name, e, exc_info=True)
    return results


async def fetch_selected_recipes_node(state: AgentState) -> dict[str, Any]:
    """
    Fetches detailed recipe data for user-selected recipes.
    For Mealie recipes: fetches via get_recipe_detailed.
    For web recipes: scrapes URL, extracts recipe via LLM, creates in Mealie, then fetches details.
    """
    selected = state.get("selected_recipe_options", [])
    if not selected:
        return {"messages": [AIMessage(content="No recipes were selected. Please select at least one recipe.")]}

    fetched_recipes = []
    raw_ingredients = []
    messages = []

    for option in selected:
        if option["source"] == "mealie":
            # Fetch from Mealie
            recipe_data = await _fetch_mealie_recipe(option["slug"])
            if recipe_data:
                fetched_recipes.append(recipe_data)
                raw_ingredients.extend(_extract_ingredients(recipe_data))
        else:
            # Fetch from web, create in Mealie
            recipe_data = await _import_web_recipe(option)
            if recipe_data:
                fetched_recipes.append(recipe_data)
                raw_ingredients.extend(_extract_ingredients(recipe_data))
                messages.append(
                    AIMessage(
                        content=f"Imported '{recipe_data['name']}' from the web and saved to your Mealie library!"
                    )
                )

    if not fetched_recipes:
        return {"messages": [AIMessage(content="Couldn't fetch any of the selected recipes. Please try again.")]}

    return {"fetched_recipes": fetched_recipes, "raw_ingredients": raw_ingredients, "messages": messages}


async def _fetch_mealie_recipe(slug: str) -> dict[str, Any] | None:
    """Fetch detailed recipe data from Mealie by slug."""
    try:
        detail_result = await call_mcp_tool(MEALIE_MCP_URL, "get_recipe_detailed", {"slug": slug})
        if detail_result and not detail_result.isError:
            return json.loads(detail_result.content[0].text)
    except Exception as e:
        logger.error("Error fetching Mealie recipe %s: %s", slug, e)
    return None


async def _import_web_recipe(option: dict[str, Any]) -> dict[str, Any] | None:
    """
    Import a recipe from a web URL using Mealie's built-in URL scraper.
    Mealie will fetch and parse the recipe automatically.
    """
    try:
        url = option["url"]

        # Use Mealie's URL import feature
        create_result = await call_mcp_tool(
            MEALIE_MCP_URL, "create_recipe_from_url", {"url": url, "include_tags": True}
        )

        if create_result and not create_result.isError and create_result.content:
            created_data = json.loads(create_result.content[0].text)
            slug = created_data.get("slug")
            if slug:
                return await _fetch_mealie_recipe(slug)

        logger.warning("Could not import recipe from %s", url)
        return None
    except Exception as e:
        logger.error("Error importing web recipe from %s: %s", option.get('url'), e)
    return None


def _extract_ingredients(recipe_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract ingredients from recipe data."""
    ingredients = []
    if "recipeIngredient" in recipe_data:
        for ing in recipe_data["recipeIngredient"]:
            ingredients.append(
                {"original": ing.get("note", "") or ing.get("food", {}).get("name", ""), "recipe": recipe_data["name"]}
            )
    return ingredients


async def filter_ingredients_node(state: AgentState) -> dict[str, Any]:
    """
    Filters ingredients against pantry config.
    """
    import re

    raw_ingredients = state.get("raw_ingredients", [])
    pantry_config = load_pantry_config()
    bypass_staples = [s.lower() for s in pantry_config.get("bypass_staples", [])]

    pantry_items = []
    pending_cart = []

    for item in raw_ingredients:
        name = item["original"].lower()
        # Use word boundary matching to avoid false positives like "ice" in "sliced"
        is_staple = any(re.search(rf"\b{re.escape(staple)}\b", name) for staple in bypass_staples)

        if is_staple:
            pantry_items.append(item)
        else:
            pending_cart.append(item)

    messages = []
    if pending_cart:
        items_str = ", ".join([i["original"] for i in pending_cart[:5]])
        if len(pending_cart) > 5:
            items_str += "..."
        messages.append(
            AIMessage(content=f"I've prepared a list of ingredients for your approval, including: {items_str}")
        )

    return {"pantry_items": pantry_items, "pending_cart": pending_cart, "messages": messages}


async def _batch_extract_products(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Batch extract product names and quantities from all ingredients in a single LLM call."""
    ingredients = [item["original"] for item in items]

    batch_prompt = f"""Extract product names and quantities for these recipe ingredients.

For EACH ingredient, return the grocery store search term and quantity to buy.

RULES:
- Use American grocery store product names
- For produce, prefix with "fresh" (e.g., "fresh cilantro", "fresh green onions")
- BEANS: Default to CANNED unless it says "dry/dried" (e.g., "black beans" -> "canned black beans")
- Quantity = number of PACKAGES to buy, not recipe amount:
  - "6 scallions" -> quantity 1 (one bunch)
  - "3 cloves garlic" -> quantity 1 (one head)
  - "2 cans tomatoes" -> quantity 2
  - "1 cup beans" -> quantity 1 (one can)

Ingredients:
{json.dumps(ingredients, indent=2)}

Return a JSON object where keys are the original ingredient strings and values are arrays of {{"product": str, "quantity": int}}.
Example: {{"1 onion, diced": [{{"product": "yellow onion", "quantity": 1}}], "salt and pepper": [{{"product": "salt", "quantity": 1}}, {{"product": "black pepper", "quantity": 1}}]}}

Return ONLY the JSON object."""

    try:
        response = await get_llm().ainvoke([HumanMessage(content=batch_prompt)])
        content = response.content.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except Exception as e:
        logger.warning("Batch extract error: %s, falling back to individual extraction", e)
        return {}


async def _process_cart_item(
    item: dict[str, Any], modality: str, location_id: str, fulfillment_filter: str,
    pre_extracted: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Process a single cart item - search and add to cart. Returns a list (may be multiple products)."""
    query = item["original"]
    logger.info("Processing cart item: %s", query)

    # Use pre-extracted products if available, otherwise extract individually
    if pre_extracted:
        products_to_order = [
            {"search_term": p.get("product", query), "quantity": max(1, int(p.get("quantity", 1)))}
            for p in pre_extracted
        ]
    else:
        # Fallback: Use LLM to extract product name(s) AND quantity
        clean_prompt = f"""
    Extract the product name(s) and quantity to BUY from this ingredient line: "{query}".

    IMPORTANT: If the ingredient lists multiple items (with "and", "or", commas, or "mixture"),
    return an array of products. For "or" choices, include all options. For "mixture of all", include all.

    Return JSON - either a single object OR an array of objects, each with "product" and "quantity" fields.
    - "product": the GROCERY STORE search term (use common American supermarket names, not culinary terms)
    - "quantity": the number of PACKAGES/ITEMS to buy from the store (not the recipe amount)

    CRITICAL - Use grocery store product names. For PRODUCE items, prefix with "fresh" to avoid packaged/processed products:
    - scallions -> "fresh green onions"
    - shallots -> "fresh shallots"
    - cilantro -> "fresh cilantro"
    - parsley -> "fresh parsley"
    - mint -> "fresh mint"
    - basil -> "fresh basil"
    - courgette -> "fresh zucchini"
    - aubergine -> "fresh eggplant"
    - rocket -> "fresh arugula"
    - coriander (leaves) -> "fresh cilantro"
    - spring onions -> "fresh green onions"
    - capsicum -> "fresh bell pepper"
    - leeks -> "fresh leeks"
    - ginger -> "fresh ginger"
    - garlic -> "fresh garlic"
    - onion -> "yellow onion" or "white onion" or "red onion"
    - mince/minced meat -> "ground beef" or "ground turkey" etc.
    - double cream -> "heavy cream"
    - caster sugar -> "granulated sugar"
    - icing sugar -> "powdered sugar"
    - plain flour -> "all purpose flour"
    - bicarbonate of soda -> "baking soda"
    - chickpeas (dried) -> "dried garbanzo beans"
    - prawns -> "shrimp"

    BEANS: Default to CANNED unless recipe specifically says "dry", "dried", or "soaked":
    - "black beans" -> "canned black beans"
    - "kidney beans" -> "canned kidney beans"
    - "pinto beans" -> "canned pinto beans"
    - "cannellini beans" -> "canned cannellini beans"
    - "chickpeas" or "garbanzo beans" -> "canned chickpeas"
    - "1 cup black beans" -> "canned black beans" (quantity 1)
    - "dried black beans" or "dry black beans" -> "dried black beans"

    Think about how the product is sold at a grocery store:
    - Produce (limes, onions, peppers): sold individually or by bunch
    - Green onions/scallions: sold in bunches, so "6 scallions" = quantity 1 (one bunch)
    - Dairy (milk, cream, butter): sold in containers, so "0.5 cups heavy cream" = quantity 1
    - Canned goods: sold per can, so "2 cans tomatoes" = quantity 2
    - Meat: sold by package, so "1 lb ground beef" = quantity 1
    - Fresh herbs: sold in bunches, so "2 cups cilantro" = quantity 1 (one bunch)
    - Garlic: sold by head, so "3 cloves garlic" = quantity 1 (one head has many cloves)
    - Eggs: sold by dozen, so "2 eggs" = quantity 1 (one carton)

    Examples:
    "6 scallions, sliced" -> {{"product": "fresh green onions", "quantity": 1}}
    "2 limes" -> {{"product": "fresh limes", "quantity": 2}}
    "1 onion, diced" -> {{"product": "yellow onion", "quantity": 1}}
    "0.5 cups heavy cream" -> {{"product": "heavy cream", "quantity": 1}}
    "salt and pepper to taste" -> [{{"product": "salt", "quantity": 1}}, {{"product": "black pepper", "quantity": 1}}]
    "cilantro, parsley, or mint, preferably a mixture" -> [{{"product": "fresh cilantro", "quantity": 1}}, {{"product": "fresh parsley", "quantity": 1}}, {{"product": "fresh mint", "quantity": 1}}]
    "1 red or yellow bell pepper" -> {{"product": "fresh bell pepper", "quantity": 1}}
    "2 cans (14oz) diced tomatoes" -> {{"product": "canned diced tomatoes", "quantity": 2}}
    "500g dried chickpeas" -> {{"product": "dried garbanzo beans", "quantity": 1}}
    "3 cloves garlic, minced" -> {{"product": "fresh garlic", "quantity": 1}}
    "1 cup black beans" -> {{"product": "canned black beans", "quantity": 1}}
    "1 can kidney beans, drained" -> {{"product": "canned kidney beans", "quantity": 1}}

    Return ONLY the JSON, no other text.
    """
        try:
            response = await get_llm().ainvoke([HumanMessage(content=clean_prompt)])
            content = response.content.strip().replace("```json", "").replace("```", "").strip()
            parsed = json.loads(content)

            # Normalize to list
            if isinstance(parsed, dict):
                parsed = [parsed]

            products_to_order = []
            for p in parsed:
                products_to_order.append(
                    {"search_term": p.get("product", query), "quantity": max(1, int(p.get("quantity", 1)))}
                )
        except Exception as e:
            logger.warning("Failed to parse product from '%s': %s", query, e)
            products_to_order = [{"search_term": query, "quantity": 1}]

    # Process each product
    results = []
    for prod in products_to_order:
        search_term = prod["search_term"]
        quantity = prod["quantity"]

        # Search for products (don't filter by fulfillment - check availability after)
        search_args = {"search_term": search_term, "limit": 10}
        if location_id:
            search_args["location_id"] = location_id

        logger.debug("Searching Kroger for: %s with args: %s", search_term, search_args)
        search_res = await call_mcp_tool(KROGER_MCP_URL, "search_products", search_args)
        logger.debug(
            "Kroger search result: found=%s, isError=%s",
            search_res is not None,
            search_res.isError if search_res else "N/A",
        )
        if not search_res or search_res.isError:
            results.append({"item": search_term, "quantity": quantity, "status": "search_failed"})
            continue

        try:
            search_data = json.loads(search_res.content[0].text)

            if not search_data.get("success"):
                results.append(
                    {
                        "item": search_term,
                        "quantity": quantity,
                        "status": "error",
                        "error": search_data.get("error", search_data.get("message", "Unknown search error")),
                    }
                )
                continue

            products = search_data.get("data", [])

            if not products:
                results.append(
                    {
                        "item": search_term,
                        "quantity": quantity,
                        "status": "not_found",
                        "error": f"No products found for '{search_term}'",
                    }
                )
                continue

            # Use LLM to pick the best matching product - include size info
            product_options = "\n".join(
                [
                    f"{i + 1}. {p.get('description', 'Unknown')} - {p.get('item', {}).get('size', 'unknown size')}"
                    for i, p in enumerate(products[:8])
                ]
            )

            pick_prompt = f"""I'm looking for: "{search_term}" (quantity needed: {quantity})

Here are the search results from the grocery store:
{product_options}

Which number is the BEST match for what I'm looking for? Consider:
- I want the actual ingredient, not a prepared food or seasoning containing it
- For produce, prefer fresh/raw items over processed
- IMPORTANT: Prefer SINGLE items over multi-packs unless I need a large quantity
  - "1 can black beans" -> pick a single can, NOT a 4-pack
  - "2 cans tomatoes" -> pick a single can (I'll order qty 2), NOT a multi-pack
  - Only pick multi-packs if quantity needed is 4+
- Avoid "BIG DEAL", "Value Pack", "Family Size" unless quantity justifies it
- "green onions" = scallions (fresh produce), NOT noodles or dips
- "fresh mint" = mint leaves (herb), NOT gum or candy

Reply with ONLY the number (1-{min(8, len(products))}) of the best match, nothing else."""

            # Rank products by LLM preference
            try:
                pick_response = await get_llm().ainvoke([HumanMessage(content=pick_prompt)])
                pick_num = int(pick_response.content.strip()) - 1
                if 0 <= pick_num < len(products):
                    # Reorder products with LLM's pick first
                    preferred_order = [pick_num] + [i for i in range(len(products)) if i != pick_num]
                else:
                    preferred_order = list(range(len(products)))
            except Exception:
                preferred_order = list(range(len(products)))

            # Try products in order until we find one in stock
            selected_product = None
            fallback_product = None  # Product with unknown stock (empty) as last resort
            is_substitute = False

            for idx in preferred_order[:8]:  # Try up to 8 products
                product = products[idx]
                inventory = product.get("item", {}).get("inventory", {})
                stock_level = inventory.get("stockLevel", "").upper()

                # Also check fulfillment availability
                fulfillment_info = product.get("item", {}).get("fulfillment", {})
                is_available_for_fulfillment = fulfillment_info.get(fulfillment_filter.lower()) is not False

                logger.debug(
                    "Checking product: %s, stock: %s, fulfillment: %s",
                    product['description'], stock_level, fulfillment_info,
                )

                if not is_available_for_fulfillment:
                    continue

                # Prefer items with explicit stock levels
                if stock_level in ("HIGH", "LOW", "MEDIUM"):
                    selected_product = product
                    is_substitute = idx != preferred_order[0]
                    break
                elif stock_level == "" and fallback_product is None:
                    # No stock info - save as fallback but keep looking
                    fallback_product = product

            # Use fallback if no confirmed in-stock item found
            if not selected_product and fallback_product:
                selected_product = fallback_product
                is_substitute = True  # Treat as substitute since stock is unknown

            if not selected_product:
                # All products out of stock
                results.append(
                    {
                        "item": search_term,
                        "quantity": quantity,
                        "status": "unavailable",
                        "error": "All matching products are out of stock",
                    }
                )
                continue

            upc = selected_product["upc"]
            logger.info(
                "Selected product: %s, UPC: %s, substitute: %s",
                selected_product['description'], upc, is_substitute,
            )

            # Add to Cart with correct quantity
            logger.info("Adding to cart: %s x%d", upc, quantity)
            add_res = await call_mcp_tool(
                KROGER_MCP_URL, "add_items_to_cart", {"product_id": upc, "quantity": quantity, "modality": modality}
            )
            logger.debug(
                "Add to cart result: found=%s, isError=%s",
                add_res is not None,
                add_res.isError if add_res else "N/A",
            )

            status = "failed"
            error_details = None

            if add_res and not add_res.isError:
                try:
                    if add_res.content:
                        res_data = json.loads(add_res.content[0].text)
                        if res_data.get("success"):
                            status = "added"
                            if is_substitute:
                                error_details = "Substituted (first choice unavailable)"
                        else:
                            status = "failed"
                            error_details = res_data.get("error")
                except Exception:
                    status = "added"
                    if is_substitute:
                        error_details = "Substituted (first choice unavailable)"

            result_item = {
                "item": search_term,
                "quantity": quantity,
                "product": selected_product["description"],
                "status": status,
            }
            if error_details:
                result_item["error"] = error_details

            results.append(result_item)

        except Exception as e:
            results.append({"item": search_term, "quantity": quantity, "status": "error", "error": str(e)})

    return results


async def execute_order_node(state: AgentState) -> dict[str, Any]:
    """
    Adds approved items to Kroger cart in parallel.
    Extracts quantities from ingredient lines and checks product availability.
    """
    approved_cart = state.get("approved_cart", [])
    modality = state.get("fulfillment_method", "PICKUP")
    location_id = state.get("preferred_store_id")

    logger.info(
        "Starting order execution with %d items, modality=%s, location=%s",
        len(approved_cart), modality, location_id,
    )

    # Map modality to Kroger fulfillment filter
    fulfillment_filter = "pickup" if modality == "PICKUP" else "delivery"

    # Batch extract all product names/quantities in one LLM call (faster than individual calls)
    logger.info("Batch extracting product names...")
    extracted_products = await _batch_extract_products(approved_cart)
    logger.info("Extracted %d items from batch", len(extracted_products))

    # Process all items in parallel, passing pre-extracted data
    tasks = []
    for item in approved_cart:
        pre_extracted = extracted_products.get(item["original"])
        tasks.append(_process_cart_item(item, modality, location_id, fulfillment_filter, pre_extracted))

    nested_results = await asyncio.gather(*tasks)

    # Flatten results (each item can return multiple products)
    order_results = []
    for result_list in nested_results:
        order_results.extend(result_list)

    return {
        "order_result": {"items": order_results},
        "messages": [
            AIMessage(content="I've processed your order request with Kroger. Check the summary for details!")
        ],
    }
