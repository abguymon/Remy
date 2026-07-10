# Remy

Remy is a self-hosted AI agent that turns a list of meals into a filled Kroger
(Fred Meyer) grocery cart. You tell Remy what you want to cook this week; it
finds ~5 recipe candidates per meal from the web and your own saved collection,
you pick one per meal, Remy builds a consolidated shopping list (merging
duplicate ingredients and skipping pantry staples), you review and edit it, and
Remy matches each item to the best real product at your preferred store and adds
them to your Kroger cart for pickup — leaving the final checkout to you on
your store's own site (fredmeyer.com, qfc.com, … — Remy links the right banner
for your store). Selected recipes are saved to a personal cookbook you can also
add to by pasting a URL or photographing a cookbook page / uploading a PDF.
It runs as a single household deployment behind your reverse proxy with
admin-managed accounts for the household; all data stays local except calls to
the Kroger, search, and LLM providers.

## Architecture

Two deployable services plus a mounted agent interface:

| Service    | Port | Purpose |
|------------|------|---------|
| `remy-web` | 3000 | React 18 + TypeScript + Vite + Tailwind SPA (served by nginx in prod). Proxies `/api/*` → `remy-api`. |
| `remy-api` | 8080 | FastAPI backend: JWT auth, the planner state machine, and the `recipes`, `kroger`, `llm`, and `websearch` internal modules. Also mounts the **MCP facade** at `/mcp`. |

Kroger and recipe functionality are **internal Python modules** of `remy-api`,
not separate containers — there is no Mealie service, no MCP sidecar, and no
LangGraph. The plan flow is a plain DB-persisted state machine
(`discovering → selecting → reviewing_list → matching → reviewing_cart →
executing → done`). The MCP facade (FastMCP mounted into FastAPI) is a
first-class second UI that calls the same modules the web app does — never
divergent logic. Data lives on a shared `./data` volume (SQLite via async
SQLAlchemy, Postgres-portable, with FTS5 for recipe search; recipe images
downloaded to `data/recipe-images/`).

```
remy-web (React/nginx) ──/api/*──▶ remy-api (FastAPI)
                                    ├── planner   (workflow state machine)
                                    ├── recipes   (store + scraper + FTS search)
                                    ├── kroger    (API client, OAuth, tokens)
                                    ├── llm       (provider-agnostic client)
                                    ├── websearch (pluggable provider)
                                    └── /mcp       (MCP facade — agent UI)
                                           │
                                           ▼  SQLite / data volume
```

## Setup

### Prerequisites

