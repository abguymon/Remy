# Remy v2 — T9 Live Verification

Date: 2026-07-09
Branch: `v2`
Verifier: automated live pass (T9)
Stack under test: `remy-api` :8080 (real OpenAI `gpt-4o`, `SEARCH_PROVIDER=llm`, real Kroger client-credentials), `remy-web` :3000, SQLite dev DB.

## Summary

| # | Criterion | Result | Notes |
|---|-----------|--------|-------|
| 1 | Fresh compose / login / connect / store / PICKUP | PASS (config-level) | `docker compose config` parses; 2 services; images built. Did **not** `docker compose up` (ports in use by dev servers) per T9 scope. |
| 2 | 3 meals → ≤~30s, per-meal progress, ~5 candidates w/ images, saved-first, favorite badges, zero listicles | PASS* | ~14s. Saved-first confirmed. Listicle-free. **Required a fix** (LLM search provider was 100% broken with gpt-4o). Thumbnails partial (cosmetic). |
| 3 | Consolidated list, dup foods merged, pantry separated + re-includable, editable | PASS | garlic merged across 3 recipes (9 cloves); qty edit + free-text add + pantry re-include all work. |
| 4 | Per-line real products (photo/size/price/stock), ≥1 swap to alternative | PASS | Real Kroger products; 28/35 lines have alternatives; swap recomputes total exactly; `manual_search` recovers a not_found line. |
| 5 | Real cart write + truthful report | **NOT EXECUTED — reserved for human.** Plan left READY in `reviewing_cart`. **Kroger must be reconnected first (see incident).** |
| 6 | Selected recipes in cookbook w/ images + ingredients/instructions, searchable | PASS | 3 recipes saved (2/3 w/ image); FTS matches title *and* ingredients. |
| 7 | Resume mid-flow | PASS | Fresh login + fresh browser load both resume `reviewing_cart` with full cart. Survived 4 API restarts (server-persisted). |
| 8 | LLM/search failure → scoped visible errors + retry | PASS | LLM fail → API 502 `llm_error` + UI toast; search fail → scoped `web_search_failed` w/ typed cause; retry after restore works. |
| 9 | Mealie import command | PARTIAL (env-blocked) | CLI wired + 4 unit tests + clean typed error on unreachable host. **No live Mealie instance in this env** (Mealie is decommissioned; real import is the T10 cutover step). **Fixed** raw-traceback error handling. |
| 10 | MCP client completes golden path; execute_cart rejects unknown draft id | PASS | find→select→build→match→swap all work via `/mcp`; `execute_cart` with a fabricated id is rejected before any write; 401 on missing/bad token. |
| 11 | Plan visible/resumable across REST ↔ MCP | PASS | REST plan visible via `plan_status`; MCP-created plan visible via `GET /plan/state`. |

\* PASS after a defect fix made during this pass (see Fixes).

---

## ⚠️ Incident: live dev DB was wiped during this pass (recovered)

**What happened.** The very first action of this pass ran the backend test suite with the deployment env sourced (`DATABASE_URL` exported → `services/remy-api/data/remy-dev.sqlite`). `tests/conftest.py` used `os.environ.setdefault("DATABASE_URL", …)`, so the exported value won and the test session's `drop_all`/`create_all` **reseeded the live dev DB with test fixtures**, destroying the pre-existing `test` user, that user's Kroger OAuth tokens, the selected store, and any pre-existing recipes.

**Recovery performed:**
- Recreated user `test` / `testpass1234` (`python -m remy_api create-user`).
- Re-selected a Fred Meyer store: **`70100135` "Fred Meyer - Hawthorne" (zip 97214)**, fulfillment PICKUP, via a real Kroger client-credential location lookup.
  - Note: network-log evidence shows the human's *original* store was **`70100285` (zip 97005, Beaverton)**. The rebuilt C2–C4 cart was matched against `70100135`; if the human prefers `70100285`, re-select it and re-match before executing.
- Re-ran a full C2–C4 plan; the `test` user is left with a real matched cart in `reviewing_cart` (details below).

**NOT recoverable:** the user's real Kroger **OAuth tokens** (encrypted, gone with the wiped rows). `kroger/status` = `connected:false`. **The human must reconnect Kroger in Settings before the C5 execute step.** (C5 requires a fresh human OAuth anyway.)

**Fix so this cannot recur:** `tests/conftest.py` now **force-assigns** `DATABASE_URL` and `RECIPE_IMAGES_DIR` to throwaway temp paths (no longer `setdefault`), so a sourced deployment env can never point the test session at a real DB. Verified: `pytest` with the live `DATABASE_URL` exported now leaves the dev DB untouched.

---

## Fixes applied during this pass

1. **`services/remy-api/src/remy_api/search/llm_provider.py`** — *blocker for C2.*
   OpenAI web search sent `web_search_options` against the general model (`gpt-4o`), which OpenAI rejects: `"Web search options not supported with this model"`. **Every** web discovery failed (`web_search_failed` on all meals). Fix: for the OpenAI branch, map the model to its `*-search-preview` variant (`gpt-4o` → `gpt-4o-search-preview`, `gpt-4o-mini*` → `gpt-4o-mini-search-preview`, models already containing `search` pass through) and drop the `temperature` param (search-preview models reject it). After fix: discovery returns 5 candidates/meal in ~14s.

