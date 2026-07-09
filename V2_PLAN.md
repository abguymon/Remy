# Remy v2 — Build Plan

Task breakdown for implementing `PRD.md` + `DESIGN_BRIEF.md`. Each task below is sized to be handed to a single Claude Code session.

**Instructions for an implementing session:**
1. Read `PRD.md` (authoritative spec — overrides all existing code) and `DESIGN_BRIEF.md` before starting. For frontend tasks, also import the Claude Design project linked at the top of `DESIGN_BRIEF.md`.
2. The old code lives under `legacy/` (Task 0 moves it there) — reference material only. Never import from it.
3. Do exactly one task per session unless a task says it can be combined. Update the checkbox and the "Status notes" line under your task when done.
4. Commit at the end of the task with a message referencing the task ID (e.g. `T5: planner state machine`). Run lint/tests before committing.
5. Every LLM call uses structured outputs validated by Pydantic (PRD §7.1). Every prompt lives in the prompt library (T4), not inline in business logic.
6. When porting prompts/heuristics from legacy, follow **Appendix A** — it reviews each legacy prompt and specifies what to keep, fix, and improve. Do not port verbatim.

---

## Phase 0 — Repo preparation

### ☑ T0: Restructure repo for v2
Move the existing implementation to `legacy/` (`git mv services legacy-services` → `legacy/services`, plus `ARCHITECTURE.md`, `remy_spec.md`, `PLAN.md` → `legacy/`). Keep at root: `PRD.md`, `DESIGN_BRIEF.md`, `V2_PLAN.md`, `.env.template` (rewrite per PRD §8), `pantry.yaml` (copy from `legacy/services/remy-agent/pantry.yaml` — it seeds pantry defaults), `recipe_sources.yaml` (seeds favorite sites). Scaffold the new tree: `services/remy-api` (FastAPI app skeleton with `/health`, config loading that **fails closed** on missing `JWT_SECRET`/`ENCRYPTION_KEY`, ruff + pytest wired) and `services/remy-web` (Vite + React 18 + TS + Tailwind skeleton). New `docker-compose.yml` with the two services + shared `data/` volume, preserving the Traefik labels from the legacy compose file. Update `CLAUDE.md` to describe the v2 layout and point to the three docs.
**Done when:** `docker compose up` serves a healthy API and a blank web app; missing env secrets abort startup with a clear message.
Status notes: Done. POC moved to `legacy/` (services + old compose + POC docs); root seeds `.env.template` (PRD §8), `pantry.yaml`, `recipe_sources.yaml`; scaffolded `services/remy-api` (FastAPI `/health`, fail-closed config, ruff+pytest 6/6 green) and `services/remy-web` (Vite/React18/TS/Tailwind); new two-service `docker-compose.yml` — `docker compose build && up` verified healthy (API on :8080, web on :3000, `/api/` proxy round-trips) and boot aborts with a clear ConfigError when JWT_SECRET/ENCRYPTION_KEY are missing.

## Phase 1 — Backend foundation

### ☑ T1: Data model, auth, settings
Implement the full schema from PRD §6 (async SQLAlchemy, SQLite/aiosqlite, Postgres-portable; FTS5 for recipe search may be SQLite-specific): `users`, `user_settings`, `kroger_tokens`, `oauth_states`, `recipes`, `recipe_ingredients`, `plans`, `orders`, `api_tokens`. Fernet crypto helper (required key); Kroger tokens and any stored secrets encrypted at rest. JWT auth (HS256, 7-day), bcrypt/argon2 passwords, first-user bootstrap via CLI command (`python -m remy_api create-user`) — no invite codes. Settings endpoints: `GET/PUT /users/me/settings` (pantry list seeded from `pantry.yaml`, favorite sites from `recipe_sources.yaml`, store, fulfillment). API-token endpoints (FR-26): create (hash at rest, show once), list, revoke; bearer-token auth path resolving to `user_id` for MCP later.
**Done when:** integration tests cover register-bootstrap → login → settings round-trip → API token create/auth/revoke, and encrypted columns are unreadable in the raw DB file.
Status notes: Done. Full async SQLAlchemy 2.x schema (all 9 tables, cascade FKs, StrEnum/JSON for Postgres portability, SQLite FK pragma enabled), created on startup lifespan. Fernet crypto helper + `EncryptedString` TypeDecorator for Kroger tokens. Argon2id passwords, JWT HS256 (7-day), `remy_`-prefixed SHA-256-hashed API tokens; `get_current_user` dependency handles both bearer paths and stamps `last_used_at`. Login-only auth (no registration/invite), `python -m remy_api create-user` bootstrap CLI, settings endpoints seeded from root pantry.yaml/recipe_sources.yaml, API-token CRUD. Uniform `{error:{code,message}}` envelope (401/403/404/409/422). 19 tests + ruff green.