- Docker + Docker Compose
- A [Kroger developer](https://developer.kroger.com/) application (client id/secret)
- An LLM provider API key (Anthropic or OpenAI)
- A web-search backend: the bundled self-hosted **SearXNG** container (default, no
  API key), or a Brave API key, or the LLM-native search provider

### 1. Create the Docker networks (first time only)

```bash
docker network create remy-net      # internal service network
docker network create t2_proxy      # Traefik reverse-proxy network
```

### 2. Configure `.env`

```bash
cp .env.template .env
```

Fill in the values. `JWT_SECRET` and `ENCRYPTION_KEY` are **required** — the API
refuses to boot without real (non-placeholder) values.

```bash
# JWT_SECRET
python -c "import secrets; print(secrets.token_hex(32))"

# ENCRYPTION_KEY (Fernet key — encrypts Kroger tokens at rest)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Kroger developer app.** Register an app at <https://developer.kroger.com/>
with the `product.compact` and `cart.basic:write` scopes, then set
`KROGER_CLIENT_ID` / `KROGER_CLIENT_SECRET`. Register **both** OAuth redirect
URIs on the Kroger app so the same credentials work in dev and prod:

- Local dev: `http://localhost:8080/kroger/callback`
- Production: `https://remy.<your-domain>/api/kroger/callback`

Set `KROGER_REDIRECT_URI` in `.env` to whichever matches the environment you are
running (the callback route the browser is redirected back to).

**LLM.** `LLM_PROVIDER` (`anthropic` | `openai` | …) and `LLM_MODEL` select the
model via LiteLLM; set the matching provider key (`ANTHROPIC_API_KEY` or
`OPENAI_API_KEY`). All extraction/ranking calls run at temperature 0. Remy's
workload (structured extraction/classification, plus vision for photo import)
runs well on mini-class models — `openai/gpt-4o-mini` passes the full eval
suite at ~6% of `gpt-4o`'s price. To vet any model:
`LLM_MODEL=<model> pytest -m prompts` in `services/remy-api`.

> Note: when `SEARCH_PROVIDER=llm` with OpenAI, the web-search step automatically
> maps the model to its `*-search-preview` variant (e.g. `gpt-4o` →
> `gpt-4o-search-preview`), since the base models reject `web_search_options`.

**Search.** `SEARCH_PROVIDER` is one of:

- `searxng` (**default, recommended**) — a self-hosted [SearXNG](https://docs.searxng.org/)
  metasearch container included in this stack. No API key: it aggregates public
  search engines and exposes a JSON API. The compose stack runs it as the internal
  `searxng` service (on `remy-net` only, no host ports, no reverse proxy) and
  remy-api queries it at `SEARXNG_URL=http://searxng:8080`. It needs a secret key —
  generate one and put it in `.env` as `SEARXNG_SECRET`:

  ```bash
  openssl rand -hex 32     # or: python -c "import secrets; print(secrets.token_hex(32))"
  ```

  The instance config lives at [`searxng/settings.yml`](searxng/settings.yml) and is
  mounted at `/etc/searxng`. Two overrides matter: **`search.formats` must include
  `json`** (otherwise the JSON API returns HTTP 403), and **`server.limiter: false`**
  disables the bot/rate limiter so a non-browser client (remy-api) is not blocked —
  safe because the instance is not publicly reachable. The secret is injected from
  `$SEARXNG_SECRET` so nothing sensitive is committed to git.

- `brave` — the [Brave Search API](https://brave.com/search/api/); set `SEARCH_API_KEY`.
- `llm` — the configured LLM provider's native web search (Anthropic/OpenAI; no separate key).

### 3. Build and run

```bash
docker compose build
docker compose up -d
curl localhost:8080/health          # {"status":"ok",...}
# web on http://localhost:3000
```

## First run

There is no registration screen or invite-code flow — the first user is created
from the CLI.

```bash
# 1. Create the owner account as an admin (prompts for the password securely)
docker compose exec remy-api python -m remy_api create-user --username owner --admin

# 2. Log in at http://localhost:3000

# 3. Connect Kroger: Settings → Connect Kroger (OAuth redirect round-trip)

# 4. Pick your store: Settings → search by ZIP → select your store,
#    and set fulfillment to PICKUP (default) or DELIVERY.
```

### Adding household members

Admins manage accounts from **Settings → Users**: add a user (a temporary
password is shown once — hand it over; they change it in **Settings → Account**
on first login), reset passwords, and deactivate/reactivate accounts. Each user
gets their own pantry, cookbook, plans, and Kroger connection. To grant or
revoke admin on an existing account:

```bash
docker compose exec remy-api python -m remy_api set-admin --username <name> [--revoke]
```

### The cookbook

Recipes you pick during planning are saved automatically. You can also add
recipes directly from **Cookbook → Add recipe**:

- **Paste a URL** — parsed with `recipe-scrapers`, falling back to LLM
  extraction for pages without recipe markup.
- **Photos or PDF** — photograph a cookbook page (multi-page supported, order
  matters) or upload a PDF; a vision model transcribes it. Review the extracted
  recipe against your photo before saving — the model is instructed to
  transcribe only what it can read (never invent lines), and the preview is
  your check.

### Importing an existing Mealie recipe collection

If you are migrating from the old Mealie-backed setup, a one-shot CLI imports
your recipes (and images) into Remy's store. Idempotent by Mealie slug, so it is
safe to re-run.

```bash
docker compose exec remy-api python -m remy_api import-mealie \
  --username owner \
  --url https://mealie.example.com \
  --api-key <mealie-api-token> \
  --dry-run           # report what would be imported without writing

# drop --dry-run to actually import
```

## Development

### Backend (`remy-api`)

```bash
cd services/remy-api
uv sync --extra dev                 # or: pip install -e ".[dev]"

export JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
export ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
uvicorn remy_api.main:app --host 0.0.0.0 --port 8080 --reload

ruff check src tests && ruff format --check src tests
pytest                              # offline suite; add -m prompts for the live LLM evals
```

### Frontend (`remy-web`)

```bash
cd services/remy-web
npm install
npm run dev                         # Vite dev server on :3000, proxies /api → :8080
npm run build                       # tsc type-check + production build
```

For split-origin local dev (web and API on different origins), set
`WEB_APP_URL=http://localhost:3000` in the API env so the OAuth-return redirect
resolves correctly.

## MCP client connection

`remy-api` mounts an MCP facade (streamable-HTTP transport) that exposes the
whole golden path as coarse-grained tools (`find_recipes` → `select_recipes` →
`build_shopping_list` → `edit_shopping_list` → `match_products` →
`swap_product` → `execute_cart`, plus `search_my_recipes` / `get_recipe` /
`save_recipe`, `get_settings` / `set_store` / `edit_pantry`, and `plan_status`).
An agent orchestrates only *between* gates and relays choices from you; all the
deterministic work runs inside the tools. `execute_cart` is the only real-cart
write, and it accepts only a `cart_draft_id` a prior `match_products` issued.

**Endpoint** (behind the reverse proxy the `/mcp` path is served under `/api`):

- Production: `https://remy.<your-domain>/api/mcp`
- Local (through the web proxy): `http://localhost:3000/api/mcp`
- Local (direct to the API): `http://localhost:8080/mcp`

**Auth.** Generate a per-user API token in **Settings → API tokens** (shown
once; hashed at rest, `remy_…` prefix) and send it as a bearer token. JWTs are
rejected on this endpoint. Kroger OAuth connect stays web-only (browser redirect
required) — the tools return a clear "Kroger not connected — visit Settings"
error otherwise.

**Claude Code:**

```bash
claude mcp add --transport http remy https://remy.example.com/api/mcp \
  --header "Authorization: Bearer remy_your_token_here"
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "remy": {
      "type": "http",
      "url": "https://remy.example.com/api/mcp",
      "headers": { "Authorization": "Bearer remy_your_token_here" }
    }
  }
}
```

The web UI and the MCP facade share the same plan rows — a plan started in the
browser is visible and resumable via `plan_status`, and vice versa. Toggle the
facade with `MCP_FACADE_ENABLED` (default on). It sits behind the reverse proxy
and enforces its own bearer auth, so DNS-rebinding protection is off by default;
set `MCP_ALLOWED_HOSTS` / `MCP_ALLOWED_ORIGINS` to your deploy domain to enable
strict host/origin checks.

## Deployment

- **Compose** runs the two services on a shared `./data` volume. `remy-web`
  joins both `t2_proxy` (Traefik) and `remy-net`; `remy-api` is internal-only on
  `remy-net` and reached via the web container's nginx `/api/` proxy (which
  strips the `/api` prefix).
- **Traefik.** `remy-web` carries the router labels
  (`Host(\`remy.$DOMAINNAME\`)`, TLS on the `https` entrypoint). Set
  `DOMAINNAME` in the compose environment. All of `/` (SPA), `/api/*` (backend),
  and `/api/mcp` (agent facade) are served on the single `remy.<domain>` host.
- **`WEB_APP_URL` empty in production.** With web and API on one origin behind
  Traefik, leave `WEB_APP_URL` empty so OAuth-return redirects stay relative and
  resolve to the deployed origin. Only set it for split-origin local dev.
- **Secrets fail closed.** Missing/placeholder `JWT_SECRET` or `ENCRYPTION_KEY`,
  or an invalid Fernet `ENCRYPTION_KEY`, abort startup with a clear message.

## Known limitations

- **The Kroger public API is add-only.** Remy can add items to your real Kroger
  cart but cannot read it, remove from it, clear it, or check out (FR-18). Any
  cart view inside Remy is a local shadow record and is labeled as such;
  estimated totals are estimates.
- **Checkout happens on your store's site.** After Remy fills the cart it hands
  you a link to your store banner's cart (e.g. fredmeyer.com/cart) to schedule
  pickup and pay. There is no checkout automation.
- **No self-registration.** Accounts are created by an admin (Settings → Users)
  or the `create-user` CLI — deliberate for a household deployment.
