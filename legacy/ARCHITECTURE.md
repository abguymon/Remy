# Remy Architecture

## Overview

Remy is a multi-tenant AI grocery planning agent with a React frontend and FastAPI backend. It uses LangGraph for workflow orchestration and MCP (Model Context Protocol) servers for external service integration.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    React Frontend (remy-web)                    │
│                    http://localhost:3000                        │
│  - Login/Register with JWT auth                                 │
│  - Recipe search and selection                                  │
│  - Cart management                                              │
│  - Settings (Kroger, Mealie, pantry)                           │
└─────────────────────────┬───────────────────────────────────────┘
                          │ /api/* → proxy
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (remy-api)                    │
│                   http://localhost:8080                         │
│  - JWT Authentication (/auth/*)                                 │
│  - User Management (/users/*)                                   │
│  - Recipe Planning (/recipes/*) - LangGraph workflow            │
│  - Cart Operations (/cart/*)                                    │
│  - Kroger OAuth (/kroger/*)                                     │
└───────────┬─────────────────────────────────┬───────────────────┘
            │ SSE                             │ SSE
            ▼                                 ▼
┌───────────────────────┐       ┌───────────────────────┐
│    Kroger MCP         │       │    Mealie MCP         │
│  http://localhost:8001│       │  http://localhost:8000│
│  - Product search     │       │  - Recipe search      │
│  - Cart management    │       │  - Recipe details     │
│  - Store locations    │       │  - Recipe import      │
│  - OAuth tokens       │       │                       │
└───────────────────────┘       └───────────┬───────────┘
                                            │
                                            ▼
                                ┌───────────────────────┐
                                │       Mealie          │
                                │  http://localhost:9925│
                                │  - Recipe database    │
                                │  - Multi-user support │
                                └───────────────────────┘
```

## Services

### remy-web (React Frontend)
- **Port**: 3000
- **Technology**: React 18, TypeScript, Vite, Tailwind CSS
- **Features**:
  - JWT-based authentication
  - Recipe search and selection UI
  - Shopping cart management
  - User settings and account linking

### remy-api (FastAPI Backend)
- **Port**: 8080
- **Technology**: FastAPI, SQLAlchemy, LangGraph
- **Features**:
  - Multi-tenant user authentication
  - LangGraph workflow orchestration
  - Per-user checkpoint storage
  - API for all frontend operations

### kroger-mcp (Kroger MCP Server)
- **Port**: 8001
- **Technology**: Python, FastMCP
- **Features**:
  - Product search
  - Cart management (local tracking)
  - Store location search
  - Per-user OAuth token storage

### mealie-mcp (Mealie MCP Server)
- **Port**: 8000
- **Technology**: Python, FastMCP
- **Features**:
  - Recipe search and retrieval
  - Recipe import from URLs
  - Per-user API key support

### mealie (Recipe Database)
- **Port**: 9925
- **Technology**: Mealie (external)
- **Features**:
  - Recipe storage
  - Multi-user support
  - Recipe scraping

## Data Flow

### Authentication Flow
```
1. User registers with invite code → /auth/register
2. User logs in → /auth/login → JWT token
3. JWT included in Authorization header for all requests
4. Token validated on each API call
```

### Recipe Planning Flow
```
1. User searches: "chicken tikka masala" → /recipes/plan
2. LangGraph workflow starts:
   a. Extract recipe names via LLM
   b. Search Mealie for matching recipes
   c. Return recipe options to user
3. User selects recipes → /recipes/plan/select
4. Workflow continues:
   a. Fetch detailed recipe data
   b. Extract ingredients
   c. Filter against pantry items
   d. Return pending cart
5. User approves cart → /recipes/plan/approve
6. Workflow completes:
   a. Add items to Kroger cart
   b. Return confirmation
```

### Multi-Tenant Isolation

Each user has isolated:
- **SQLite checkpoint database**: `data/checkpoints/{user_id}.sqlite`
- **User settings in database**: pantry items, store preferences
- **Kroger tokens** (via user_id parameter to MCP)
- **Mealie API key** (stored in user settings)

## Database Schema

```sql
-- Users
users (id, username, email, password_hash, is_active, created_at)

-- User settings
user_settings (user_id, pantry_items, recipe_sources, store_location_id,
               store_name, zip_code, fulfillment_method, mealie_api_key)

-- Kroger tokens
kroger_tokens (user_id, access_token, refresh_token, expires_at)

-- Invite codes
invite_codes (code, email, used_by, created_at, used_at)
```

## Environment Variables

```bash
# Required
OPENAI_API_KEY=          # For LLM calls
JWT_SECRET=              # For JWT signing
KROGER_CLIENT_ID=        # Kroger API
KROGER_CLIENT_SECRET=    # Kroger API
MEALIE_BASE_URL=         # Mealie instance
MEALIE_API_KEY=          # Default Mealie API key

# Optional
INITIAL_INVITE_CODE=     # Bootstrap first user
```

## Deployment

### Development
```bash
# Start all services
docker-compose up -d

# Access
# - Frontend: http://localhost:3000
# - API: http://localhost:8080
# - Mealie: http://localhost:9925
```

### Production Considerations
1. Use strong JWT_SECRET
2. Remove INITIAL_INVITE_CODE after first user
3. Configure HTTPS via reverse proxy
4. Set up proper database backups
5. Configure Kroger redirect URI for production domain

## Legacy Support

The original Streamlit UI (remy-agent) is preserved with the `legacy` profile:
```bash
docker-compose --profile legacy up remy-agent
```

This allows gradual migration from the old UI to the new React frontend.