### ☐ T2: Kroger module
Internal module (no MCP service) using the `kroger-api` SDK: client-credentials token for products/locations; per-user OAuth2 + PKCE (`product.compact cart.basic:write`) with the DB as the **single** token store and auto-refresh (PRD §7.2). Endpoints: `GET /kroger/auth`, `GET /kroger/callback` (state + PKCE from `oauth_states`), `GET /kroger/status`, `DELETE /kroger/disconnect`, `GET /kroger/stores?zip=`, `POST /kroger/stores/{id}/select`. Module functions consumed by the planner: `search_products(term, location_id, limit, fulfillment)` returning normalized products (description, size, price, stock level, fulfillment flags, images, upc, department), `add_items_to_cart(items, modality)`. Typed errors throughout — no `None`-swallowing (PRD §9.1). Reference: `legacy/services/kroger-mcp/src/kroger_mcp/tools/` for API usage patterns only.
**Done when:** with real credentials, a manual script connects OAuth, finds the Fred Meyer by ZIP, searches "black beans" at that store, and adds one can to the real cart.
Status notes: —

## Phase 2 — Intelligence layer

### ☐ T3: Recipe store + scraper + Mealie import
Recipes module per PRD §5: CRUD + FTS search over title/ingredient foods; `recipe-scrapers` for URL parsing with LLM structured-output fallback (uses T4's client — stub the interface if building in parallel); images downloaded to `data/recipe-images/`, never hotlinked. Endpoints: recipes list/search/get/create-from-url/update/delete, `POST /recipes/{id}/cooked` (stamps `last_cooked_at`). One-shot CLI `python -m remy_api import-mealie --url --api-key` mapping Mealie recipes + images into the store.
**Done when:** three real recipe URLs (one schema.org-clean, one messy, one paywalled/broken) parse or fail gracefully with typed errors; Mealie import brings over an existing library with images.
Status notes: —

### ☐ T4: LLM client, search providers, prompt library
LLM: provider-agnostic client (LiteLLM) configured by env; a single `structured(prompt_id, input, schema)` entrypoint enforcing Pydantic validation with one retry (PRD §7.1). Search: `SearchProvider` interface + Brave implementation + LLM-native-web-search implementation, env-selected (PRD §7.3); og:image thumbnail fetcher (proper HTML parser, short timeout, bounded concurrency). **Prompt library**: implement all six prompts as versioned modules with typed input/output models, following Appendix A's port-and-improve guidance. Include a lightweight eval harness: fixture files of real inputs (ingredient lines from legacy test data, sample search results) with expected outputs, runnable as `pytest -m prompts`, so future prompt tuning is measurable rather than vibes.
**Done when:** prompt evals pass against fixtures; swapping `LLM_PROVIDER` between two providers requires only env changes.
Status notes: —

## Phase 3 — The planner

### ☐ T5: Planner state machine + pipeline
The core. Plain persisted state machine over the `plans` table (PRD §4 — no LangGraph): statuses `discovering → selecting → reviewing_list → matching → reviewing_cart → executing → done/abandoned`. Steps as plain async functions with bounded concurrency (semaphore 5–8):
- **Discover** (FR-1–FR-5): meal extraction (prompt P1), per-meal concurrent search — recipe store first, then favorite-site-boosted web search — listicle filtering (P3), dedup (Appendix A.7), thumbnails. Per-meal status streaming; degraded results labeled, never silent.
- **Select** (FR-6–FR-8): parse chosen URLs via T3, save to cookbook, collect parsed ingredient lines (P2 relevance filter for store matches).
- **List** (FR-9–FR-12): ingredient parsing (P4a), consolidation (deterministic code per FR-10), pantry bypass (word-boundary match on parsed food name), edit operations.
- **Match** (FR-13–FR-15): batched product-term extraction (P4), per-item Kroger search + ranking with alternatives (P5), stock/fulfillment-aware substitution (port legacy fallback logic per Appendix A.8), producing a cart draft with prices, alternatives, estimated total. Swap/drop/count operations.
- **Execute** (FR-16–FR-17): real cart writes, truthful per-item outcomes, order record.
REST endpoints for each gate + `GET /plan/state`; one active plan per user; resumable.
**Done when:** a scripted end-to-end run (real Kroger, real web search) goes from "tikka masala and tacos" to items in the real Kroger cart, and every acceptance-criteria behavior in PRD §10 items 2–5 is demonstrable via the API alone.
Status notes: —

### ☐ T6: MCP facade
Mount FastMCP into remy-api exposing the PRD §7.4 toolset (`find_recipes` … `execute_cart`, cookbook, settings, `plan_status`), authenticated by T1's API tokens, calling the same planner/module code — zero divergent logic. Enforce the draft-id chain (`execute_cart` rejects unknown/foreign/stale draft ids). Feature flag `MCP_FACADE_ENABLED` (default true).
**Done when:** PRD §10 criteria 10–11 pass — a Claude Code session connected to the facade completes the whole golden path conversationally, and a web-started plan is visible via `plan_status`.
Status notes: —

## Phase 4 — Frontend

Import the Claude Design project (link at top of `DESIGN_BRIEF.md`) before starting; it is the visual source of truth, the brief is the state/intent checklist. Phone-first (390px), light only. Shared foundations in the first FE task: API client with typed errors, auth store, tab-bar/sidebar layout, design tokens, the component inventory from brief §6.

### ☐ T7: Frontend — flow screens (Plan steps 0–4)
Brief §4.2–§4.6 and the flagship cart-review spec §5: meal input + resume card, per-meal streaming candidate cards, shopping-list review with three groups and edit ops, cart review (stacked cards, inline swap expander with alternatives, live estimated total in sticky bar), done/report screen with the kroger.com handoff CTA. Implement every listed state: skeletons, per-unit degraded banners with scoped retry, empty states.
**Done when:** the full golden path runs in the browser against the real backend on a 390px viewport; brief §4's states for these screens are all reachable and match the design.
Status notes: —

### ☐ T8: Frontend — cookbook, cart record, settings, login
Brief §4.1, §4.7–§4.10: login; cookbook grid + search + add-URL sheet with parse preview; recipe detail (editorial register) with edit/delete/"I cooked this"; Cart tab styled as *Remy's record* (never a live cart) with order history; settings (Kroger connect with OAuth return toast, store picker, fulfillment, pantry chips, favorite sites, API tokens with show-once modal).
**Done when:** all states listed in the brief for these screens exist; Kroger connect round-trips from the browser.
Status notes: —

## Phase 5 — Hardening & cutover

### ☐ T9: Verification pass
Walk PRD §10 acceptance criteria 1–11 end-to-end against a real deployment (real Kroger account, real store, real web search), fixing what fails. Add the failure-mode drills: kill the LLM provider mid-plan and the search provider mid-discovery — verify scoped, visible errors with retry (criterion 8); kill the browser mid-flow and resume (criterion 7). Record results in a `VERIFICATION.md` checklist.
Status notes: —

### ☐ T10: Cutover
Delete `legacy/`, finalize `README.md` (setup, env, deploy, Mealie import instructions), final `CLAUDE.md`, merge v2 → master, deploy, run the Mealie import against the production Mealie instance, then decommission the Mealie + old MCP containers.
Status notes: —

**Sequencing:** T0 → T1 → {T2, T3, T4 in any order/parallel sessions} → T5 → {T6, T7, T8 in any order} → T9 → T10. T7/T8 can start against T5's API even before T6.

---

## Appendix A — Legacy prompt & heuristic review (port-and-improve guide)

The legacy prompts (`legacy/services/remy-agent/src/remy_agent/nodes.py`) were a working first pass. This review is the required guidance for T4/T5: **Keep** = proven behavior to preserve; **Fix** = defects; **Improve** = tuning worth doing in v2. All prompts move to structured outputs (Pydantic schemas, no fence-stripping) — that global fix isn't repeated below.

### A.1 — P1: Meal extraction (legacy `search_recipes_node`, ~line 254)
- **Keep:** the basic job — free text → list of distinct meal intents; returning `[]` when nothing is found (drives the "what would you like to make?" reprompt).
- **Fix:** legacy loses vague intents — "some kind of salmon dish" gets flattened into an invented specific recipe name, silently narrowing the search. Schema should be `{meals: [{query: str, verbatim: str, is_specific: bool}]}`: `query` is a *search-friendly phrase* preserving vagueness ("salmon dinner"), `verbatim` is the user's words for display as the meal section header.
- **Improve:** strip scheduling/quantity chatter ("tacos **on Friday**", "for 6 people") from queries but don't error on it; extract inline URLs into the same schema (`{url}` meal entries) instead of legacy's separate all-or-nothing URL branch, which skipped search entirely whenever any URL appeared; ignore non-food content in mixed messages.

### A.2 — P2: Saved-recipe relevance filter (legacy `_search_mealie`, ~line 352)
- **Keep:** the strictness instruction and the three calibration examples (tikka = match; "Spaghetti Carbonara" for "pasta carbonara" = match, same dish different pasta; "Coconut Fish and Tomato Bake" for "farro tomato bake" = no match). These encode real taste and survived use.
- **Fix:** legacy matches LLM output back to recipes **by name string equality** — duplicate titles, case drift, or the LLM paraphrasing a title silently drops results. Pass indexed candidates and return indices: `{relevant_indices: [int]}`.
- **Improve:** include each candidate's key ingredients (available from our own store, unlike Mealie's search response) so relevance judgment isn't title-only; add a borderline third state is unnecessary — keep binary, but instruct that for a *vague* query (`is_specific=false` from P1) matching should loosen to "plausible fits" rather than "same dish".

