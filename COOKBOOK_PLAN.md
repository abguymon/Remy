# Cookbook Plan — turning the Cookbook tab into a real recipe library

Status: **v1 built** (2026-10-04, branch `rebrand`): items 1–5 plus the app-wide visual rebrand and dark mode (item 9). v2 items 6–8 remain.

## Why

Mealie was removed in v2 (PRD §5) and Remy now owns the recipe store. We
looked at off-the-shelf replacements (Mealie, Tandoor, Norish, KitchenOwl,
Mela) and none has both a UI we like and Remy's plan → Kroger cart flow.
Rather than run a second recipe app beside Remy, we fill the library gaps in
Remy itself and give the browse screens a proper design pass.

## What Remy already has

- URL import (`recipe-scrapers` + LLM fallback) and photo/PDF import (vision)
- Parsed ingredient lines (quantity / unit / food) feeding the shopping list
- FTS5 search over titles and ingredients
- Edit, delete, "I cooked this" (`last_cooked_at`)
- Planning → consolidated list → Kroger cart (neither Mealie nor Norish does this)
- MCP facade / API tokens, multi-user with invites and admin
- Design system: Newsreader serif + Hanken Grotesk, terracotta on cream (`DESIGN_BRIEF.md`)

## Gaps vs Mealie / Norish

| # | Gap | Mealie | Norish | Notes |
|---|---|---|---|---|
| 1 | **Cook mode** — one step at a time, large type, screen wake lock, the ingredients each step uses, timers | ✓ | ✓ | Biggest day-to-day win |
| 2 | **Serving scaling + unit conversion** (½×, 2×, metric ↔ US) | ✓ | ✓ | Cheap: ingredients are already parsed |
| 3 | **Tags / categories / collections** ("weeknight", "Thanksgiving") + filters | ✓ | ✓ | Library is hard to browse past ~50 recipes without them |
| 4 | **Favorites, ratings, personal notes** ("used half the salt") | ✓ | partial | DESIGN_BRIEF §7 deferred these from v1 |
| 5 | **Browse views** — recently added, cook again, haven't made in a while, sort/filter by time | partial | partial | Uses the existing `last_cooked_at` |
| 6 | **Video import** (TikTok / Reels / YouTube Shorts) | ✗ | ✓ | Existing vision LLM path could handle it |
| 7 | **Meal-plan calendar** ("what's for dinner Tuesday") | ✓ | ✓ | Remy plans a shop, not a week |
| 8 | **Export / backup** (JSON, schema.org Recipe) + print view | ✓ | ✗ | Keeps data portable |
| 9 | **Dark mode** | ✓ | ✓ | DESIGN_BRIEF §7 excluded it; kitchens at night want it |
| 10 | Standalone shared grocery list (live-synced) | ✓ | ✓ (realtime) | Overlaps the Kroger flow |
| 11 | Nutrition / allergens | ✓ | ✓ (AI) | Low value |
| — | Household-shared cookbook | ✓ | ✓ | **Decided: not now** — see below |

## Scope

- **v1:** items 1–5. Turns the Cookbook tab into a library. Backend work is
  small (tag + favorite tables, a rating and notes field on `Recipe`, a few
  list/filter params); most of the work is frontend.
- **v2:** items 6–9.
- **Skip unless missed:** items 10–11.

## Decisions

- **Cookbooks stay per-user** (`Recipe.user_id`, as today). No household
  sharing for now; revisit if it becomes annoying. Keep new tables (tags,
  favorites, notes) user-scoped too so a later move to household ownership is
  a single migration, not a redesign.
- **Evolve the existing design system, don't replace it.** Same fonts, palette
  and component seeds from `DESIGN_BRIEF.md`; the redesign targets the browse
  register (Cookbook, Recipe detail) plus the new cook mode.

## Design pass (next step)

Screens to mock up before building:

1. **Library home** — shelves (Cook again · Recently added · Quick weeknight ·
   Favorites), tag filter chips, search, sort.
2. **Recipe detail** — serving scaler and unit toggle on the ingredient list,
   tags, rating/favorite, personal notes, "Start cooking" as the primary action.
3. **Cook mode** — full-screen, step-at-a-time, per-step ingredients, tap-to-
   start timers parsed from step text, wake lock, swipe/arrow navigation.
4. **Tag / collection management** — add/remove tags inline on a recipe;
   collection view.
5. **Dark theme** tokens for all of the above (v2, but design tokens now).

The PRD stays the source of truth for the plan/cart flow; once designed, the
new FRs from this doc should be folded into `PRD.md` and `DESIGN_BRIEF.md`.
