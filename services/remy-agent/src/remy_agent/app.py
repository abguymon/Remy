import streamlit as st
import os
import uuid
import asyncio
import json
import yaml
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from remy_agent.graph import get_workflow

# Config file paths
PANTRY_CONFIG_PATH = "pantry.yaml"
RECIPE_SOURCES_PATH = "recipe_sources.yaml"
USER_SETTINGS_PATH = "user_settings.yaml"


def load_yaml_config(path, default):
    """Load a YAML config file."""
    if os.path.exists(path):
        with open(path, "r") as f:
            return yaml.safe_load(f) or default
    return default


def save_yaml_config(path, data):
    """Save data to a YAML config file."""
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def load_user_settings():
    """Load user settings."""
    default = {
        "store": {"location_id": None, "name": None, "zip_code": ""},
        "fulfillment": "PICKUP"
    }
    return load_yaml_config(USER_SETTINGS_PATH, default)


def save_user_settings(settings):
    """Save user settings."""
    save_yaml_config(USER_SETTINGS_PATH, settings)

# Page config
st.set_page_config(page_title="Remy - AI Grocery Agent", layout="wide")

# Persistent Thread ID for LangGraph
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# Workflow definition (uncompiled)
workflow = get_workflow()
DB_PATH = "data/checkpoints.sqlite"
KROGER_MCP_URL = os.getenv("KROGER_MCP_URL", "http://kroger-mcp:8000/sse")

st.title("Remy: Your Personal Grocery Agent")

# Helper to run the graph asynchronously
async def run_agent(input_state=None, command="invoke"):
    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        app = workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["fetch_selected_recipes", "execute_order"]
        )
        config = {"configurable": {"thread_id": st.session_state.thread_id}}

        if command == "invoke":
            return await app.ainvoke(input_state, config=config)
        elif command == "get_state":
            return await app.aget_state(config)
        elif command == "update_state":
            return await app.aupdate_state(config, input_state)

# Load user settings
user_settings = load_user_settings()
store_settings = user_settings.get("store", {})
st.session_state.preferred_store_id = store_settings.get("location_id")
st.session_state.preferred_store = store_settings.get("name")
st.session_state.modality = user_settings.get("fulfillment", "PICKUP")

# Set preferred location in Kroger MCP on startup
if st.session_state.preferred_store_id and "kroger_store_set" not in st.session_state:
    async def init_store():
        try:
            async with sse_client(KROGER_MCP_URL) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.call_tool("set_preferred_location", {
                        "location_id": st.session_state.preferred_store_id
                    })
        except:
            pass
    asyncio.run(init_store())
    st.session_state.kroger_store_set = True