### A.3 — P3: Listicle/roundup filter (legacy `filter_web_results`, ~line 122)
- **Keep:** the exclude taxonomy (roundups, listicles, category pages, non-recipe articles) — it targets the right junk.
- **Fix:** same identity bug as A.2 — filters by returned title strings; return indices. Also legacy classifies on **title alone**; the URL slug is often the stronger signal (`/recipes/chicken-tikka-masala/` vs `/best-taco-recipes/`, numbers in slugs). Pass `{title, url, snippet}` per candidate.
- **Improve:** add a zero-cost regex prefilter before the LLM call (titles starting `\d+ (Best|Easy|…)` are auto-dropped) so the LLM only judges ambiguous cases; with a structured search API (Brave/Serper) results are cleaner than DuckDuckGo scraping, so expect this filter to do less work — measure via the T4 eval fixtures before adding complexity.

### A.4 — P4: Batched product extraction (legacy `_batch_extract_products` ~line 629, and per-item fallback ~line 676)
The highest-value legacy prompt. Note v2 changes its input: it receives **parsed, consolidated lines** (`{quantity, unit, food, note}` per FR-9/10), not raw ingredient strings.
- **Keep:** all the domain heuristics, which encode real shopping knowledge: package-vs-recipe quantity reasoning ("6 scallions → 1 bunch", "3 cloves garlic → 1 head", "2 eggs → 1 carton"); canned-beans-by-default unless "dried"; "fresh X" prefixing for produce; multi-product expansion ("salt and pepper" → two products; "cilantro, parsley, or mint" → all options); the extensive UK→US translation table (courgette/aubergine/caster sugar/double cream/prawns/mince…).
- **Fix:** (1) The legacy batch prompt keys its output on **raw ingredient strings** — any whitespace/case drift breaks the join and silently falls back to per-item calls; use indexed input/output. (2) The rich rules (UK→US table, per-category package logic) exist **only in the per-item fallback prompt**, while the batch prompt has a thin summary — the primary path ran with the weaker rules. Define one shared rules block used by both batch and fallback so they can't drift.
- **Improve:** since input is now parsed, add unit-aware package math ("2 lb chicken thighs" → search "chicken thighs", note target ~2 lb so ranking can prefer the right package size — emit an optional `target_size` field); handle "to taste"/garnish quantities (always 1 package); consider a `confidence` field per item so low-confidence extractions get visually flagged in the cart-review UI; keep the per-item fallback (P4-single) but only as the retry path after a failed batch validation.

