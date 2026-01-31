# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Remy is a self-hosted AI agent that automates grocery planning and ordering. It uses LangGraph for workflow orchestration, Model Context Protocol (MCP) for service abstraction, and Streamlit for the frontend UI.

## Build and Run Commands

```bash
# Create Docker network (first time only)
docker network create remy-net

# Build all services
docker-compose build

# Run all services
docker-compose up -d

# Verify MCP servers are working
python verify_tools.py

# View logs
docker-compose logs -f [service-name]
```

### Individual Service Development

Each service uses `uv` or `pip` with hatchling:

```bash
# Install dependencies for a service
cd services/remy-agent
uv sync  # or pip install -e .

# Run remy-agent locally (requires MCP servers running)
streamlit run src/remy_agent/app.py

# Run kroger-mcp locally
cd services/kroger-mcp
python docker_entrypoint.py

# Run mealie-mcp-server locally
cd services/mealie-mcp-server
python docker_entrypoint.py
```

## Architecture

### Services

| Service | Port | Purpose |
|---------|------|---------|
| remy-agent | 8501 | Streamlit UI + LangGraph orchestrator |
| kroger-mcp | 8001 | FastMCP server for Kroger shopping API |
| mealie-mcp-server | 8000 | MCP server for Mealie recipe database |
| mealie | 9925 | Recipe database (external dependency) |

### Service Communication

All MCP servers use SSE (Server-Sent Events) transport. In Docker:
- Mealie MCP: `http://mealie-mcp-server:8000/sse`
- Kroger MCP: `http://kroger-mcp:8000/sse`

### LangGraph Workflow (remy-agent)

The workflow is defined in `services/remy-agent/src/remy_agent/graph.py`:

```
START → fetch_recipes_node → [web_search_node if needed] → filter_ingredients_node → [user approval] → execute_order_node → END
```

**State Definition** (`state.py`):
- `messages`: Conversation history
- `target_recipe_names`: Extracted recipe names from user input
- `fetched_recipes`: Recipes found in Mealie
- `not_found_recipes`: Recipes requiring web search
- `pending_cart`: Filtered ingredients for approval
- `approved_cart`: User-approved items
- `fulfillment_method`: "PICKUP" or "DELIVERY"
- `order_result`: Final Kroger API response

**Node Implementations** (`nodes.py`):
- `fetch_recipes_node`: Extract recipe names via LLM, fetch from Mealie
- `web_search_node`: DuckDuckGo search for missing recipes
- `filter_ingredients_node`: Filter against pantry.yaml items
- `execute_order_node`: Add approved items to Kroger cart

State persists to SQLite (`data/checkpoints.sqlite`) allowing workflow resume.

### Kroger MCP Tools

Located in `services/kroger-mcp/src/kroger_mcp/tools/`:
- `location_tools.py`: Store search, set preferred location
- `product_tools.py`: Product search by term or ID
- `cart_tools.py`: Add/remove items, view cart (tracked locally in kroger_cart.json)
- `auth.py`: OAuth2 token handling with refresh

### Mealie MCP Tools

Located in `services/mealie-mcp-server/src/tools/`:
- `recipe_tools.py`: Recipe fetch and search
- `mealplan_tools.py`: Meal plan operations

## Configuration

### Environment Variables

Copy `.env.template` to `.env` and configure:
- `KROGER_CLIENT_ID`, `KROGER_CLIENT_SECRET`: Kroger API credentials
- `MEALIE_BASE_URL`, `MEALIE_API_KEY`: Mealie instance connection
- `OPENAI_API_KEY`: For GPT-4o LLM calls

### Pantry Bypass List

`services/remy-agent/pantry.yaml` contains common staples (salt, pepper, olive oil, etc.) that are automatically filtered from cart additions.

## Key Implementation Details

- LLM: GPT-4o with temperature=0 for deterministic outputs
- MCP client uses `mcp.client.sse.sse_client` and `mcp.client.session.ClientSession`
- Kroger auth tokens stored in memory with automatic refresh
- Local cart tracking in JSON files (not synced to Kroger until checkout)
- Streamlit sidebar provides fulfillment method and store selection
