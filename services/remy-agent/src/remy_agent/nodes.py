import os
import json
import asyncio
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchResults
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from .state import AgentState
from .utils import load_pantry_config, load_recipe_sources

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

async def call_mcp_tool(url: str, tool_name: str, arguments: Dict[str, Any] = {}) -> Any:
    """Helper to call an MCP tool via SSE"""
    try:
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return result
    except Exception as e:
        print(f"Error calling {tool_name} at {url}: {e}")
        return None

def _extract_urls(text: str) -> List[str]:
    """Extract URLs from text."""
    import re
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    return re.findall(url_pattern, text)


async def search_recipes_node(state: AgentState) -> Dict[str, Any]:
    """
    Extracts recipe names from messages and searches both Mealie and web in parallel.
    If URLs are provided, offers to import them directly.
    Returns recipe_options for user to select from.
    """
    messages = state['messages']
    last_message = messages[-1].content

    # Check for URLs in the message
    urls = _extract_urls(last_message)
    if urls:
        recipe_options = []
        for url in urls:
            # Extract domain for display
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.replace('www.', '')

            # Try to get a title from the URL path
            path = urlparse(url).path
            name_from_path = path.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
            if not name_from_path or name_from_path == '/':
                name_from_path = f"Recipe from {domain}"

            recipe_options.append({
                "name": name_from_path,
                "source": "web",
                "url": url,
                "slug": None,
                "description": f"Import recipe from {domain}"
            })

        return {
            "target_recipe_names": [f"Recipe from URL"],
            "recipe_options": recipe_options,
            "messages": [AIMessage(content=f"I found {len(urls)} recipe URL(s). Select the one you'd like to import:")]
        }

    # Extract recipe names via LLM if not already set
    target_names = state.get('target_recipe_names', [])
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
        except:
            print("Failed to parse recipe names")
            return {}

    if not target_names:
        return {"messages": [AIMessage(content="I couldn't find any recipe names in your request. What would you like to make?")]}

    recipe_options = []

    for name in target_names:
        # Search Mealie, favorite sites, and general web in parallel
        mealie_task = _search_mealie(name)
        favorites_task = _search_favorite_sites(name)
        web_task = _search_web(name)
        mealie_results, favorites_results, web_results = await asyncio.gather(
            mealie_task, favorites_task, web_task
        )

        recipe_options.extend(mealie_results)
        recipe_options.extend(favorites_results)
        recipe_options.extend(web_results)

    if not recipe_options:
        return {
            "target_recipe_names": target_names,
            "recipe_options": [],
            "messages": [AIMessage(content=f"I couldn't find any recipes for: {', '.join(target_names)}. Try different recipe names.")]
        }

    # Build summary message
    mealie_count = len([r for r in recipe_options if r['source'] == 'mealie'])
    web_count = len([r for r in recipe_options if r['source'] == 'web'])
    msg = f"I found {len(recipe_options)} recipe options"
    if mealie_count and web_count:
        msg += f" ({mealie_count} from your Mealie library, {web_count} from the web)"
    elif mealie_count:
        msg += f" from your Mealie library"
    else:
        msg += f" from the web"
    msg += ". Please select which recipes you'd like to use."

    return {
        "target_recipe_names": target_names,
        "recipe_options": recipe_options,
        "messages": [AIMessage(content=msg)]
    }


async def _search_mealie(recipe_name: str) -> List[Dict[str, Any]]:
    """Search Mealie for recipes matching the name."""
    results = []
    try:
        search_result = await call_mcp_tool(MEALIE_MCP_URL, "get_recipes", {"search": recipe_name, "per_page": 5})
        if search_result and not search_result.isError and search_result.content:
            search_data = json.loads(search_result.content[0].text)
            recipes_list = []
            if isinstance(search_data, list):
                recipes_list = search_data
            elif isinstance(search_data, dict):
                recipes_list = search_data.get('items', [])

            for recipe in recipes_list[:5]:
                slug = recipe.get('slug', '')
                results.append({
                    "name": recipe.get('name', ''),
                    "source": "mealie",
                    "url": f"{MEALIE_EXTERNAL_URL}/g/home/r/{slug}",
                    "slug": slug,
                    "description": recipe.get('description', '') or "Recipe from your Mealie library"
                })
    except Exception as e:
        print(f"Error searching Mealie for {recipe_name}: {e}")
    return results