2. **`services/remy-api/tests/conftest.py`** — *safety/hardening (the incident fix).* `setdefault` → forced assignment for `DATABASE_URL` and `RECIPE_IMAGES_DIR`.

3. **`services/remy-api/src/remy_api/__main__.py`** — *C9 UX.* `import-mealie` now catches `httpx.HTTPError`/`OSError` and prints a clean `Error: could not reach Mealie at <url>: …` message + exit 1, instead of dumping a raw traceback on an unreachable host.

**Test status after fixes:** backend `146 passed` (ruff clean); frontend `tsc && vite build` green.

## Defects deferred (documented, not fixed)

- **Intermittent MCP-session LLM immediate-timeout.** In one fresh MCP session, `find_recipes` failed 4× consecutively with `litellm.Timeout … time taken=0.0 seconds`, while a direct `litellm` probe, the REST plan path, and an *earlier* MCP session all succeeded. Points at an async/event-loop or connection-pool issue specific to a freshly-initialized MCP streamable-HTTP session. Low frequency; the C10 golden path itself completed. Needs deeper investigation (retry-on-transient in the LLM client would also mask it).
- **Thumbnails often missing** for bot-blocking sources (e.g. seriouseats returns HTTP 403 to the og:image fetch). Cosmetic per FR-4 / §7.3 ("missing thumbnail is cosmetic, never blocking"). No fix.
- **One saved web recipe lacks an image** (masalamonk "Salmon Bowl Recipe" — scraper/og:image yielded none). Cosmetic.

---

## Evidence by criterion

### C1 — Fresh compose (config-level)
- `docker compose config` (with `.env` present) → PARSE OK, 75 lines. Services: `remy-api` (published 8080 → 8080), `remy-web` (published 3000 → 80). Data volume + pantry/recipe_sources seed mounts. **No Mealie, no MCP sidecar services.** Images `confident-dhawan-992d67-remy-api` / `-remy-web` built.
- Not started (`up`) — dev servers hold the ports; T9 scope says config-level only.

### C2 — Discovery
- Input `"chicken tikka masala, salmon bowls, and street tacos"`. Meal extraction: 3 meals; `salmon bowls`/`street tacos` correctly flagged `is_specific=false` (vagueness preserved); `verbatim` retained.
- Timing: `selecting` reached at **t+14s** (POST /plan 3s + background discover). Per-meal progress visible mid-run (`searching:0 searching:0 ready:5` at t+10s).
- 5 candidates/meal. Origins: `favorite` (seriouseats, cookieandkate — from favorite-sites list) and `web` (bonappetit, foodnetwork, thekitchn, masalamonk). **Zero listicles** (spot-checked titles/URLs — all individual recipe pages).
- **Saved-first CONFIRMED:** after recipes were saved, re-running discovery for "chicken tikka masala" returned the saved recipe first as `origin=saved` with `saved_recipe_id`, ahead of favorite/web.
- **Degraded markers work:** the *initial* (pre-fix) run surfaced `status=error, source_errors=['web_search_failed']` on all meals — labeled, never a silent empty.
- Thumbnails: present on some (bonappetit, cookieandkate), absent where the source 403s the fetch (seriouseats). Cosmetic.

### C3 — Shopping list
- 51 lines → 23 to_buy / 28 pantry_skipped. Consolidation: `garlic` merged across all 3 recipes → **9 cloves**; `ginger` (tikka+salmon), `lime juice` (salmon+tacos) merged with summed quantities; `contributing` refs recorded per line.
- Pantry separation visible (garlic, cumin, turmeric, salt, onion, oils, etc.).
- Edits: re-include `onion` (pantry_skipped → to_buy) ✓; `ginger` qty 1.67 → 3 tbsp ✓; free-text `"2 lemons"` added to to_buy ✓. Groups recomputed (28→27 pantry, 23→25 to_buy).

### C4 — Product matching
- Matching completed **t+36s**; 25 lines → 35 search terms (multi-product expansion, e.g. garnish "cilantro/green onion" split). Outcomes: 24 matched, 4 substituted, 3 stock_unknown, 4 not_found. Est. total **$95.22** (progressive, granular per-item status during matching).
- Real products verified: e.g. `fresh ginger → Organic Ginger Root, 1 lb, $3.99, HIGH, pickup=true, image=yes`; `chicken breast → Simple Truth Boneless Skinless, $6.99`; `canned whole peeled tomatoes → Kroger 28 oz, $1.89`. 28/35 lines carry ≥1 alternative.
- Swap: `garam masala $6.49 → $7.79` alternative; total recomputed **95.22 → 96.52** (exact +1.30).
- manual_search: `cardamom pods` (not_found) → search "ground cardamom" → matched `Simple Truth Organic Ground Cardamom Powder $6.99 HIGH`; total → 103.51.
- Honest `warnings: ['kroger_not_connected']` present (product search uses client-credentials; cart write needs user OAuth).

