"""Unit tests for deterministic consolidation, the unit table, and pantry match."""

from remy_api.planner.consolidation import (
    ParsedContribution,
    classify_pantry,
    consolidate,
    matches_pantry,
)
from remy_api.planner.consolidation import _compile_pantry as compile_pantry


def _c(food, qty=None, unit=None, recipe="r1", title="R1", raw=None, note=None):
    return ParsedContribution(
        recipe_id=recipe, recipe_title=title, raw=raw or food, food=food, quantity=qty, unit=unit, note=note
    )


def test_merges_same_food_counts():
    lines = consolidate([_c("onion", 1, None, recipe="a"), _c("onion", 2, None, recipe="b")])
    assert len(lines) == 1
    line = lines[0]
    assert line.food == "onion"
    assert line.quantity == 3
    assert line.unit is None
    assert not line.conflict
    assert {c.recipe_id for c in line.contributing} == {"a", "b"}


def test_sums_compatible_volume_units():
    # 1 tbsp (3 tsp) + 3 tsp = 6 tsp = 2 tbsp
    lines = consolidate([_c("soy sauce", 1, "tbsp"), _c("soy sauce", 3, "tsp")])
    assert len(lines) == 1
    seg = lines[0].segments[0]
    assert seg.unit == "tbsp"
    assert seg.quantity == 2
    assert not lines[0].conflict


def test_sums_cups():
    lines = consolidate([_c("flour", 1, "cup"), _c("flour", 2, "cup")])
    assert lines[0].segments[0].unit == "cup"
    assert lines[0].segments[0].quantity == 3


def test_imperial_weight_sums_to_pounds():
    # 8 oz + 8 oz = 16 oz = 1 lb
    lines = consolidate([_c("beef", 8, "oz"), _c("beef", 8, "oz")])
    assert lines[0].segments[0].unit == "lb"
    assert lines[0].segments[0].quantity == 1


def test_metric_weight_sums_to_kg():
    lines = consolidate([_c("sugar", 600, "g"), _c("sugar", 600, "g")])
    assert lines[0].segments[0].unit == "kg"
    assert lines[0].segments[0].quantity == 1.2


def test_incompatible_units_kept_split_with_both_shown():
    # A pound of garlic and 2 cloves of garlic are incompatible families.
    lines = consolidate([_c("garlic", 1, "lb"), _c("garlic", 2, "clove")])
    assert len(lines) == 1
    line = lines[0]
    assert line.conflict is True
    assert len(line.segments) == 2
    assert "lb" in line.display and "clove" in line.display
    assert line.food in line.display


def test_metric_and_imperial_weight_are_incompatible():
    lines = consolidate([_c("cheese", 1, "lb"), _c("cheese", 100, "g")])
    assert lines[0].conflict is True
    assert len(lines[0].segments) == 2


def test_unquantified_line_shows_bare_food():
    lines = consolidate([_c("salt", None, None, note="to taste")])
    assert lines[0].display == "salt"
    assert lines[0].quantity is None


def test_pantry_word_boundary_matches_whole_word():
    patterns = compile_pantry(["salt", "ice", "olive oil"])
    assert matches_pantry("salt", patterns) is True
    assert matches_pantry("salt and pepper", patterns) is True
    assert matches_pantry("olive oil", patterns) is True


def test_pantry_sliced_does_not_match_ice():
    # The canonical false-positive the legacy substring matcher produced.
    patterns = compile_pantry(["ice"])
    assert matches_pantry("sliced almond", patterns) is False
    assert matches_pantry("sliced avocado", patterns) is False
    assert matches_pantry("ice", patterns) is True


def test_classify_pantry_maps_each_food():
    result = classify_pantry(["salt", "sliced almond", "chicken thigh"], ["salt", "ice", "pepper"])
    assert result == {"salt": True, "sliced almond": False, "chicken thigh": False}
