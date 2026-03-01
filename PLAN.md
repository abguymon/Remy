# Remy Improvement Plan

## Status Legend
- [x] Completed
- [~] Simplified / Rolled back (unnecessary for small personal project)
- [-] Deferred

---

## P0 - Critical Bugs & Security

### 1. Fix NoneType crash in remy-api cart search
- **File**: `remy-api/src/remy_api/routers/cart.py`
- **Status**: [x] Fixed - added explicit type checks for list/dict/other

### 2. JWT_SECRET validation
- **File**: `remy-api/src/remy_api/main.py`
- **Status**: [~] Simplified - warns on default value at startup, no entropy/length requirements

### 3. Fix broken pyproject.toml entry point in remy-agent
- **File**: `remy-agent/pyproject.toml`
- **Status**: [x] Removed broken [project.scripts] section (Streamlit app, no CLI entry)

### 4. Add Docker VOLUME to kroger-mcp Dockerfile
- **File**: `kroger-mcp/Dockerfile`
- **Status**: [x] Added VOLUME ["/app/data"] to kroger-mcp, remy-api, remy-agent

### 5. Pin dependency versions across all services
- **Files**: All `pyproject.toml` files
- **Status**: [x] Added upper bounds (>=X.Y.Z,<X+1.0.0) to all 4 services

### 6. ~~Add rate limiting to remy-api~~
- **Status**: [~] Removed - unnecessary for small trusted user group behind auth

### 7. ~~Restrict invite code creation to admins~~
- **Status**: [~] Removed admin role system entirely - all authenticated users can create invite codes

---

## P1 - Multi-Tenant Completion

### 8. Complete kroger-mcp multi-tenant support
- **File**: `kroger-mcp/src/kroger_mcp/tools/profile_tools.py`
- **Status**: [x] Added user_id to all profile/auth tools

### 9. Complete mealie-mcp multi-tenant support
- **Files**: `mealie-mcp-server/src/tools/recipe_tools.py`, `mealplan_tools.py`
- **Status**: [x] All 11 tools now accept mealie_api_key parameter

### 10. Add authentication between remy-api and MCP servers
- **Status**: [-] Deferred - requires architecture decision (shared secret or mTLS)

### 11. Validate user_id format in kroger-mcp
- **File**: `kroger-mcp/src/kroger_mcp/tools/shared.py`
- **Status**: [x] Added validate_user_id() with regex + length check, prevents path traversal

---

## P2 - Error Handling & Resilience

### 12. Implement MCP connection pooling
- **Status**: [-] Deferred - SSE protocol creates new connections per-call by design

### 13. Add MCP call timeouts
- **Status**: [x] Added 30s asyncio.wait_for() timeout to both remy-agent and remy-api

### 14. Add MCP retry logic with backoff
- **Status**: [x] Added 2-retry loop with exponential backoff for connection errors

### 15. ~~Distinguish MCP error types~~
- **Status**: [~] Simplified - uses plain exceptions with logging instead of custom exception hierarchy

### 16. ~~Add startup validation for all services~~
- **Status**: [~] Simplified - just warns on default JWT secret, removed strict validation for API keys and URLs

### 17. Implement database migrations (Alembic)
- **Status**: [-] Deferred - complex, low ROI for POC stage

---

## P3 - Frontend Improvements

### 18. ~~Implement JWT refresh token flow~~
- **Status**: [~] Removed - using 7-day JWTs instead. Simple 401 → logout flow

### 19. Replace unknown types with proper interfaces
- **Status**: [x] Created src/types/api.ts with all interfaces, updated client + all pages

### 20. Add error state display to all pages
- **Status**: [x] Home, Cart, Settings all show red error banner on query failure

### 21. Add 404 catch-all route
- **Status**: [x] NotFound component + catch-all route

### 22. Add nginx security headers
- **Status**: [x] Added X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy

### 23. Make nginx backend URL configurable
- **Status**: [-] Deferred - Docker networking handles this adequately

### 24. Add mobile responsive sidebar
- **Status**: [-] Deferred - UI polish, lower priority

### 25. Use npm ci in remy-web Dockerfile
- **Status**: [x] Changed to npm ci

---

## P4 - Agent/Workflow Improvements

### 26. Deduplicate recipe search results
- **Status**: [x] Added URL + name deduplication after search aggregation

### 27. Split oversized LangGraph nodes
- **Status**: [-] Deferred - refactoring risk for POC

### 28. Add message trimming to agent state
- **Status**: [x] Custom reducer trims to 50 messages max

### 29. Batch ingredient-to-product extraction
- **Status**: [-] Deferred - needs testing with real data

### 30. Implement WebSocket streaming
- **Status**: [-] Deferred - Phase 4 in tasks.md

---

## P5 - Missing Features

### 31. Add Mealie shopping list integration
- **Status**: [-] Deferred

### 32. Add recipe deletion tool to mealie-mcp
- **Status**: [x] Added delete_recipe method + MCP tool

### 33. Add account deletion endpoint to remy-api
- **Status**: [x] Added DELETE /users/me with cascade cleanup

### 34. Add token revocation/blacklist to remy-api
- **Status**: [-] Deferred - needs Redis or similar

### 35. Implement dietary restrictions filtering
- **Status**: [-] Deferred

---

## P6 - DevOps & Code Quality

### 36. Add HEALTHCHECK to all Dockerfiles
- **Status**: [x] Added to all 5 Dockerfiles (curl/wget based)

### 37. Run containers as non-root
- **Status**: [x] Added appuser to all Python Dockerfiles, nginx already non-root

### 38. Replace print() with logging module
- **Status**: [x] Replaced 24 print() calls in nodes.py with logger.debug/info/warning/error

### 39. Add test coverage for remy-api
- **Status**: [-] Deferred - large effort

### 40. Add test coverage for error conditions in remy-agent
- **Status**: [-] Deferred

### 41. Remove dead code
- **Status**: [x] Removed: kroger-mcp/server.py, kroger-mcp/run_server.py, deprecated state field, unused functions

### 42. Fix deprecated datetime.utcnow() calls
- **Status**: [x] Replaced all 9 occurrences with datetime.now(timezone.utc)

### 43. Update CLAUDE.md to reflect new architecture
- **Status**: [x] Rewritten with all 5 services, React frontend, FastAPI backend, multi-tenant info

---

## Simplification Pass

Removed over-engineering that wasn't needed for a small friends-and-family deployment:

| Removed | Reason |
|---------|--------|
| **slowapi rate limiting** | Unnecessary behind auth with ~5 users |
| **Admin role system** (`is_admin`, `get_admin_user`) | Everyone is trusted |
| **Invite code email restrictions & usage tracking** | Simplified to just code + used boolean |
| **Refresh tokens & /auth/refresh endpoint** | 7-day JWTs with simple re-login |
| **Dual login endpoints** (form + JSON) | Kept JSON only, removed form-based |
| **MCP exception hierarchy** (`mcp_errors.py`) | Plain exceptions with logging |
| **Strict startup validation** (API key, URL parsing, JWT entropy) | Just a warning on default JWT secret |
| **`python-multipart` dependency** | No longer needed without form-based login |

**Kept** (good practice even for small projects): MCP timeouts/retries, health checks, non-root containers, message trimming, user_id validation, dependency pinning.

---

## Summary

**Completed**: 24 tasks
**Simplified/Rolled back**: 6 tasks (over-engineering for small project)
**Deferred**: 13 tasks
