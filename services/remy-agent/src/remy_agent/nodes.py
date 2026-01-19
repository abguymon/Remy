import os
import json
import asyncio
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchRun
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from .state import AgentState
from .utils import load_pantry_config

MEALIE_MCP_URL = os.getenv("MEALIE_MCP_URL", "http://localhost:8000/sse")
KROGER_MCP_URL = os.getenv("KROGER_MCP_URL", "http://localhost:8001/sse")

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0)
search_tool = DuckDuckGoSearchRun()

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

async def fetch_recipes_node(state: AgentState) -> Dict[str, Any]:
    """
    Extracts recipe intent from messages and fetches from Mealie.
    """
    messages = state['messages']
    last_message = messages[-1].content
    
    # Simple extraction via LLM if target names not set
    target_names = state.get('target_recipe_names', [])
    if not target_names:
        extraction_prompt = f"""
        Extract the recipe names the user wants to cook from the following text.
        Return ONLY a JSON list of strings, e.g. ["Shrimp Scampi", "Chicken Tikka"].
        If no recipe is specified, return [].
        
        Text: {last_message}
        """
        response = await llm.ainvoke([HumanMessage(content=extraction_prompt)])
        try:
            content = response.content.replace("```json", "").replace("```", "").strip()
            target_names = json.loads(content)
        except:
            print("Failed to parse recipe names")
            return {}

    if not target_names:
        return {"messages": [AIMessage(content="I couldn't find any recipe names in your request. What would you like to make?")]}

    fetched_recipes = []
    raw_ingredients = []
    not_found = []
    
    for name in target_names:
        # 1. Search for recipe
        search_result = await call_mcp_tool(MEALIE_MCP_URL, "get_recipes", {"search": name})
        found = False
        if search_result and not search_result.isError and search_result.content:
            try:
                search_data = json.loads(search_result.content[0].text)
                recipes_list = []
                if isinstance(search_data, list):
                    recipes_list = search_data
                elif isinstance(search_data, dict):
                    recipes_list = search_data.get('items', [])
                
                if recipes_list:
                    slug = recipes_list[0]['slug']
                    # 2. Get detailed recipe
                    detail_result = await call_mcp_tool(MEALIE_MCP_URL, "get_recipe_detailed", {"slug": slug})
                    if detail_result and not detail_result.isError:
                        recipe_data = json.loads(detail_result.content[0].text)
                        fetched_recipes.append(recipe_data)
                        found = True
                        
                        if 'recipeIngredient' in recipe_data:
                            for ing in recipe_data['recipeIngredient']:
                                raw_ingredients.append({
                                    "original": ing.get('note', '') or ing.get('food', {}).get('name', ''),
                                    "recipe": recipe_data['name']
                                })
            except Exception as e:
                print(f"Error processing recipe {name}: {e}")
        
        if not found:
            not_found.append(name)

    return {
        "target_recipe_names": target_names,
        "fetched_recipes": fetched_recipes,
        "raw_ingredients": raw_ingredients,
        "not_found_recipes": not_found
    }

async def web_search_node(state: AgentState) -> Dict[str, Any]:
    """
    Searches the web for recipes not found in Mealie.
    """
    not_found = state.get("not_found_recipes", [])
    if not not_found:
        return {}
    
    new_raw_ingredients = []
    messages = []
    
    for name in not_found:
        try:
            search_query = f"{name} recipe ingredients"
            search_results = search_tool.run(search_query)
            
            extraction_prompt = f"""
            Extract the ingredients list from the following recipe search result for "{name}".
            Return ONLY a JSON list of strings, e.g. ["1 lb shrimp", "2 tbsp butter"].
            
            Search Results: {search_results}
            """
            response = await llm.ainvoke([HumanMessage(content=extraction_prompt)])
            
            content = response.content.replace("```json", "").replace("```", "").strip()
            ingredients = json.loads(content)
            for ing in ingredients:
                new_raw_ingredients.append({
                    "original": ing,
                    "recipe": f"{name} (Web)"
                })
            messages.append(AIMessage(content=f"I couldn't find '{name}' in your Mealie recipes, so I found it on the web for you!"))
        except Exception as e:
            print(f"Error in web search for {name}: {e}")
            messages.append(AIMessage(content=f"I couldn't find '{name}' in Mealie or on the web."))

    # Combine with existing raw ingredients
    combined_ingredients = state.get("raw_ingredients", []) + new_raw_ingredients
    
    return {
        "raw_ingredients": combined_ingredients,
        "messages": messages
    }

async def filter_ingredients_node(state: AgentState) -> Dict[str, Any]:
    """
    Filters ingredients against pantry config.
    """
    raw_ingredients = state.get('raw_ingredients', [])
    pantry_config = load_pantry_config()
    bypass_staples = set(s.lower() for s in pantry_config.get('bypass_staples', []))
    
    pantry_items = []
    pending_cart = []
    
    for item in raw_ingredients:
        name = item['original'].lower()
        is_staple = any(staple in name for staple in bypass_staples)
        
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

async def execute_order_node(state: AgentState) -> Dict[str, Any]:
    """
    Adds approved items to Kroger cart.
    """
    approved_cart = state.get('approved_cart', [])
    order_results = []
    
    for item in approved_cart:
        query = item['original']
        search_res = await call_mcp_tool(KROGER_MCP_URL, "search_products", {"term": query, "limit": 1})
        if search_res and not search_res.isError:
            try:
                products = json.loads(search_res.content[0].text)
                if products:
                    product = products[0]
                    upc = product['upc']
                    
                    add_res = await call_mcp_tool(KROGER_MCP_URL, "add_items_to_cart", {"items": [{"upc": upc, "quantity": 1}]})
                    order_results.append({
                        "item": query,
                        "product": product['description'],
                        "status": "added" if (add_res and not add_res.isError) else "failed"
                    })
                else:
                    order_results.append({"item": query, "status": "not_found"})
            except Exception as e:
                order_results.append({"item": query, "status": "error", "error": str(e)})
        else:
            order_results.append({"item": query, "status": "search_failed"})
            
    return {
        "order_result": {"items": order_results},
        "messages": [AIMessage(content="I've processed your order request with Kroger. Check the summary for details!")]
    }