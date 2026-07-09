# Remy v2 — Design Brief

Companion to `PRD.md`. The PRD defines *what* the product does (functional requirements, data contracts, flow gates); this brief defines *how it should look, feel, and behave on screen*. Where this brief references FR-numbers, the PRD is the source of truth for the data on screen. The deliverable expected from a design pass: high-fidelity mockups (or coded screens) for every screen and state listed in §4, phone-first.

> **Finished design:** a Claude Design project implementing this brief exists at
> https://claude.ai/design/p/2bae85db-fceb-440b-bc18-2d347efa0703?file=Remy.dc.html
> Import it via the `claude_design` MCP server (`https://api.anthropic.com/v1/design/mcp`, authenticate with `/design-login`). When building the frontend, treat the design project as the visual source of truth and this brief as the intent/state checklist behind it.

---

## 1. Product in one line (for design context)

The user types the meals they want to cook this week; Remy shows ~5 recipe options per meal, builds a consolidated shopping list from their picks, matches each item to a real Kroger product with price and photo, fills their Kroger cart, and hands them to kroger.com to check out. Recipes they pick are saved into a personal cookbook.

---

## 2. Design principles

1. **Phone-first, always.** The primary device is a ~390px phone on the couch. Every screen — including the dense cart-review step — must be fully usable one-handed on a phone. Desktop (≥1024px) is the adaptation: grids widen, lists gain columns, nothing appears that phone lacks.
2. **Warm where you browse, utilitarian where you edit.** Two registers, one system:
   - *Browse register* (recipe candidates, cookbook, recipe detail): editorial and appetizing — large photography, generous whitespace, food is the hero.
   - *Edit register* (shopping list review, cart review, settings): dense, crisp, fast — clear checkboxes, tight rows, prices right-aligned, zero decoration competing with decisions.