# --- Sidebar ---
with st.sidebar:
    # Show current settings
    st.header("Current Settings")
    if st.session_state.preferred_store:
        st.write(f"**Store:** {st.session_state.preferred_store}")
    else:
        st.warning("No store selected - configure in Settings below")
    st.write(f"**Fulfillment:** {st.session_state.modality}")

    st.divider()

    # Kroger Authentication
    if "auth_url" not in st.session_state:
        if st.button("Login to Kroger"):
            async def start_auth():
                try:
                    async with sse_client(KROGER_MCP_URL) as (read, write):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            res = await session.call_tool("start_authentication", {})
                            if res and not res.isError:
                                return json.loads(res.content[0].text)
                except Exception as e:
                    st.error(f"Error: {e}")
                return None

            auth_data = asyncio.run(start_auth())
            if auth_data and auth_data.get("auth_url"):
                st.session_state.auth_url = auth_data.get("auth_url")
                st.rerun()
    else:
        st.write("Complete Kroger login:")
        st.link_button("Authorize", st.session_state.auth_url)
        redirect_url = st.text_input("Paste redirect URL")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Complete"):
                async def finish_auth(url):
                    try:
                        async with sse_client(KROGER_MCP_URL) as (read, write):
                            async with ClientSession(read, write) as session:
                                await session.initialize()
                                res = await session.call_tool("complete_authentication", {"redirect_url": url})
                                if res and not res.isError:
                                    return json.loads(res.content[0].text)
                    except:
                        pass
                    return None

                res_data = asyncio.run(finish_auth(redirect_url))
                if res_data and res_data.get("success"):
                    st.success("Logged in!")
                    del st.session_state.auth_url
                    st.rerun()
                else:
                    st.error("Login failed")
        with col2:
            if st.button("Cancel"):
                del st.session_state.auth_url
                st.rerun()

    st.divider()

    # --- Settings Section ---
    with st.expander("Settings"):
        # Store Settings
        st.markdown("**Store Settings**")
        settings_zip = st.text_input("Zip Code", value=store_settings.get("zip_code", ""), key="settings_zip")

        if st.button("Search Stores"):
            async def fetch_stores():
                try:
                    async with sse_client(KROGER_MCP_URL) as (read, write):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            res = await session.call_tool("search_locations", {"zip_code": settings_zip})
                            if res and not res.isError:
                                data = json.loads(res.content[0].text)
                                return data.get("data", [])
                except Exception as e:
                    st.error(f"Error: {e}")
                return []

            with st.spinner("Searching..."):
                st.session_state.store_search_results = asyncio.run(fetch_stores())

        if "store_search_results" in st.session_state and st.session_state.store_search_results:
            stores = st.session_state.store_search_results
            store_options = {f"{s['name']} - {s['address']['street']}": s for s in stores}
            selected = st.selectbox("Select Store", list(store_options.keys()))

            if st.button("Save Store"):
                store = store_options[selected]
                user_settings["store"] = {
                    "location_id": store["location_id"],
                    "name": f"{store['name']} - {store['address']['street']}",
                    "zip_code": settings_zip
                }
                save_user_settings(user_settings)

                # Update Kroger MCP
                async def update_store():
                    try:
                        async with sse_client(KROGER_MCP_URL) as (read, write):
                            async with ClientSession(read, write) as session:
                                await session.initialize()
                                await session.call_tool("set_preferred_location", {"location_id": store["location_id"]})
                    except:
                        pass
                asyncio.run(update_store())

                st.success(f"Saved store: {store['name']}")
                del st.session_state.store_search_results
                st.rerun()

        # Fulfillment method
        fulfillment_options = ["PICKUP", "DELIVERY"]
        current_idx = fulfillment_options.index(user_settings.get("fulfillment", "PICKUP"))
        new_fulfillment = st.selectbox("Fulfillment Method", fulfillment_options, index=current_idx)
        if new_fulfillment != user_settings.get("fulfillment"):
            user_settings["fulfillment"] = new_fulfillment
            save_user_settings(user_settings)
            st.session_state.modality = new_fulfillment

        st.markdown("---")

        # Favorite Recipe Sources
        st.markdown("**Favorite Recipe Sites**")
        sources_config = load_yaml_config(RECIPE_SOURCES_PATH, {"favorite_sources": []})
        favorite_sources = sources_config.get("favorite_sources", [])

        for i, source in enumerate(favorite_sources):
            col_name, col_del = st.columns([4, 1])
            with col_name:
                st.text(f"{source.get('name', '')} ({source.get('domain', '')})")
            with col_del:
                if st.button("X", key=f"del_source_{i}"):
                    favorite_sources.pop(i)
                    sources_config["favorite_sources"] = favorite_sources
                    save_yaml_config(RECIPE_SOURCES_PATH, sources_config)
                    st.rerun()

        new_source_name = st.text_input("Site name", placeholder="e.g., Budget Bytes", key="new_source_name")
        new_source_domain = st.text_input("Domain", placeholder="e.g., budgetbytes.com", key="new_source_domain")
        if st.button("Add Site"):
            if new_source_name and new_source_domain:
                favorite_sources.append({"name": new_source_name, "domain": new_source_domain})
                sources_config["favorite_sources"] = favorite_sources
                save_yaml_config(RECIPE_SOURCES_PATH, sources_config)
                st.success(f"Added {new_source_name}")
                st.rerun()

        st.markdown("---")

        # Pantry Bypass Items
        st.markdown("**Pantry Items (auto-skipped)**")
        pantry_config = load_yaml_config(PANTRY_CONFIG_PATH, {"bypass_staples": []})
        bypass_staples = pantry_config.get("bypass_staples", [])

        pantry_text = st.text_area(
            "One item per line:",
            value="\n".join(bypass_staples),
            height=150,
            key="pantry_items_text"
        )

        if st.button("Save Pantry Items"):
            new_staples = [item.strip() for item in pantry_text.split("\n") if item.strip()]
            pantry_config["bypass_staples"] = new_staples
            save_yaml_config(PANTRY_CONFIG_PATH, pantry_config)
            st.success(f"Saved {len(new_staples)} pantry items")

# --- Main UI ---
# Get current state
state = asyncio.run(run_agent(command="get_state"))
recipe_options = []
selected_recipe_options = []
pending_cart = []
pantry_items = []
order_result = None

if state and state.values:
    recipe_options = state.values.get("recipe_options", [])
    selected_recipe_options = state.values.get("selected_recipe_options", [])
    pending_cart = state.values.get("pending_cart", [])
    pantry_items = state.values.get("pantry_items", [])
    order_result = state.values.get("order_result")