### A.5 — P5: Product-match ranking (legacy `_process_cart_item` pick prompt, ~line 822)
- **Keep:** the anti-multipack rules (single can over 4-pack unless qty ≥ 4; avoid "BIG DEAL"/"Value Pack"/"Family Size"); "actual ingredient, not a prepared food or seasoning containing it"; fresh-over-processed for produce; the disambiguation examples ("green onions ≠ noodles or dips", "fresh mint ≠ gum").
- **Fix:** (1) Legacy returns "ONLY the number" parsed with `int()` — any prose breaks it; structured output. (2) Legacy shows the LLM only description + size; v2 must include **price** (unit-price reasoning: a $1.19 can vs a $6 six-pack) and department/category. (3) **Return a ranked top-4, not a single pick** — v2's cart review needs up to 3 alternatives per line (FR-15/§7.4), and one call should produce both the match and its alternatives: `{ranked: [{index, reason}], none_acceptable: bool}`.
- **Improve:** pass P4's `target_size` when present so the ranking prefers the right package size; add a `none_acceptable` escape hatch (legacy always picked *something*, even absurd matches — better to surface "no good match, search manually" in the review UI); stay brand-neutral (no organic/premium bias unless the ingredient says so).

### A.6 — P4a: Ingredient-line parsing (new in v2, no legacy equivalent)
Legacy passed raw strings end to end; v2 parses lines into `{quantity, unit, food, note}` (FR-9) to enable consolidation. New prompt (or use `recipe-scrapers`' parsed data when present + LLM only for unparsed lines). Batch per recipe, indexed output. Normalize food names to a canonical singular lowercase form (drives consolidation and pantry matching) while retaining the raw line.

### A.7 — Heuristic: candidate dedup (legacy `search_recipes_node`, ~line 289)
- **Fix:** legacy dedupes by URL **or lowercase name across all sources** — two different sites' "Chicken Tikka Masala" collapse to one, discarding a legitimately different recipe. Dedupe by normalized URL, then by (name, domain).
- **Keep:** source-priority ordering (saved > favorite sites > web) when collapsing true duplicates.

### A.8 — Heuristic: stock/substitution fallback (legacy `_process_cart_item`, ~line 852)
- **Keep:** the overall shape — walk the ranked list, require fulfillment availability, prefer explicit stock levels (HIGH/LOW/MEDIUM), hold unknown-stock items as fallback, mark anything that isn't the first choice as a substitution. This logic is sound and battle-tested; port it as deterministic code operating on P5's ranked output.
- **Improve:** distinguish `substituted` (different product chosen) from `stock_unknown` (first choice, but no stock data) — legacy conflated them, which overstates substitutions in the report; both get distinct pills in the cart-review UI.

### A.9 — Heuristics: retired outright
- DuckDuckGo result-string regex parsing (`link:/title:/snippet:` scraping) — replaced by the structured `SearchProvider` (PRD §7.3).
- og:image extraction via regex over raw HTML — replaced with a proper HTML parser in T4 (same 200KB-cap streaming idea is fine to keep).
- Sequential per-favorite-site search loop — favorite sites query concurrently under the semaphore.
- Mealie URL import (`create_recipe_from_url`) — replaced by T3's scraper.
- The legacy pantry **substring** matching in `remy-api` — the word-boundary version is the one specified (FR-11), applied to the parsed food name rather than the raw line.