3. **The flow is a journey with a spine.** One continuous, resumable flow (Plan → Pick recipes → Review list → Review cart → Done) with a persistent, tappable step indicator. The user always knows where they are, what's done, and that leaving is safe (state persists server-side).
4. **Honesty is a UI feature.** Substitutions, out-of-stock items, failed searches, and the fact that the in-app "cart" is a local record (not Kroger's real cart) are surfaced plainly, never buried. Degraded results get labeled banners, not silence (FR-5, FR-16, FR-18).
5. **Never a dead spinner.** Every long operation shows granular, per-unit progress (per-meal search status, per-item matching status). Skeletons and progressive reveal over blocking loaders (PRD §3).

## 3. Visual direction

- **Tone:** warm hybrid. A cookbook that behaves like a well-made tool.
- **Theme:** light only. No dark mode in v1.
- **Color:** warm neutral canvas (cream/off-white, warm grays) — not stark white. One warm accent (terracotta / paprika family — nod to the name Remy) for primary actions and the step indicator; a supporting green for "added/success/in-stock", amber for "substituted/low stock", red only for errors and "unavailable/failed". Product/recipe photography supplies most of the color; the chrome stays quiet.
- **Type:** a friendly serif or serif-adjacent display face for recipe titles and screen headers (editorial warmth); a clean sans for everything interactive and data-dense (lists, prices, buttons, labels). Prices and quantities in tabular figures.
- **Shape & depth:** soft-rounded cards (12–16px radius), hairline borders + subtle shadow; no heavy neumorphism, no glassmorphism.
- **Imagery rules:** recipe images are 4:3 or square, cover-cropped, with a graceful fallback (warm placeholder with a utensil glyph — never a broken-image icon). Product images from Kroger sit on white tiles with padding.
- **Voice:** short, warm, plain. "Couldn't find tortillas at your store — here's the closest match." Never robotic ("ERROR: product_not_found"), never cutesy walls of personality.
- **Accessibility:** WCAG AA contrast on the warm palette (check the terracotta on cream), 44px minimum touch targets, all state colors paired with icons/text (color-blind safe), visible focus states.

---

## 4. Screen inventory

Navigation: bottom tab bar on phone (Plan · Cookbook · Cart · Settings), left sidebar on desktop. The Plan tab is home.

### 4.1 Login
- Minimal: wordmark, username, password, sign in. No registration UI in v1 (single user).
- **States:** error (bad credentials, inline), loading.

### 4.2 Plan — step 0: Meal input
- The emotional start: a warm, inviting prompt ("What are we cooking this week?") over a large free-text field. Accepts prose and/or pasted recipe URLs (FR-1).
- If a plan is already in flight: this screen is replaced by a **resume card** ("You're mid-plan: 3 recipes picked, list not yet reviewed → Continue / Start over"). Start over requires confirm (destructive).
- **States:** first-run empty (brief 3-step explainer of how Remy works), Kroger-not-connected notice (can plan, can't order — links to Settings), submitting.

### 4.3 Plan — step 1: Pick recipes
- Grouped by meal: each meal is a section header ("Chicken tikka masala") with a horizontally swipeable card row on phone (grid on desktop) of up to 5 candidates (FR-2/FR-4).
- Candidate card (browse register): photo dominant, title (2-line clamp), source domain, origin badge (`Saved` / `★ favorite site` / `web`), total time if known. Tap = select (border + check in accent color); long-press or a detail affordance opens source URL preview.
- Per-meal actions: "skip this meal", "use a URL instead" (inline paste field).
- Sticky bottom bar: "Continue with N recipes".
- **States:** per-meal loading (skeleton cards appear as each meal's search completes — meals stream in independently, FR-5), per-meal degraded banner ("Web search failed — showing saved recipes only · Retry"), per-meal empty ("Nothing good found — try rewording or paste a URL"), thumbnail-missing fallback.

### 4.4 Plan — step 2: Review shopping list
- Edit register. Three collapsible groups (FR-11/12): **To buy** (checked by default), **Pantry — skipping** (unchecked, re-includable), and a subtle "excluded by you" area for lines the user unchecks.
- Line row: checkbox · consolidated quantity + food ("2 lb chicken thighs") · contributing-recipe chips or count ("2 recipes" — tap to expand which, and the raw ingredient lines behind the consolidation, FR-9/10).
- Row actions: edit quantity (stepper/inline), delete; list-level "add item" free-text row.
- Sticky bottom bar: "Find products at {store name} →".
- **States:** parsing/consolidating progress (per-recipe), consolidation-conflict display (incompatible units shown as both, e.g. "1 lb + 2 cloves"), empty pantry group (hidden).

### 4.5 Plan — step 3: Review cart (the flagship screen — see §5)
- Edit register, phone-first stacked cards. Per approved line: matched Kroger product with photo, name, size, price, stock status, substitution flag, count stepper, and swap/drop actions (FR-15).
- Sticky summary bar: estimated total (labeled "estimated"), item count, "Add N items to Kroger cart" primary action.
- **States:** per-item matching progress (rows resolve one by one with skeletons — bounded-concurrency matching streams results), per-item `not found` (row offers manual search field), out-of-stock substitution (amber flag "substituted for X — swap?"), matching failed (scoped retry on the row).

### 4.6 Plan — step 4: Done / order report
- Truthful per-item report (FR-16/17): grouped Added ✓ / Substituted ⚠ / Unavailable · Failed ✗, estimated total, and the single most prominent CTA in the app: **"Finish checkout on kroger.com"** (opens kroger.com/cart).
- Explicit honesty copy: "Items are in your Kroger cart. Review, schedule pickup, and pay on kroger.com — Remy can't see or change your cart from here" (FR-18).
- Secondary: "Save & finish" (stamps recipes, ends plan), link to view the saved recipes.
- **States:** partial failure (some items failed — offer retry of failed subset), total failure (clear error + retry).

### 4.7 Cookbook (recipe list)
- Browse register. Search field, then a 2-col photo card grid on phone (FR-19): image, title, source domain, "last cooked" if set.
- "Add recipe" → paste-URL sheet (FR-8) with parse progress and a parsed preview to confirm.
- **States:** empty first-run ("Recipes you pick get saved here automatically — or paste a URL"), search-no-results, parse-failed ("Couldn't read that page — try another URL"; LLM-fallback in progress indicator).

### 4.8 Recipe detail
- Browse register, the most editorial screen: full-bleed image, serif title, meta row (source link, yield, prep/cook time), ingredients list, numbered instructions (FR-19).
- Actions: edit fields (FR-8), delete (confirm), "I cooked this" (stamps last_cooked_at, FR-20), open original.

### 4.9 Cart (local record)
- Shows the running local record of what Remy has added, latest order report, order history (FR-17).
- Permanently labeled: "Remy's record — your real cart lives on kroger.com" + link (FR-18). Do **not** style this like a live cart.
- **States:** empty ("Nothing ordered yet"), history list.

### 4.10 Settings
- Grouped sections (FR-21–24, FR-26): **Kroger account** (connect/disconnect with status pill; OAuth returns with `?kroger=connected|error` — show a toast on return), **Store** (ZIP search → result list with address/distance → selected store card; fulfillment PICKUP/DELIVERY segmented control), **Pantry staples** (chip field, add/remove, "reset to defaults"), **Favorite recipe sites** (ordered domain list, add/remove/reorder), **API tokens** (list, create → show-once token modal, revoke).
- **States:** Kroger connect error (with reason), ZIP no-results, token show-once emphasis.

### 4.11 System-level states
- Global error toast pattern for typed API errors; every failure names the failed unit and offers a scoped retry (PRD §3).
- Session expiry → login with return-to.
- 404 → simple warm "nothing here" page.

---

## 5. The flagship problem: cart review on a phone

This is the densest screen and the reason the web UI exists; design it first and let its patterns set the edit register.

- **Stacked cards, not a table.** Each line: product thumbnail (left, white tile) · product name + size · price (right-aligned, tabular) · stock/substitution pill · count stepper · overflow row: **Swap** and **Remove**.
- **Swap is an inline expander (bottom sheet acceptable), not a new page.** Tapping Swap reveals the up-to-3 alternatives (FR-15) as compact selectable rows (thumb, name, size, price) plus "search for something else". Selecting collapses the expander and updates the line with a brief highlight.
- **Substitution lines self-explain:** amber pill "substituted — wanted: {original term}", with Swap pre-suggested.
- **The estimated total is always visible** in the sticky bar and updates live on every swap/count/drop.
- **Desktop adaptation:** the same cards become a comfortable single-column list max-width ~720px, or a two-column grid — do not redesign into a spreadsheet table; keep one component.
- **Scale target:** must stay scannable at 25–30 lines. Consider grouping by department/aisle (data available from Kroger product results) as a stretch — flat list is acceptable for v1.

---

## 6. Component inventory (design-system seeds)

Step indicator (5 steps, tappable-back) · recipe candidate card + skeleton · origin badge · list line row (checkbox/qty/chips) · product line card + skeleton · alternative row · status pills (in stock / low / substituted / unavailable / failed) · sticky action bar with total · chip input (pantry/sites) · degraded-result banner with retry · confirm dialog (destructive) · toast · empty-state block (illustration-light: warm glyph + one line + one action).

---

## 7. Out of scope for design v1

Dark mode; native app chrome; weekly calendar views; dietary/budget UI; ratings/notes on recipes; multi-user account switching (schema supports it later — leave no UI for it now).