# Two-column layout
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Chat")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message("user" if isinstance(msg, HumanMessage) else "assistant"):
            st.markdown(msg.content)

    # Recipe Selection UI (in main chat area)
    if recipe_options and not selected_recipe_options and not pending_cart:
        with st.chat_message("assistant"):
            st.markdown("**Select a recipe to use:**")

            # Build options for radio button
            all_options = []
            option_labels = []

            # Mealie options first
            mealie_options = [r for r in recipe_options if r['source'] == 'mealie']
            web_options = [r for r in recipe_options if r['source'] == 'web']

            if mealie_options:
                st.markdown("**From Your Mealie Library:**")
                for option in mealie_options:
                    all_options.append(option)
                    option_labels.append(f"{option['name']}")
                    # Show description and link
                    st.markdown(f"- [{option['name']}]({option['url']}) - {option.get('description', '')[:100]}")

            if web_options:
                st.markdown("**From the Web:**")
                for option in web_options:
                    all_options.append(option)
                    option_labels.append(f"{option['name']}")
                    st.markdown(f"- [{option['name']}]({option['url']}) - {option.get('description', '')[:100]}")

            st.divider()

            # Radio selection
            if all_options:
                def format_option(i):
                    opt = all_options[i]
                    if opt['source'] == 'mealie':
                        return f"{opt['name']} (Mealie)"
                    else:
                        # Extract domain from URL
                        from urllib.parse import urlparse
                        domain = urlparse(opt['url']).netloc.replace('www.', '')
                        return f"{opt['name']} ({domain})"

                selected_index = st.radio(
                    "Choose a recipe:",
                    range(len(all_options)),
                    format_func=format_option,
                    index=0
                )

                if st.button("Use This Recipe"):
                    selected_recipe = all_options[selected_index]
                    asyncio.run(run_agent({
                        "selected_recipe_options": [selected_recipe]
                    }, "update_state"))

                    with st.spinner("Fetching recipe details..."):
                        asyncio.run(run_agent(None, "invoke"))
                        st.rerun()

    # Chat input
    if prompt := st.chat_input("What would you like to cook?"):
        st.session_state.messages.append(HumanMessage(content=prompt))
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Remy is thinking..."):
                input_state = {"messages": st.session_state.messages}
                result = asyncio.run(run_agent(input_state, "invoke"))

                new_messages = result.get("messages", [])
                if len(new_messages) > len(st.session_state.messages):
                    for i in range(len(st.session_state.messages), len(new_messages)):
                        msg = new_messages[i]
                        if isinstance(msg, AIMessage):
                            st.markdown(msg.content)
                            st.session_state.messages.append(msg)

                # Trigger rerun to show recipe selection
                if result.get("recipe_options"):
                    st.rerun()

with col2:
    st.subheader("Cart")

    approved_items = []

    # Cart approval (when we have pending items)
    if pending_cart:
        st.write("**Items to order:**")
        for i, item in enumerate(pending_cart):
            checked = st.checkbox(item['original'], value=True, key=f"item_{i}")
            if checked:
                approved_items.append(item)

    # Pantry items - can be added to cart if needed
    if pantry_items:
        with st.expander("Pantry Items (check to order anyway)", expanded=False):
            for i, item in enumerate(pantry_items):
                checked = st.checkbox(item['original'], value=False, key=f"pantry_{i}")
                if checked:
                    approved_items.append(item)

    # Add to cart button
    if pending_cart or pantry_items:
        if st.button("Add to Cart", disabled=len(approved_items) == 0):
            asyncio.run(run_agent({
                "approved_cart": approved_items,
                "fulfillment_method": st.session_state.get("modality", "PICKUP"),
                "preferred_store_id": st.session_state.get("preferred_store_id")
            }, "update_state"))

            with st.spinner("Adding items to cart..."):
                asyncio.run(run_agent(None, "invoke"))
                st.success("Items added to Kroger Cart!")
                st.markdown("[View your Kroger Cart](https://www.kroger.com/cart)")
                st.rerun()

    # Order result display
    if order_result:
        st.subheader("Order Summary")
        st.markdown("[Open Kroger Cart](https://www.kroger.com/cart)")
        for item in order_result.get("items", []):
            qty = item.get('quantity', 1)
            qty_str = f"x{qty} " if qty > 1 else ""

            if item['status'] == "added":
                icon = "+"
            elif item['status'] == "unavailable":
                icon = "?"
            else:
                icon = "x"

            product_info = item.get('product', item['status'])
            err = f" - {item['error']}" if 'error' in item else ""
            st.write(f"{icon} {qty_str}{item['item']} -> {product_info}{err}")

    # Empty state
    if not pending_cart and not order_result and not pantry_items:
        st.write("Cart items will appear here after you select a recipe.")
