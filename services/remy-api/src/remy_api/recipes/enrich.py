"""Ingredient sections and author-written unit conversions from a recipe page.

Two things the schema.org data alone loses:

- **Sections** ("For the dough:", "For the icing:"). ``recipe-scrapers``
  exposes them as ingredient groups.
- **The author's own conversion** of each line into the other unit system
  ("245 g milk" ↔ "1 cup milk"). WP Recipe Maker, which most food blogs use,
  embeds both systems in ``window.wprm_recipes``; we keep the one that isn't
  the saved line as ``alt_raw`` so the app can show the author's numbers
  instead of computing its own.

Both are best-effort: anything missing or ambiguous yields ``None`` for that
line, never a guess.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence

logger = logging.getLogger("remy.recipes.enrich")

_METRIC_UNITS = {
    "g",
    "gram",
    "grams",
    "kg",
    "ml",
    "l",
    "liter",
    "liters",
    "litre",
    "litres",
    "milliliter",
    "milliliters",
}
_US_UNITS = {
    "cup",
    "cups",
    "tsp",
    "tbsp",
    "teaspoon",
    "teaspoons",
    "tablespoon",
    "tablespoons",
    "oz",
    "ounce",
    "ounces",
    "lb",
    "lbs",
    "pound",
    "pounds",
    "pint",
    "pints",
    "quart",
    "quarts",
    "fl oz",
}


def _norm(text: str) -> str:
    """Comparison key for an ingredient line: lowercase alphanumerics only."""
    return re.sub(r"[^a-z0-9½¼¾⅓⅔⅛]+", " ", text.lower()).strip()


def align_sections(lines: Sequence[str], groups: Sequence[tuple[str | None, Sequence[str]]]) -> list[str | None]:
    """Section heading for each of ``lines``, from (purpose, group lines) groups.

    Returns all ``None`` when there's only one unnamed group, or when the groups
    don't account for the lines (so a mismatch never mislabels anything).
    """
    if not groups or (len(groups) == 1 and not groups[0][0]):
        return [None] * len(lines)
    by_key: dict[str, list[str | None]] = {}
    for purpose, items in groups:
        heading = (purpose or "").strip() or None
        for item in items:
            by_key.setdefault(_norm(item), []).append(heading)
    out: list[str | None] = []
    for line in lines:
        queue = by_key.get(_norm(line))
        if not queue:
            return [None] * len(lines)
        out.append(queue.pop(0))
    return out


def _wprm_recipe(html: str) -> dict | None:
    """The first recipe object from ``window.wprm_recipes = {...}``, if present."""
    m = re.search(r"wprm_recipes\s*=\s*", html)
    if not m:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(html, m.end())
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    for value in data.values():
        if isinstance(value, dict) and isinstance(value.get("ingredients"), list):
            return value
    return None


def _system_of(unit: str) -> str | None:
    u = unit.strip().lower().rstrip(".")
    if u in _METRIC_UNITS:
        return "metric"
    if u in _US_UNITS:
        return "us"
    return None


def _line(amount: str, unit: str, name: str, notes: str) -> str:
    text = " ".join(p for p in (amount.strip(), unit.strip(), name.strip()) if p)
    notes = notes.strip()
    return f"{text} ({notes})" if notes else text


def wprm_alternates(html: str, lines: Sequence[str]) -> list[str | None]:
    """The author's other-system version of each of ``lines``, from WP Recipe Maker.

    Matched by ingredient position and checked by name; any line that can't be
    matched confidently gets ``None``.
    """
    recipe = _wprm_recipe(html)
    if recipe is None:
        return [None] * len(lines)
    items = [i for i in recipe["ingredients"] if isinstance(i, dict) and i.get("type", "ingredient") == "ingredient"]
    if len(items) != len(lines):
        logger.info("wprm ingredient count %d != parsed %d; skipping conversions", len(items), len(lines))
        return [None] * len(lines)

    out: list[str | None] = []
    for item, line in zip(items, lines, strict=True):
        name = str(item.get("name") or "")
        if not name or _norm(name) not in _norm(line):
            out.append(None)
            continue
        primary_system = _system_of(str(item.get("unit") or ""))
        alt: str | None = None
        for conv in (item.get("converted") or {}).values():
            if not isinstance(conv, dict):
                continue
            unit = str(conv.get("unit") or "")
            amount = str(conv.get("amount") or "")
            system = _system_of(unit)
            # Only a real conversion into the *other* system is worth keeping.
            if amount and system and system != primary_system:
                alt = _line(amount, unit, name, str(item.get("notes") or ""))
                break
        out.append(alt)
    return out


# --- Backfill for recipes saved before sections/conversions were captured -----


async def backfill_recipe(recipe, *, dry_run: bool = False) -> tuple[int, str]:  # noqa: ANN001 - Recipe model
    """Fill ``section``/``alt_raw`` on a saved recipe's lines from its source page.

    Only lines whose text still matches the page are touched, and only fields
    that are empty — a user's edits are never overwritten. Returns
    ``(lines updated, status)``; the caller commits.
    """
    from remy_api.recipes.llm_fallback import RecipeParseError
    from remy_api.recipes.scraper import fetch_page, parse_with_scrapers

    if not recipe.source_url:
        return 0, "no source URL"
    try:
        html = await fetch_page(recipe.source_url)
        parsed = parse_with_scrapers(html, recipe.source_url)
    except RecipeParseError as exc:
        return 0, f"fetch failed ({exc.message})"
    except Exception as exc:  # noqa: BLE001 - malformed pages raise many types
        return 0, f"parse failed ({type(exc).__name__})"

    found: dict[str, tuple[str | None, str | None]] = {}
    for ing in parsed.ingredients:
        found.setdefault(_norm(ing.raw), (ing.section, ing.alt_raw))
    if not any(section or alt for section, alt in found.values()):
        return 0, "page has no sections or conversions"

    updated = 0
    for line in recipe.ingredients:
        match = found.get(_norm(line.raw))
        if match is None:
            continue
        section, alt = match
        changed = False
        if section and not line.section:
            if not dry_run:
                line.section = section
            changed = True
        if alt and not line.alt_raw:
            if not dry_run:
                line.alt_raw = alt
            changed = True
        updated += changed
    return updated, "ok" if updated else "nothing to add"
