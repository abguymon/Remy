"""Deterministic shopping-list consolidation and pantry bypass (FR-10, FR-11).

Pure functions, no I/O — unit-tested in isolation. Two concerns:

* **Consolidation (FR-10):** parsed ingredient lines that share a normalized
  ``food`` are merged into one list line. Quantities in *compatible* units are
  summed (a small unit table covers volume tsp/tbsp/cup, imperial weight oz/lb,
  metric weight g/kg, and bare counts); *incompatible* units are kept as separate
  segments and both are shown ("1 lb + 2 clove"). Each merged line records which
  recipes contributed.
* **Pantry bypass (FR-11):** a staple matches a line when a pantry term appears
  in the parsed ``food`` on a **word boundary** (the legacy word-boundary regex,
  not the bidirectional-substring version). "salt" matches "salt and pepper";
  "ice" does NOT match "sliced".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- Unit table --------------------------------------------------------------
# Each known unit maps to (family, factor-to-base). Units in the same family are
# summed after converting to the family's base unit; different families are
# incompatible and kept split. Unknown units become their own family keyed by the
# unit string, so "2 clove" + "1 clove" sum but "clove" + "can" stay split.

_VOLUME = "volume"  # base: tsp
_WEIGHT_IMPERIAL = "weight_imperial"  # base: oz
_WEIGHT_METRIC = "weight_metric"  # base: g
_COUNT = "count"  # unit-less count

_UNIT_TABLE: dict[str, tuple[str, float]] = {
    # volume (base tsp)
    "tsp": (_VOLUME, 1.0),
    "teaspoon": (_VOLUME, 1.0),
    "teaspoons": (_VOLUME, 1.0),
    "tbsp": (_VOLUME, 3.0),
    "tbs": (_VOLUME, 3.0),
    "tablespoon": (_VOLUME, 3.0),
    "tablespoons": (_VOLUME, 3.0),
    "cup": (_VOLUME, 48.0),
    "cups": (_VOLUME, 48.0),
    # weight, imperial (base oz)
    "oz": (_WEIGHT_IMPERIAL, 1.0),
    "ounce": (_WEIGHT_IMPERIAL, 1.0),
    "ounces": (_WEIGHT_IMPERIAL, 1.0),
    "lb": (_WEIGHT_IMPERIAL, 16.0),
    "lbs": (_WEIGHT_IMPERIAL, 16.0),
    "pound": (_WEIGHT_IMPERIAL, 16.0),
    "pounds": (_WEIGHT_IMPERIAL, 16.0),
    # weight, metric (base g)
    "g": (_WEIGHT_METRIC, 1.0),
    "gram": (_WEIGHT_METRIC, 1.0),
    "grams": (_WEIGHT_METRIC, 1.0),
    "kg": (_WEIGHT_METRIC, 1000.0),
    "kilogram": (_WEIGHT_METRIC, 1000.0),
    "kilograms": (_WEIGHT_METRIC, 1000.0),
}

# For rendering a base amount back to a friendly unit: (unit, factor) largest first.
_RENDER_LADDER: dict[str, list[tuple[str, float]]] = {
    _VOLUME: [("cup", 48.0), ("tbsp", 3.0), ("tsp", 1.0)],
    _WEIGHT_IMPERIAL: [("lb", 16.0), ("oz", 1.0)],
    _WEIGHT_METRIC: [("kg", 1000.0), ("g", 1.0)],
}


def normalize_unit(unit: str | None) -> str | None:
    """Lowercase/strip a unit; ``None``/empty stays ``None`` (a bare count)."""
    if unit is None:
        return None
    u = unit.strip().lower()
    return u or None


def _family_of(unit: str | None) -> str:
    """Return the consolidation family for ``unit``."""
    if unit is None:
        return _COUNT
    known = _UNIT_TABLE.get(unit)
    if known is not None:
        return known[0]
    return f"raw:{unit}"


def _to_base(quantity: float, unit: str | None) -> float:
    if unit is None:
        return quantity
    known = _UNIT_TABLE.get(unit)
    if known is not None:
        return quantity * known[1]
    return quantity  # unknown-unit family: base factor 1


def _fmt_number(value: float) -> str:
    """Trim a float to a tidy string ("2.0" -> "2", "1.50" -> "1.5")."""
    rounded = round(value, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:g}"


def _render_segment(family: str, base_total: float, raw_unit: str | None) -> tuple[str | None, float, str]:
    """Render a summed base amount to (unit, quantity, display) for a family."""
    if family == _COUNT:
        return None, base_total, _fmt_number(base_total)
    if family.startswith("raw:"):
        unit = raw_unit or family[4:]
        return unit, base_total, f"{_fmt_number(base_total)} {unit}"
    ladder = _RENDER_LADDER[family]
    for unit, factor in ladder:
        if base_total >= factor:
            qty = base_total / factor
            return unit, qty, f"{_fmt_number(qty)} {unit}"
    # Smaller than the smallest ladder unit: use the smallest unit.
    unit, factor = ladder[-1]
    qty = base_total / factor
    return unit, qty, f"{_fmt_number(qty)} {unit}"


# --- Data shapes -------------------------------------------------------------


@dataclass
class ParsedContribution:
    """One parsed ingredient line feeding consolidation."""

    recipe_id: str
    recipe_title: str
    raw: str
    food: str
    quantity: float | None = None
    unit: str | None = None
    note: str | None = None


@dataclass
class Segment:
    unit: str | None
    quantity: float | None
    display: str


@dataclass
class ConsolidatedLine:
    food: str
    segments: list[Segment]
    display: str
    # Primary quantity/unit (largest summable segment) — what product matching uses.
    quantity: float | None
    unit: str | None
    note: str | None
    conflict: bool
    contributing: list[ParsedContribution] = field(default_factory=list)


def _normalize_food(food: str | None, raw: str) -> str:
    f = (food or "").strip().lower()
    return f or raw.strip().lower()


def consolidate(contributions: list[ParsedContribution]) -> list[ConsolidatedLine]:
    """Merge parsed lines sharing a normalized ``food`` (FR-10).

    Grouping preserves first-seen order. Within a group, quantities are summed per
    unit family; a line with no quantity contributes to an "unquantified" segment
    (shown as just the food, no number). Multiple segments => ``conflict`` and a
    "A + B" display.
    """
    groups: dict[str, list[ParsedContribution]] = {}
    order: list[str] = []
    for c in contributions:
        key = _normalize_food(c.food, c.raw)
        c.food = key
        c.unit = normalize_unit(c.unit)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)

    lines: list[ConsolidatedLine] = []
    for key in order:
        members = groups[key]
        # Sum base amounts per family; track a bare-count of unquantified lines.
        family_totals: dict[str, float] = {}
        family_raw_unit: dict[str, str | None] = {}
        family_first_order: dict[str, int] = {}
        unquantified = 0
        seq = 0
        for m in members:
            if m.quantity is None:
                unquantified += 1
                continue
            fam = _family_of(m.unit)
            family_totals[fam] = family_totals.get(fam, 0.0) + _to_base(m.quantity, m.unit)
            family_raw_unit.setdefault(fam, m.unit)
            if fam not in family_first_order:
                family_first_order[fam] = seq
                seq += 1

        segments: list[Segment] = []
        # Emit summed segments in first-seen family order.
        for fam in sorted(family_totals, key=lambda f: family_first_order[f]):
            unit, qty, disp = _render_segment(fam, family_totals[fam], family_raw_unit.get(fam))
            segments.append(Segment(unit=unit, quantity=qty, display=disp))
        # An unquantified segment (e.g. "salt to taste") shows just the food.
        if unquantified and not segments:
            segments.append(Segment(unit=None, quantity=None, display=key))

        # Pick a primary segment (largest base among summable) for product matching.
        primary_unit: str | None = None
        primary_qty: float | None = None
        if family_totals:
            primary_fam = max(family_totals, key=lambda f: family_totals[f])
            primary_unit, primary_qty, _ = _render_segment(
                primary_fam, family_totals[primary_fam], family_raw_unit.get(primary_fam)
            )

        conflict = len(segments) > 1
        if segments and not (len(segments) == 1 and segments[0].display == key):
            # e.g. "2 cup + 1 clove garlic"; the unquantified-only case shows bare food.
            display = f"{' + '.join(s.display for s in segments)} {key}"
        else:
            display = key

        note = next((m.note for m in members if m.note), None)
        lines.append(
            ConsolidatedLine(
                food=key,
                segments=segments,
                display=display,
                quantity=primary_qty,
                unit=primary_unit,
                note=note,
                conflict=conflict,
                contributing=members,
            )
        )
    return lines


# --- Pantry bypass (FR-11) ---------------------------------------------------


def _compile_pantry(pantry_items: list[str]) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for item in pantry_items:
        term = (item or "").strip().lower()
        if not term:
            continue
        patterns.append(re.compile(rf"\b{re.escape(term)}\b"))
    return patterns


def matches_pantry(food: str, pantry_patterns: list[re.Pattern[str]]) -> bool:
    """True if any pantry term matches ``food`` on a word boundary (FR-11)."""
    target = (food or "").strip().lower()
    if not target:
        return False
    return any(p.search(target) for p in pantry_patterns)


def classify_pantry(foods: list[str], pantry_items: list[str]) -> dict[str, bool]:
    """Map each food -> True if it is a pantry staple (word-boundary match)."""
    patterns = _compile_pantry(pantry_items)
    return {food: matches_pantry(food, patterns) for food in foods}
