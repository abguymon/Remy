# Remy v2 — Product Requirements Document

## 0. How to read this document

This PRD specifies a ground-up rewrite of **Remy**, a self-hosted AI agent that turns a list of meals into a filled Kroger (Fred Meyer) grocery cart. A proof-of-concept exists in this repository; it is **reference material only** — do not port its code wholesale. Where the POC got something right, this document says so explicitly; where it got something wrong, the requirement here overrides whatever the old code does. If this document conflicts with the existing code, this document wins.

Sections 1–3 describe the product. Sections 4–8 describe the system. Section 9 lists lessons from the POC that must not be repeated. Section 10 defines acceptance criteria.

---

## 1. Product summary

**One sentence:** The user tells Remy what meals they want to cook this week; Remy finds ~5 recipe options per meal from the web and the user's saved collection, the user picks, Remy builds a consolidated shopping list, the user reviews and edits it, and Remy fills their Kroger cart with the best-matching products for pickup at their Fred Meyer — leaving final checkout on kroger.com.

**Primary user:** A single household (the owner). The system must be *multi-user ready* at the data layer (see §6), but v1 ships with single-user UX. No invite-code flows, no admin screens.

**Deployment:** Self-hosted via Docker Compose behind the user's existing reverse proxy (Traefik). All data stays local except calls to the Kroger API, the search provider, and the LLM provider.

### 1.1 Core user journey (the golden path)

1. **Plan** — User enters a list of meals in free text (e.g. "chicken tikka masala, some kind of salmon dish, and tacos on Friday").
2. **Discover** — For each meal, Remy presents ~5 recipe candidates: matches from the user's saved recipe collection first, then web results (favorite sites prioritized). Each candidate shows a photo, title, source, and total time when available.
3. **Select** — User picks one recipe per meal (or skips a meal, or pastes a specific URL to use instead).
4. **List** — Remy scrapes/parses the selected recipes, extracts ingredients, **consolidates duplicates across recipes** (two recipes each needing an onion → one line: "2 onions"), and filters out pantry staples.
5. **Review** — User sees the full list in three groups: *to buy*, *pantry (skipped)*, and can uncheck items, edit quantities, and re-include pantry items.
6. **Match** — Remy searches Kroger for each approved item at the user's preferred store, picks the best product match via LLM ranking, and shows the actual product (photo, size, price, availability) per line. User can swap any match from the top alternatives or drop the line.
7. **Order** — Remy adds the confirmed products to the user's real Kroger cart (pickup modality) and shows a final report: added / substituted / unavailable. A prominent link hands the user to kroger.com/cart to schedule pickup and pay.
8. **Save** — Selected recipes are saved into Remy's own recipe collection automatically, so future planning searches them first.

### 1.2 Explicit non-goals for v1

- No checkout automation (Kroger public API cannot place orders; no browser automation).
- No weekly calendar / meal-plan-by-day view.
- No dietary preferences, budgets, price optimization, or recipe ratings/notes. (Design should not preclude them.)
- No Mealie. The POC's Mealie dependency is removed entirely (see §5).
- No mobile app; responsive web is sufficient.

---

## 2. Functional requirements

### 2.1 Meal input & recipe discovery

