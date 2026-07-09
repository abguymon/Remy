# Multi-Tenant Remy Implementation Tasks

## Overview
Replacing Streamlit UI with React + FastAPI for multi-tenant support.

---

## Phase 1: FastAPI Backend Foundation
- [x] Create `services/remy-api/` directory structure
- [x] Set up pyproject.toml with dependencies
- [x] Create FastAPI app skeleton (main.py)
- [x] Create Dockerfile
- [x] Test: API starts and returns health check

## Phase 2: Authentication System
- [x] Create database.py with SQLAlchemy models (users, settings, tokens, invite_codes)
- [x] Create auth.py with JWT utilities
- [x] Create Pydantic models (models.py)
- [x] Create /auth router (login, register, refresh)
- [x] Create /users router (me, settings)
- [x] Test: Can register, login, get JWT, call /users/me

## Phase 3: Migrate LangGraph to FastAPI
- [x] Copy and adapt graph.py → services/langgraph.py
- [x] Copy and adapt nodes.py → services/mcp_client.py
- [x] Copy and adapt state.py → models
- [x] Add user_id to workflow state
- [x] Create per-user checkpoint paths
- [x] Create /recipes router (search, plan)
- [x] Create /cart router
- [x] Create /kroger router (OAuth, stores)
- [ ] Test: Can trigger workflow via API (requires MCP servers)

## Phase 4: WebSocket Streaming
- [ ] Create websocket.py handler
- [ ] Implement streaming events from LangGraph
- [ ] Add JWT auth for WebSocket connections
- [ ] Test: Can connect and receive streaming events
(Deferred - will add after React frontend)

## Phase 5: React Frontend
- [x] Create `services/remy-web/` with Vite + React + TypeScript
- [x] Set up Tailwind CSS
- [x] Set up React Router
- [x] Set up TanStack Query
- [x] Create API client with JWT interceptor
- [x] Create Login page
- [x] Create Register page
- [x] Create Home page (recipe search + chat)
- [x] Create Cart page
- [x] Create Settings page
- [ ] Create WebSocket hook for streaming (deferred)
- [x] Create Dockerfile (nginx)
- [x] Test: Frontend builds successfully

## Phase 6: Update kroger-mcp for Multi-Tenant
- [ ] Add get_user_data_dir() helper to shared.py
- [ ] Update auth.py for per-user token storage
- [ ] Update cart_tools.py with user_id parameter
- [ ] Update location_tools.py with user_id parameter
- [ ] Update all tool registrations to accept user_id
- [ ] Test: Two users have separate carts/tokens

## Phase 7: Update mealie-mcp for Multi-Tenant
- [ ] Add mealie_api_key parameter to tools
- [ ] Create per-request MealieClient
- [ ] Test: Different API keys return different recipes

## Phase 8: Docker & Deployment
- [x] Update docker-compose.yml with remy-api and remy-web
- [x] Add JWT_SECRET to .env.template
- [ ] Create migration script for existing data
- [ ] Test: Full docker-compose up works
- [x] Document architecture in ARCHITECTURE.md

## Phase 9: Documentation & Cleanup
- [ ] Update CLAUDE.md with new architecture
- [ ] Create user onboarding guide
- [ ] Final end-to-end testing
- [ ] (Optional) Remove remy-agent service after migration

---

## Progress Log

### 2026-01-31
- Created checkpoint tag: v1.0-streamlit
- Phase 1: Created FastAPI backend foundation (remy-api service)
- Phase 2: Implemented JWT authentication with bcrypt password hashing
- Phase 3: Migrated LangGraph workflow to FastAPI with per-user checkpoints
- Phase 5: Created React frontend with login, register, home, cart, settings pages
- Phase 8: Updated docker-compose.yml with new services
- Phase 8: Created ARCHITECTURE.md documentation
- Phase 8: Docker images build successfully for remy-api and remy-web

### Remaining Work
- Phase 4: WebSocket streaming (deferred for now)
- Phase 6: Update kroger-mcp for multi-tenant (user_id parameter)
- Phase 7: Update mealie-mcp for multi-tenant (API key parameter)
- Phase 9: End-to-end testing and cleanup
