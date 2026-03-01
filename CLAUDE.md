# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Remy is a self-hosted, multi-tenant AI agent that automates grocery planning and ordering. It uses a React frontend, FastAPI backend with JWT auth, LangGraph for workflow orchestration, and MCP (Model Context Protocol) servers for external service integration.

## Build and Run Commands

```bash
# Create Docker network (first time only)
docker network create remy-net

# Build and run all services (default profile: remy-web, remy-api, kroger-mcp, mealie-mcp-server, mealie)
docker-compose build
docker-compose up -d

# Run the legacy Streamlit UI (remy-agent) instead of / alongside the new stack
docker-compose --profile legacy up remy-agent

# View logs
docker-compose logs -f [service-name]
```

### Individual Service Development

Each service uses `uv` or `pip` with hatchling:

```bash
# Install dependencies for a service
cd services/remy-api
uv sync  # or pip install -e .

# Run remy-api locally (requires MCP servers running)
uvicorn remy_api.main:app --host 0.0.0.0 --port 8080

# Run remy-web locally
cd services/remy-web
npm install
npm run dev  # Vite dev server on port 5173

# Run kroger-mcp locally
cd services/kroger-mcp
python docker_entrypoint.py

# Run mealie-mcp-server locally
cd services/mealie-mcp-server
python docker_entrypoint.py

# Legacy: Run remy-agent (Streamlit) locally
cd services/remy-agent
streamlit run src/remy_agent/app.py
```

## Architecture

### Services

| Service | Port | Purpose |
|---------|------|---------|
| remy-web | 3000 | React + TypeScript + Vite frontend (login, recipe search, cart, settings) |
| remy-api | 8080 | FastAPI backend (JWT auth, SQLAlchemy, LangGraph orchestrator) |
| kroger-mcp | 8001 | FastMCP server for Kroger shopping API |
| mealie-mcp-server | 8000 | MCP server for Mealie recipe database |
| mealie | 9925 | Recipe database (external dependency) |
| remy-agent | 8501 | **Legacy** Streamlit UI + LangGraph orchestrator (only runs with `--profile legacy`) |

### Access URLs

- **Frontend**: http://localhost:3000
- **API**: http://localhost:8080
- **Mealie**: http://localhost:9925

### Service Communication

All MCP servers use SSE (Server-Sent Events) transport. In Docker:
- Mealie MCP: `http://mealie-mcp-server:8000/sse`
- Kroger MCP: `http://kroger-mcp:8000/sse`

The React frontend proxies API calls through `/api/*` to `remy-api:8080`.

### LangGraph Workflow (remy-api / remy-agent)

The workflow is defined in `services/remy-agent/src/remy_agent/graph.py` (legacy) and replicated in `services/remy-api/`:

```
START → search_recipes → [interrupt for user selection] → fetch_selected_recipes → filter_ingredients → [interrupt for approval] → execute_order → END
```

**State Definition** (`state.py`):
- `messages`: Conversation history
- `target_recipe_names`: Extracted recipe names from user input
- `recipe_options`: Mealie + web search results for user selection
- `selected_recipe_options`: User-selected recipes
- `fetched_recipes`: Detailed recipe data
- `raw_ingredients`: Extracted ingredients from recipes
- `pending_cart`: Filtered ingredients for approval
- `pantry_items`: Ingredients matched to pantry bypass list
- `approved_cart`: User-approved items
- `fulfillment_method`: "PICKUP" or "DELIVERY"
- `preferred_store_id`: Kroger store location ID
- `order_result`: Final Kroger API response

**Node Implementations** (`nodes.py`):
- `search_recipes_node`: Extract recipe names via LLM, search Mealie + web in parallel
- `fetch_selected_recipes_node`: Fetch detailed recipe data, import web recipes into Mealie
- `filter_ingredients_node`: Filter against pantry bypass items
- `execute_order_node`: Batch extract product names, add approved items to Kroger cart in parallel

### Multi-Tenant Isolation (remy-api)

Each user has isolated:
- **SQLite checkpoint database**: `data/checkpoints/{user_id}.sqlite`
- **User settings in database**: pantry items, store preferences
- **Kroger tokens** (via user_id parameter to MCP)
- **Mealie API key** (stored in user settings)

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
- `KROGER_REDIRECT_URI`: OAuth redirect (default: `http://localhost:8080/kroger/callback`)
- `MEALIE_BASE_URL`, `MEALIE_API_KEY`: Mealie instance connection
- `OPENAI_API_KEY`: For GPT-4o LLM calls
- `JWT_SECRET`: Secret key for JWT token signing
- `INITIAL_INVITE_CODE`: Bootstrap invite code for the first user registration
- `ENCRYPTION_KEY`: For encrypting sensitive data at rest

### Pantry Bypass List

`services/remy-agent/pantry.yaml` contains common staples (salt, pepper, olive oil, etc.) that are automatically filtered from cart additions. In the new architecture, pantry items are stored per-user in the database.

## Key Implementation Details

- LLM: GPT-4o with temperature=0 for deterministic outputs
- MCP client uses `mcp.client.sse.sse_client` and `mcp.client.session.ClientSession`
- Kroger auth tokens stored per-user with automatic refresh
- Local cart tracking in JSON files (not synced to Kroger until checkout)
- Frontend: React 18 + TypeScript + Vite + Tailwind CSS
- Backend: FastAPI + SQLAlchemy (async) + JWT authentication
- Database: SQLite via aiosqlite (users, settings, kroger tokens, invite codes)