### C5 — Real cart write — RESERVED FOR HUMAN
- **Left READY in `reviewing_cart`.** See "State left for the human" below.
- **Blocked until Kroger reconnected** (tokens lost in the incident).
- `POST /plan/cart/execute` / `execute_cart` / `add_items_to_cart` were **never called** during this pass (the only fake-id `execute_cart` call was the required rejection test — no write).

### C6 — Cookbook
- 3 recipes saved: Chicken Tikka Masala (bonappetit, img), Easy Black Bean Tacos (cookieandkate, img), Salmon Bowl Recipe (masalamonk, no img). Tikka detail: 18 ingredients (raw + parsed), 6 instruction steps, source URL.
- FTS: `?q=tikka`→Tikka, `?q=salmon`→Salmon, `?q=cotija`→Black Bean Tacos (ingredient-level match).
- Verified in cookbook UI (recipe cards + images load via `/api/recipes/{id}/image`).

### C7 — Resume
- Fresh login + `GET /plan/state` → `reviewing_cart`, 35 items, $103.51, same `cart_draft_id`.
- Fresh browser load of :3000 renders the persisted step (app fetches `/plan/state` on mount).
- Plan survived 4 API restarts (DB-persisted checkpoint).

### C8 — Failure drills
- **LLM fail** (`LLM_MODEL=openai/gpt-4o-this-model-does-not-exist`): `POST /plan` → HTTP 502 `{"error":{"code":"llm_error","message":"Language model call failed: … does not exist or you do not have access to it."}}`. **UI toast** shows the same scoped message. No silent success.
- **Search fail** (`SEARCH_PROVIDER=brave`, no key): meal extraction OK, discovery meal → `status=error, source_errors=['web_search_failed']`; log carries the typed cause `"Brave search selected but SEARCH_API_KEY is not set"`. No crash.
- **Retry after restore** (good config): plan succeeds, 5 candidates, no errors.

### C9 — Mealie import
- `import-mealie --dry-run` reaches the Mealie client (httpx) and fails only on DNS — no Mealie instance runs in this env (compose has no Mealie service; §5 decommissions it; real import is a T10 step against production Mealie).
- After fix, clean error: `Error: could not reach Mealie at http://mealie:9000: [Errno -2] Name or service not known. …` (exit 1). Logic covered by 4 passing unit tests (`test_mealie_import.py`).

### C10 — MCP facade golden path
- Auth: no-token → 401, bad-token → 401, valid API token → `initialize` 200 (serverInfo `remy`), 14 tools listed.
- Chain on a fresh plan: `find_recipes` (5 candidates + `plan_draft_id`) → `select_recipes` (url=bonappetit → saved, `reviewing_list`) → `build_shopping_list` (to_buy/pantry_skipped/excluded) → `match_products` (`cart_draft_id`, 7 items, $23.64, rich `product` + `alternatives[].alternative_id`) → `swap_product` (ginger → Spice World alternative, confirmed via REST).
- **`execute_cart` with fabricated `cart_draft_id` "fake-draft-…" → REJECTED**: `"Unknown or stale cart_draft_id. Run match_products …"`. No cart write. Real-id execute never called.

### C11 — Cross-interface visibility
- REST→MCP: the REST-created `test` plan is returned by MCP `plan_status` (`reviewing_cart`, 35 items, $103.51, matching `cart_draft_id`).
- MCP→REST: the MCP-created `verify` plan is returned by `GET /plan/state` (`reviewing_cart`, `cart_draft_id fb972…`, 7 items, $23.64).

---

## State left for the human (C5)

- **User:** `test` / `testpass1234`
- **Plan:** `b84dc909-ce83-4595-bc95-e183ba428762`, status `reviewing_cart` — **READY, awaiting human execute.**
- **Cart draft id:** `0ad8a81d0ed9436f8ce4035cbad15db5`
- **Store:** Fred Meyer - Hawthorne `70100135` (zip 97214), fulfillment PICKUP.
- **Cart:** 35 lines — 24 matched, 4 substituted, 3 stock_unknown, 4 not_found. **31 buyable lines** (matched/substituted/stock_unknown with a chosen product). **Estimated total ≈ $103.51.**
- **BEFORE executing (required):** reconnect Kroger in Settings (OAuth) — `kroger/status` is currently `connected:false` (tokens lost in the incident). Optionally re-select the original store `70100285`/zip 97005 and re-match if the human wants Beaverton rather than Hawthorne.
- To execute: in the web UI confirm the cart at the "Review cart" step, **or** `POST /plan/cart/execute` (JWT), **or** MCP `execute_cart` with the real `cart_draft_id`.

### Test artifacts left behind (harmless)
- Extra user `verify` / `verifypass1234` (used for destructive drills; abandoned plan).
- Fixture users `owner` / `other` (from the errant test run).
- API tokens named `t9-verify` (test) and `v-mcp` (verify).
