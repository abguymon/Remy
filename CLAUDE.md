# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Authoritative docs

The specification and build history live in three root docs; the PRD
**overrides code** where they disagree:

- **`PRD.md`** — product requirements & system spec (the source of truth).
- **`DESIGN_BRIEF.md`** — visual/interaction spec for the frontend.
- **`V2_PLAN.md`** — the task breakdown (T0…T10) and its status notes; a record
  of how the current codebase was built. Appendix A documents the ported prompt
  heuristics.

## Project overview

Remy is a self-hosted, single-household AI agent (multi-user with an admin
role) that turns a list of meals into a filled Kroger (Fred Meyer) pickup cart:
discover recipes → pick → consolidated shopping list → match to real Kroger
products → add to the real cart, handing off to the store banner's site
(fredmeyer.com etc., `kroger/banners.py`) for checkout. Selected recipes are
saved to a local cookbook, which also imports from URLs and from photos/PDFs
(vision extraction).

## v2 architecture (PRD §4)

Modular-monolith backend + a thin MCP facade. **Two app services** plus a
self-hosted search container:

| Service  | Port | Purpose |
|----------|------|---------|
| remy-web | 3000 | React 18 + TypeScript + Vite + Tailwind (nginx in prod) |
| remy-api | 8080 | FastAPI: auth, planner state machine, recipes, kroger, llm, websearch, and a mounted MCP facade |
| searxng  | (internal) | Self-hosted metasearch (default `SEARCH_PROVIDER=searxng`); remy-net only, no host ports; config in `searxng/settings.yml` |

Kroger and recipe functionality are **internal Python modules** of `remy-api`,
not separate containers. No Mealie, no MCP sidecars, no LangGraph (the plan flow
is a plain DB-persisted state machine). The MCP facade (FastMCP mounted into
FastAPI, flag `MCP_FACADE_ENABLED`, default on) is a first-class second UI that
calls the same modules — never divergent logic.

- **MCP facade** (`remy_api.mcp_facade`, T6): streamable-HTTP endpoint at
  **`/mcp`** (via the reverse proxy: `https://<host>/api/mcp`). Auth = a
  per-user Remy **API token** (`remy_…`, generated in Settings) sent as
  `Authorization: Bearer …`; JWTs are rejected. Tools mirror the pipeline gates
  (`find_recipes` → `select_recipes` → `build_shopping_list`/`edit_shopping_list`
  → `match_products`/`swap_product` → `execute_cart`, plus cookbook/settings and
  `plan_status`). The plan/cart **draft-id chain** is the write-safety structure:
  `execute_cart` accepts only the current `cart_draft_id`.

- **Access:** frontend http://localhost:3000, API http://localhost:8080.
- **API proxy:** remy-web proxies `/api/*` → remy-api (vite dev proxy locally,
  nginx `location /api/` in prod; the `/api` prefix is stripped).
- **Data:** SQLite via async SQLAlchemy (Postgres-portable) + FTS5 for recipe
  search; images and the DB live on the shared `./data` volume.

## Build, run, test

```bash
# First time only: create the docker networks
docker network create remy-net
docker network create t2_proxy   # Traefik reverse-proxy network

# Configure
cp .env.template .env            # fill in secrets (see PRD §8)

# Build & run the two-service stack
docker compose build
docker compose up -d
curl localhost:8080/health       # {"status":"ok",...}
# web on http://localhost:3000

docker compose logs -f [remy-api|remy-web]
docker compose down
```

### remy-api (local dev)

```bash
cd services/remy-api
uv sync --extra dev              # or: pip install -e ".[dev]"
export JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
export ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
uvicorn remy_api.main:app --host 0.0.0.0 --port 8080 --reload

ruff check src tests && ruff format --check src tests
pytest
```

`JWT_SECRET` and `ENCRYPTION_KEY` are **required** — the API refuses to boot if
either is missing, empty, or a placeholder (fail-closed, PRD §9.5).

### remy-web (local dev)

```bash
cd services/remy-web
npm install
npm run dev                      # Vite dev server on :3000, proxies /api → :8080
npm run build                    # type-check + production build
```

## Configuration (PRD §8)

Copy `.env.template` → `.env`:
`JWT_SECRET`, `ENCRYPTION_KEY` (Fernet), `KROGER_CLIENT_ID`/`SECRET`,
`KROGER_REDIRECT_URI`, `LLM_PROVIDER`/`LLM_MODEL` + provider key,
`SEARCH_PROVIDER` (`searxng` default — needs `SEARXNG_URL` + `SEARXNG_SECRET`;
`brave` needs `SEARCH_API_KEY`; `llm` uses the LLM key), `MCP_FACADE_ENABLED`,
`WEB_APP_URL` (empty in prod; web origin in split-origin dev).
Mini-class models suffice: `openai/gpt-4o-mini` passes the full eval suite.

Seed configs at the repo root: `pantry.yaml` (pantry-staple defaults, FR-11) and
`recipe_sources.yaml` (favorite recipe sites, FR-24).

## Conventions

- **No silent failures** (PRD §9.1): every integration call succeeds, raises a
  typed error surfaced to the API, or returns an explicit degraded-result
  marker. Never swallow errors into empty results.
- **Structured LLM outputs everywhere** (PRD §7.1): Pydantic-validated
  tool-use/JSON-schema responses with one retry; no regex/fence-stripping of
  prose. Prompts live in the prompt library, not inline.
- **Bounded async concurrency** for all fan-out work (semaphore ~5–8).
- **Honest cart semantics:** the Kroger public API is add-only (no read, remove,
  or checkout). Any in-app cart is a local shadow record — label it as such.
- **Prompt changes require eval runs**: prompts live in
  `remy_api/prompts/` (versioned; bump `VERSION` on changes). Run the live
  evals with an LLM key: `pytest -m prompts` (offline suite excludes them).
  New prompt behaviors and every real-world bug fix get pinned as fixture
  cases in `tests/prompts/` so they cannot regress.
- Python 3.12+, ruff (line length 120), pytest. Backend package: `remy_api`.