- **FR-1**: Accept free-text meal descriptions; an LLM (structured output, see §7) extracts a list of distinct meal intents. Also accept direct recipe URLs anywhere in the input; a URL becomes a pre-selected candidate for that meal.
- **FR-2**: For each meal, produce up to 5 candidates from two sources, merged and deduplicated (by URL and normalized title):
  - **Saved recipes** (Remy's own store, §5) — full-text search on title/ingredients; these rank first.
  - **Web search** via a pluggable provider (§7.3) — query per meal, with the user's configured *favorite recipe sites* boosted (query them with `site:` restriction or provider-equivalent first, fill remaining slots from general search).
- **FR-3**: Filter out roundup/listicle pages ("17 Best Taco Recipes") via an LLM classification pass; only individual recipe pages survive.
- **FR-4**: Each candidate carries: title, source domain, URL (or saved-recipe id), thumbnail (og:image or saved image), and origin badge (`saved` / `favorite site` / `web`).
- **FR-5**: Discovery for multiple meals runs concurrently; a slow meal must not block others. Partial results are acceptable and must be labeled (e.g. "web search failed for this meal — showing saved recipes only"), never silently empty.

### 2.2 Recipe capture & parsing

- **FR-6**: When a web recipe is selected, parse it with the **`recipe-scrapers`** Python library (schema.org/JSON-LD first). If it fails or yields incomplete data, fall back to fetching the page and extracting `{title, image, yield, times, ingredients[], instructions[]}` with an LLM structured-output call.
- **FR-7**: Parsed recipes are saved to Remy's recipe store with: title, slug, source URL, image (downloaded and stored locally), yield, prep/cook time, ingredient lines (both the raw line and a parsed `{quantity, unit, food, note}`), instructions, created-at, last-cooked-at (nullable).
- **FR-8**: Users can also add a recipe manually (paste URL from the recipes screen) and edit any saved recipe's fields.

### 2.3 Shopping list construction

- **FR-9**: Ingredient lines from all selected recipes are parsed into `{quantity, unit, food, note}` (LLM structured output; the raw line is always retained and displayed on hover/expand).
- **FR-10**: **Consolidation:** lines with the same normalized food are merged; compatible units are summed ("1 cup" + "2 cups"), incompatible ones are listed together ("1 lb + 2 cloves garlic" stays split or shows both). Each consolidated line records which recipes contributed.
- **FR-11**: **Pantry bypass:** the user maintains a pantry-staples list (per-user, editable in Settings, seeded from the POC's `pantry.yaml` defaults). Matching uses **word-boundary matching against the parsed food name** (the POC's legacy word-boundary regex, not the newer bidirectional-substring version, which produced false positives). Matched items move to a visible "pantry — skipped" group, not deleted.
- **FR-12**: Review UI: check/uncheck any line (including re-including pantry items), edit quantity, delete line, add a free-text line. Nothing proceeds to product matching until the user confirms.

### 2.4 Product matching & cart execution

- **FR-13**: For each approved line, one **batched** LLM call across the whole list first translates ingredient lines into Kroger-style search terms and purchase quantities (port the POC legacy prompt's heuristics: grocery-store naming, UK→US terms, produce → "fresh X", dried/canned defaults, package-size awareness). Fall back to per-item extraction if the batch call fails validation.
- **FR-14**: For each item (concurrently, bounded parallelism): search Kroger products at the preferred store filtered by the pickup modality, then LLM-rank the top ~10 results to pick the best match (avoid multipacks/value packs unless quantity warrants; prefer exact form — canned vs dried, fresh vs frozen). Check stock level; if the top pick is out of stock or not pickup-eligible, choose the best in-stock substitute and mark it as a substitution.
- **FR-15**: Present the matched cart to the user **before** any Kroger cart writes: per line — product photo, name, size, unit count, price, stock status, and a substitution flag. User can swap to an alternative (show the other top search results), change count, or drop the line.
- **FR-16**: On final confirmation, add all items to the real Kroger cart via `PUT /cart/add` equivalent, with modality PICKUP (or the user's configured fulfillment method). Report per-item outcomes truthfully: `added`, `substituted`, `unavailable`, `not_found`, `failed` — a failed API call must surface as failed, never as silent success (§9).
- **FR-17**: After execution, show an order summary with estimated total and a link to `https://www.kroger.com/cart` for checkout. Persist the summary as an order-history record (local — the Kroger API cannot read back the real cart).
- **FR-18**: Known platform constraints, to be reflected in UX copy: the Kroger public API is **add-only** (cannot read, remove from, or clear the real cart, and cannot check out). Any local "cart" view is a shadow record and must be labeled as such.

### 2.5 Recipe collection ("cookbook")

- **FR-19**: A Recipes screen lists saved recipes (card grid: image, title, source, last cooked) with search and delete. Clicking opens a detail view: image, meta, ingredients, instructions, link to original source.
- **FR-20**: Saved recipes are first-class discovery sources (FR-2). Marking a plan "done" (or one-click on the recipe) stamps `last_cooked_at`.

### 2.6 Settings

- **FR-21**: Kroger account: connect (OAuth2 redirect flow, see §7.2), status display, disconnect.
- **FR-22**: Store: search Kroger locations by ZIP, pick preferred store (persisted); fulfillment method PICKUP/DELIVERY (default PICKUP).
- **FR-23**: Pantry staples list management (chips, add/remove, reset to defaults).
- **FR-24**: Favorite recipe sites list management (domains, ordered).
- **FR-25**: Provider config (LLM provider/model, search provider) is server-side env config, not user-facing settings.
- **FR-26**: API tokens: generate/revoke per-user bearer tokens for MCP clients (§7.4) from Settings; tokens are hashed at rest and scoped to the owning user.

---

## 3. UX requirements

- Single-page React app; the golden path (§1.1) is one continuous, resumable flow on the home screen with a visible step indicator (Plan → Pick recipes → Review list → Review cart → Done).
- The flow's state is server-persisted: closing the browser and returning resumes at the same step. "Start over" abandons the current plan explicitly.
- Every long operation streams progress (per-meal search status, per-item matching status) rather than a single spinner. Server-Sent Events or polling with granular status objects — do not leave the user staring at "loading" for 30+ seconds as the POC does.
- Errors are always surfaced with a human-readable message and a retry affordance scoped to the failed unit (retry one meal's search, retry one item's match), not a whole-flow restart.
- Clean, modern look: Tailwind, card-based recipe grids, product images throughout. The POC's `remy-web` layout is a reasonable structural starting point; the visual bar should be higher.

---

## 4. System architecture

**Pattern: modular monolith backend + thin MCP facade (hybrid).**

```
┌────────────┐     ┌──────────────────────────────────────────┐
│  remy-web   │────▶│  remy-api (FastAPI)                       │
│  React/Vite │     │  ├── planner  (workflow engine)           │
└────────────┘     │  ├── recipes  (store + scraper + search)  │
                    │  ├── kroger   (API client, OAuth, tokens) │
                    │  ├── llm      (provider-agnostic client)  │
                    │  ├── websearch (pluggable provider)       │
                    │  └── mcp      (MCP facade — agent UI, §7.4)│
                    └───────────────┬──────────────────────────┘
                                    │ SQLite (or Postgres-ready SQLAlchemy)
                                    ▼
                              data volume
```

- **Two deployable services only**: `remy-web` (static React behind nginx) and `remy-api`. Kroger and recipe functionality are **internal Python modules**, not separate MCP services. This eliminates the POC's SSE plumbing, per-call connection setup, and the class of bug where the API called MCP tool names that didn't exist and failed silently.
- **MCP facade (first-class second interface):** `remy-api` additionally mounts an MCP endpoint (FastMCP mounted into FastAPI, sharing the same internal modules) so a general-purpose agent (Claude Desktop, Hermes/OpenClaw-style personal agents) can drive the *entire* golden path conversationally. This is not a debug surface — it is the second UI, specified in §7.4. The facade calls the same planner/recipes/kroger modules the web app uses and must never have divergent logic. Feature flag (`MCP_FACADE_ENABLED`) defaults on.
- **Workflow engine:** the plan flow is a **plain, explicit state machine persisted to the DB** (the `plans` table in §6 is the checkpoint). Do not use LangGraph — the flow has exactly three user gates (select recipes, approve list, confirm cart) and no dynamic branching, so a framework buys nothing here. Each step is a plain async function that reads the plan row, does its work, and writes the next status + step data. **Requirement:** exactly one implementation of the workflow (the POC maintained two divergent copies; see §9). State must be inspectable via a `GET /plan/state` endpoint returning the current step and all step data.
- **Concurrency:** all fan-out work (per-meal search, thumbnail fetch, per-item product matching) uses bounded async concurrency (e.g. semaphore of 5–8) — the POC's new stack regressed to sequential loops.

---

## 5. Recipe store (replaces Mealie)

Mealie is removed. Rationale: Remy used only three Mealie capabilities (search, fetch, URL-import), the UI is disliked, and it added a container plus per-user API-key management. Replacement:

- **Storage:** `recipes` + `recipe_ingredients` tables (schema in §6), images on the data volume under `data/recipe-images/{recipe_id}.jpg` (downloaded at save time; never hotlink).
- **Parsing:** `recipe-scrapers` library (same engine Mealie wraps) → LLM structured-output fallback (FR-6).
- **Search:** SQLite FTS5 over title + ingredient food names (or `ILIKE` fallback if Postgres). No external service.
- **Migration:** a one-shot CLI script (`remy-api` management command) that imports existing recipes from a Mealie instance via its REST API (given base URL + API key): fetch all recipes, map fields, download images. This is how the user's current collection comes across; it is not a runtime dependency.

---

## 6. Data model & multi-tenancy posture

Single-user UX, **multi-user-ready schema**: every user-owned table carries `user_id` from day one; all queries are scoped by it; auth resolves to a user record. Adding registration later must require no migrations of existing tables.

Tables (SQLAlchemy async; SQLite via aiosqlite, but avoid SQLite-only features except FTS5 so Postgres is a config change):

- `users` — id (uuid), username, password_hash (bcrypt/argon2), created_at, is_active.
- `user_settings` — user_id FK; pantry_items JSON, favorite_sites JSON, store_location_id, store_name, zip_code, fulfillment_method.
- `kroger_tokens` — user_id FK; access_token, refresh_token, expires_at — **encrypted at rest** with Fernet via required `ENCRYPTION_KEY`. This is the **single** token store: the Kroger module reads/writes/refreshes here. (The POC kept a second plaintext token file inside the MCP server that silently diverged from the DB copy — do not reproduce.)
- `oauth_states` — state, user_id, created_at (10-min TTL, deleted on use). PKCE verifier stored alongside state.
- `recipes` / `recipe_ingredients` — per §5, with user_id.
- `plans` — user_id, status (enum: discovering / selecting / reviewing_list / matching / reviewing_cart / executing / done / abandoned), created_at, plus JSON columns (or child tables) for meals, candidates, selections, list lines, matches, and execution results. One active plan per user.
- `orders` — user_id, plan_id, items JSON (per-item outcome + price), estimated_total, created_at.
- `api_tokens` — user_id, token_hash, name, created_at, last_used_at, revoked_at (nullable) — bearer tokens for MCP clients (FR-26).

**Auth (v1):** single-user login (username/password → JWT, HS256, 7-day expiry). `JWT_SECRET` and `ENCRYPTION_KEY` are **required** at startup — refuse to boot with defaults/missing (the POC only warned). First user is created via env vars or a CLI command, not an invite-code flow.

---

## 7. External integrations

### 7.1 LLM — provider-agnostic

- Abstract all LLM calls behind one internal interface configured by env (`LLM_PROVIDER`, `LLM_MODEL`, provider API key). Implement via **LiteLLM** (or LangChain chat-model abstraction if LangGraph is used) so Anthropic Claude, OpenAI, and local endpoints are config swaps. Default config ships pointing at a current top-tier model; temperature 0 for all extraction/ranking calls.
- **Every LLM call uses structured output** (native tool-use / JSON-schema response format) validated with Pydantic models, with one retry on validation failure. **No regex-stripping of markdown fences, no "return just a number" prompts** (§9).
- The LLM call sites (all exist in POC legacy `remy-agent/src/remy_agent/nodes.py` as prompt prior art): meal extraction, listicle filtering, saved-recipe relevance filtering, recipe-parse fallback, ingredient-line parsing, batched product-term extraction, product-match ranking.

### 7.2 Kroger

- Direct client against the Kroger **Public API** (the `kroger-api` Python SDK the POC uses is fine), as an internal module.
- Client-credentials token for products/locations; per-user OAuth2 + PKCE (`product.compact cart.basic:write`) for cart. Auto-refresh; single token store (§6).
- OAuth flow: `GET /kroger/auth` returns the authorization URL (state + PKCE persisted) → Kroger login → `GET /kroger/callback` (unauthenticated route, validates state) exchanges the code, stores tokens, redirects to `/settings?kroger=connected`.
- Respect documented rate limits (products 10k/day, locations 1.6k/day, cart 5k/day); bounded concurrency covers this at household scale.
- Hard constraints to design around (restated from FR-18): add-only cart, no checkout, no reading the real cart.

### 7.3 Web search — pluggable provider

- Define a `SearchProvider` interface: `search(query, site: str | None, max_results) -> [ {title, url, snippet} ]`.
- Ship two implementations, selected by env: (a) **Brave Search API** (or Serper — pick whichever at implementation time; both are cheap at this volume) as the default; (b) an **LLM-native web-search tool** implementation (e.g. Anthropic's web search tool) as an alternative. The DuckDuckGo scraping approach from the POC is explicitly retired.
- Thumbnails: fetch og:image concurrently with a short timeout; missing thumbnail is cosmetic, never blocking.

### 7.4 MCP tool surface (agent interface)

The MCP facade exposes **coarse-grained tools that mirror the pipeline gates**, not raw primitives. All deterministic logic (search + listicle filtering, parsing, consolidation, pantry bypass, batched product extraction, ranking, substitution) runs *inside* the tools; the calling agent orchestrates only *between* gates and relays choices from the human. Design rules:

- **Draft-id chain as a safety structure.** Stateful steps return an opaque `draft_id`; the next step requires it. `execute_cart` accepts only a `cart_draft_id` previously returned by `match_products` — an agent cannot construct a cart write from scratch. Drafts persist in the `plans` table (same rows the web UI uses; the two interfaces see and can resume the same in-flight plan).
- **Rich structured returns.** Every tool returns compact JSON designed for an agent to render/summarize in chat: candidates carry title/source/url/thumbnail; matched items carry product name, size, price, stock status, substitution flag, and up to 3 alternatives (each with a stable `alternative_id` so a swap is a reference, not a re-search).
- **Explicit mutation reporting.** Tools that touch the real Kroger cart return per-item outcomes (`added`/`substituted`/`unavailable`/`failed`) and tool descriptions instruct the agent to relay substitutions and failures verbatim, never to summarize them away.

Toolset:

| Tool | In | Out | Notes |
|---|---|---|---|
| `find_recipes` | `meals[]` (free text and/or URLs) | per-meal candidate lists + `plan_draft_id` | runs FR-1–FR-5 |
| `select_recipes` | `plan_draft_id`, per-meal choice (candidate id or URL) | parsed recipes summary | runs FR-6–FR-8; saves to cookbook |
| `build_shopping_list` | `plan_draft_id` | consolidated list (to-buy + pantry-skipped) + line ids | runs FR-9–FR-11 |
| `edit_shopping_list` | `plan_draft_id`, line edits (include/exclude/qty/add) | updated list | FR-12 equivalent |
| `match_products` | `plan_draft_id` | matched cart draft (`cart_draft_id`) with prices, stock, alternatives, estimated total | runs FR-13–FR-15 |
| `swap_product` | `cart_draft_id`, line id, `alternative_id` \| drop | updated cart draft | |
| `execute_cart` | `cart_draft_id` | per-item outcome report + kroger.com/cart link | runs FR-16–FR-17; the only real-cart write |
| `search_my_recipes` / `get_recipe` / `save_recipe(url)` | — | cookbook access | FR-19–FR-20 |
| `get_settings` / `set_store(zip → pick)` / `edit_pantry` | — | settings access | FR-21–FR-24 |
| `plan_status` | — | current plan step + data | resume/inspect; same data as `GET /plan/state` |

Auth: MCP clients authenticate with a bearer token (per-user API token generated in Settings) resolving to the same `user_id` scoping as the web app. Kroger OAuth connect remains web-only (browser redirect required); the `execute_cart`/`match_products` tools return a clear "Kroger not connected — visit Settings" error otherwise.

---

## 8. Configuration

`.env` (template checked in):

```
JWT_SECRET=              # required, no default
ENCRYPTION_KEY=          # required, Fernet key
KROGER_CLIENT_ID= / KROGER_CLIENT_SECRET=
KROGER_REDIRECT_URI=     # e.g. https://remy.example.com/api/kroger/callback
LLM_PROVIDER= / LLM_MODEL= / <provider API key>
SEARCH_PROVIDER=brave    # brave | serper | llm
SEARCH_API_KEY=
MCP_FACADE_ENABLED=true
```

Docker Compose: `remy-web` (nginx, port 3000), `remy-api` (port 8080), shared `data/` volume, Traefik labels as in the current compose file. No Mealie, no separate MCP containers.

---

## 9. Lessons from the POC — hard requirements

These are failure modes observed in the existing code. Each is a requirement, not advice:

1. **No silent failures.** The POC's MCP client returned `None` on any error and routers returned empty lists, so a broken integration looked like "no results" (and misnamed tool calls made cart execution a silent no-op for months of commits). Every integration call either succeeds, raises a typed error surfaced to the API layer, or returns an explicit degraded-result marker rendered in the UI.
2. **One workflow implementation.** The POC had two divergent copies (legacy Streamlit had the good logic; the new API had a lobotomized port). The rewrite has exactly one planner module.
3. **Structured outputs everywhere.** No parsing LLM prose with regex/fence-stripping.
4. **Port the legacy "brain," not the new "body's" logic:** batched product extraction with grocery heuristics, LLM product ranking (anti-multipack), stock/fulfillment-aware substitution, favorite-site-prioritized parallel search with listicle filtering, word-boundary pantry matching. All of that lives in `services/remy-agent/src/remy_agent/nodes.py` and is the best reference in the repo. **Do not port verbatim** — the prompts were a first pass; `V2_PLAN.md` Appendix A reviews each prompt/heuristic and specifies what to keep, fix, and improve.
5. **Secrets hygiene:** required JWT/encryption keys (fail closed), Kroger tokens encrypted, one token store.
6. **Concurrency by default** with bounded parallelism for all fan-out steps.
7. **Honest cart semantics:** never present the local shadow cart as the real Kroger cart; label estimates as estimates.

---

## 10. Acceptance criteria (v1 done means)

1. From a fresh `docker compose up` with a configured `.env`, the owner can log in, connect Kroger, pick their Fred Meyer by ZIP, and set fulfillment to PICKUP.
2. Entering "chicken tikka masala, salmon bowls, street tacos" yields, within ~30s and with visible per-meal progress, up to 5 candidates per meal with images, mixing saved recipes (ranked first) and web results (favorite sites badged), with zero listicle pages.
3. Selecting three recipes produces a consolidated ingredient list where duplicate foods are merged with combined quantities, pantry staples are visibly separated (and re-includable), and every line is editable.
4. Confirming the list produces per-line Kroger product matches with photo, size, price, and stock status; at least one line can be swapped to an alternative product before execution.
5. Final confirmation results in the items actually appearing in the real Kroger cart on kroger.com, and the app shows a truthful per-item report (added/substituted/unavailable/failed) plus an estimated total and a link to kroger.com/cart.
6. The three selected recipes appear in the Recipes screen with images and full ingredients/instructions, and are findable via search in the next plan.
7. Killing the browser mid-flow and returning resumes the plan at the same step.
8. Stopping the LLM provider or search provider mid-flow produces visible, scoped error messages with retry — never empty results presented as success.
9. A migration command imports the user's existing Mealie recipes.
10. An MCP client authenticated with a Settings-generated API token can complete the entire golden path conversationally — `find_recipes` → `select_recipes` → `build_shopping_list` → `match_products` → `execute_cart` — resulting in items in the real Kroger cart, and `execute_cart` rejects a `cart_draft_id` it did not previously issue.
11. A plan started in the web UI is visible and resumable from the MCP `plan_status` tool, and vice versa.