async def _search_favorite_sites(recipe_name: str) -> List[Dict[str, Any]]:
    """Search configured favorite recipe sites for matching recipes."""
    results = []
    config = load_recipe_sources()
    favorite_sources = config.get('favorite_sources', [])

    if not favorite_sources:
        return results

    for source in favorite_sources:
        domain = source.get('domain', '')
        site_name = source.get('name', domain)
        if not domain:
            continue

        try:
            search_query = f"site:{domain} {recipe_name} recipe"
            print(f"[Favorite Sites] Searching {site_name}: {search_query}")
            search_results = get_search_tool().run(search_query)

            if not search_results:
                continue

            # Parse results
            import re
            links = re.findall(r'link:\s*(https?://[^\s,]+)', search_results)
            titles = re.findall(r'title:\s*([^,]+),\s*link:', search_results)
            snippets = re.findall(r'snippet:\s*([^,]+(?:,(?!\s*title:)[^,]*)*),\s*title:', search_results)

            for i, link in enumerate(links[:2]):  # Max 2 per site
                title = titles[i] if i < len(titles) else recipe_name
                snippet = snippets[i] if i < len(snippets) else f"Recipe from {site_name}"

                results.append({
                    "name": title.strip(),
                    "source": "web",
                    "url": link.strip(),
                    "slug": None,
                    "description": snippet.strip()[:200]
                })

            print(f"[Favorite Sites] Found {min(len(links), 2)} results from {site_name}")
        except Exception as e:
            print(f"[Favorite Sites] Error searching {site_name}: {e}")

    return results


async def _search_web(recipe_name: str) -> List[Dict[str, Any]]:
    """Search the web for recipes matching the name."""
    results = []
    try:
        search_query = f"{recipe_name} recipe"
        print(f"[Web Search] Searching for: {search_query}")
        search_results = get_search_tool().run(search_query)
        print(f"[Web Search] Raw results length: {len(search_results) if search_results else 0}")

        if not search_results:
            print("[Web Search] No results from DuckDuckGo")
            return results

        # Parse the DuckDuckGoSearchResults format: "snippet: ..., title: ..., link: ..."
        # Results are separated by comma-space between entries
        import re

        # Find all link entries
        links = re.findall(r'link:\s*(https?://[^\s,]+)', search_results)
        titles = re.findall(r'title:\s*([^,]+),\s*link:', search_results)
        snippets = re.findall(r'snippet:\s*([^,]+(?:,(?!\s*title:)[^,]*)*),\s*title:', search_results)

        print(f"[Web Search] Found {len(links)} links, {len(titles)} titles")

        for i, link in enumerate(links[:5]):
            title = titles[i] if i < len(titles) else recipe_name
            snippet = snippets[i] if i < len(snippets) else "Recipe from the web"

            results.append({
                "name": title.strip(),
                "source": "web",
                "url": link.strip(),
                "slug": None,
                "description": snippet.strip()[:200]
            })

        print(f"[Web Search] Parsed {len(results)} web recipe options")
    except Exception as e:
        print(f"[Web Search] Error searching web for {recipe_name}: {e}")
        import traceback
        traceback.print_exc()
    return results


async def fetch_selected_recipes_node(state: AgentState) -> Dict[str, Any]:
    """
    Fetches detailed recipe data for user-selected recipes.
    For Mealie recipes: fetches via get_recipe_detailed.
    For web recipes: scrapes URL, extracts recipe via LLM, creates in Mealie, then fetches details.
    """
    selected = state.get('selected_recipe_options', [])
    if not selected:
        return {"messages": [AIMessage(content="No recipes were selected. Please select at least one recipe.")]}

    fetched_recipes = []
    raw_ingredients = []
    messages = []

    for option in selected:
        if option['source'] == 'mealie':
            # Fetch from Mealie
            recipe_data = await _fetch_mealie_recipe(option['slug'])
            if recipe_data:
                fetched_recipes.append(recipe_data)
                raw_ingredients.extend(_extract_ingredients(recipe_data))
        else:
            # Fetch from web, create in Mealie
            recipe_data = await _import_web_recipe(option)
            if recipe_data:
                fetched_recipes.append(recipe_data)
                raw_ingredients.extend(_extract_ingredients(recipe_data))
                messages.append(AIMessage(content=f"Imported '{recipe_data['name']}' from the web and saved to your Mealie library!"))

    if not fetched_recipes:
        return {"messages": [AIMessage(content="Couldn't fetch any of the selected recipes. Please try again.")]}

    return {
        "fetched_recipes": fetched_recipes,
        "raw_ingredients": raw_ingredients,
        "messages": messages
    }


async def _fetch_mealie_recipe(slug: str) -> Dict[str, Any] | None:
    """Fetch detailed recipe data from Mealie by slug."""
    try:
        detail_result = await call_mcp_tool(MEALIE_MCP_URL, "get_recipe_detailed", {"slug": slug})
        if detail_result and not detail_result.isError:
            return json.loads(detail_result.content[0].text)
    except Exception as e:
        print(f"Error fetching Mealie recipe {slug}: {e}")
    return None


async def _import_web_recipe(option: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Import a recipe from a web URL using Mealie's built-in URL scraper.
    Mealie will fetch and parse the recipe automatically.
    """
    try:
        url = option['url']

        # Use Mealie's URL import feature
        create_result = await call_mcp_tool(MEALIE_MCP_URL, "create_recipe_from_url", {
            "url": url,
            "include_tags": True
        })

        if create_result and not create_result.isError and create_result.content:
            created_data = json.loads(create_result.content[0].text)
            slug = created_data.get('slug')
            if slug:
                return await _fetch_mealie_recipe(slug)

        print(f"Could not import recipe from {url}")
        return None
    except Exception as e:
        print(f"Error importing web recipe from {option.get('url')}: {e}")
    return None


def _extract_ingredients(recipe_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract ingredients from recipe data."""
    ingredients = []
    if 'recipeIngredient' in recipe_data:
        for ing in recipe_data['recipeIngredient']:
            ingredients.append({
                "original": ing.get('note', '') or ing.get('food', {}).get('name', ''),
                "recipe": recipe_data['name']
            })
    return ingredients


async def filter_ingredients_node(state: AgentState) -> Dict[str, Any]:
    """
    Filters ingredients against pantry config.
    """
    import re
    raw_ingredients = state.get('raw_ingredients', [])
    pantry_config = load_pantry_config()
    bypass_staples = [s.lower() for s in pantry_config.get('bypass_staples', [])]

    pantry_items = []
    pending_cart = []

    for item in raw_ingredients:
        name = item['original'].lower()
        # Use word boundary matching to avoid false positives like "ice" in "sliced"
        is_staple = any(re.search(rf'\b{re.escape(staple)}\b', name) for staple in bypass_staples)

        if is_staple:
            pantry_items.append(item)
        else:
            pending_cart.append(item)
            
    messages = []
    if pending_cart:
        items_str = ", ".join([i['original'] for i in pending_cart[:5]])
        if len(pending_cart) > 5:
            items_str += "..."
        messages.append(AIMessage(content=f"I've prepared a list of ingredients for your approval, including: {items_str}"))

    return {
        "pantry_items": pantry_items,
        "pending_cart": pending_cart,
        "messages": messages
    }

async def _process_cart_item(item: Dict[str, Any], modality: str, location_id: str, fulfillment_filter: str) -> List[Dict[str, Any]]:
    """Process a single cart item - extract info, search, and add to cart. Returns a list (may be multiple products)."""
    query = item['original']
    print(f"[process_cart_item] Processing: {query}", flush=True)

    # Use LLM to extract product name(s) AND quantity
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
            products_to_order.append({
                "search_term": p.get("product", query),
                "quantity": max(1, int(p.get("quantity", 1)))
            })
    except Exception as e:
        print(f"[Order] Failed to parse '{query}': {e}")
        products_to_order = [{"search_term": query, "quantity": 1}]

    # Process each product
    results = []
    for prod in products_to_order:
        search_term = prod["search_term"]
        quantity = prod["quantity"]

        # Search for products (don't filter by fulfillment - check availability after)
        search_args = {
            "search_term": search_term,
            "limit": 10
        }
        if location_id:
            search_args["location_id"] = location_id

        print(f"[process_cart_item] Searching for: {search_term} with args: {search_args}", flush=True)
        search_res = await call_mcp_tool(KROGER_MCP_URL, "search_products", search_args)
        print(f"[process_cart_item] Search result: {search_res is not None}, isError: {search_res.isError if search_res else 'N/A'}", flush=True)
        if not search_res or search_res.isError:
            results.append({"item": search_term, "quantity": quantity, "status": "search_failed"})
            continue

        try:
            search_data = json.loads(search_res.content[0].text)

            if not search_data.get("success"):
                results.append({
                    "item": search_term,
                    "quantity": quantity,
                    "status": "error",
                    "error": search_data.get("error", search_data.get("message", "Unknown search error"))
                })
                continue

            products = search_data.get("data", [])

            if not products:
                results.append({
                    "item": search_term,
                    "quantity": quantity,
                    "status": "not_found",
                    "error": f"No products found for '{search_term}'"
                })
                continue

            # Use LLM to pick the best matching product
            product_options = "\n".join([
                f"{i+1}. {p.get('description', 'Unknown')} (UPC: {p.get('upc', 'N/A')})"
                for i, p in enumerate(products[:8])
            ])

            pick_prompt = f"""I'm looking for: "{search_term}"

Here are the search results from the grocery store:
{product_options}

Which number is the BEST match for what I'm looking for? Consider:
- I want the actual ingredient, not a prepared food or seasoning containing it
- For produce, prefer fresh/raw items over processed
- "green onions" = scallions (fresh produce), NOT noodles or dips
- "fresh mint" = mint leaves (herb), NOT gum or candy
- "cilantro" = fresh cilantro (herb), NOT dried or seasoning

Reply with ONLY the number (1-{min(8, len(products))}) of the best match, nothing else."""

            try:
                pick_response = await get_llm().ainvoke([HumanMessage(content=pick_prompt)])
                pick_num = int(pick_response.content.strip()) - 1
                if 0 <= pick_num < len(products):
                    selected_product = products[pick_num]
                else:
                    selected_product = products[0]
            except:
                selected_product = products[0]

            # Check if the selected product is available for fulfillment
            fulfillment_info = selected_product.get("item", {}).get("fulfillment", {})
            is_unavailable = not fulfillment_info.get(fulfillment_filter.lower(), False)

            upc = selected_product['upc']
            print(f"[process_cart_item] Found product: {selected_product['description']}, UPC: {upc}, unavailable: {is_unavailable}", flush=True)

            # Add to Cart with correct quantity
            print(f"[process_cart_item] Adding to cart: {upc} x{quantity}", flush=True)
            add_res = await call_mcp_tool(KROGER_MCP_URL, "add_items_to_cart", {
                "product_id": upc,
                "quantity": quantity,
                "modality": modality
            })
            print(f"[process_cart_item] Add result: {add_res is not None}, isError: {add_res.isError if add_res else 'N/A'}", flush=True)

            status = "failed"
            error_details = None

            if add_res and not add_res.isError:
                try:
                    if add_res.content:
                        res_data = json.loads(add_res.content[0].text)
                        if res_data.get("success"):
                            status = "added"
                            if is_unavailable:
                                error_details = f"Note: May not be available for {modality}"
                        else:
                            status = "failed"
                            error_details = res_data.get("error")
                except:
                    status = "added"
                    if is_unavailable:
                        error_details = f"Note: May not be available for {modality}"

            result_item = {
                "item": search_term,
                "quantity": quantity,
                "product": selected_product['description'],
                "status": status
            }
            if error_details:
                result_item["error"] = error_details

            results.append(result_item)

        except Exception as e:
            results.append({"item": search_term, "quantity": quantity, "status": "error", "error": str(e)})

    return results


async def execute_order_node(state: AgentState) -> Dict[str, Any]:
    """
    Adds approved items to Kroger cart in parallel.
    Extracts quantities from ingredient lines and checks product availability.
    """
    approved_cart = state.get('approved_cart', [])
    modality = state.get('fulfillment_method', 'PICKUP')
    location_id = state.get('preferred_store_id')

    print(f"[execute_order] Starting with {len(approved_cart)} items, modality={modality}, location={location_id}", flush=True)

    # Map modality to Kroger fulfillment filter
    fulfillment_filter = "pickup" if modality == "PICKUP" else "delivery"

    # Process all items in parallel
    tasks = [
        _process_cart_item(item, modality, location_id, fulfillment_filter)
        for item in approved_cart
    ]
    nested_results = await asyncio.gather(*tasks)

    # Flatten results (each item can return multiple products)
    order_results = []
    for result_list in nested_results:
        order_results.extend(result_list)

    return {
        "order_result": {"items": order_results},
        "messages": [AIMessage(content="I've processed your order request with Kroger. Check the summary for details!")]
    }