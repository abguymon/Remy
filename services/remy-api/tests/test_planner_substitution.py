"""Unit tests for the deterministic stock/fulfillment substitution walk (A.8)."""

from remy_api.kroger.models import Product, StockLevel
from remy_api.planner.substitution import MatchStatus, select_product


def _p(upc, stock=StockLevel.UNKNOWN, pickup=True):
    return Product(upc=upc, description=upc, stock_level=stock, pickup=pickup)


def test_top_pick_in_stock_is_matched():
    sel = select_product([_p("a", StockLevel.HIGH), _p("b", StockLevel.LOW)], fulfillment="pickup")
    assert sel.status == MatchStatus.MATCHED
    assert sel.chosen.upc == "a"
    assert [alt.upc for alt in sel.alternatives] == ["b"]


def test_out_of_stock_top_pick_substitutes_next_in_stock():
    ranked = [_p("a", StockLevel.TEMPORARILY_OUT_OF_STOCK), _p("b", StockLevel.HIGH)]
    sel = select_product(ranked, fulfillment="pickup")
    assert sel.status == MatchStatus.SUBSTITUTED
    assert sel.chosen.upc == "b"


def test_top_pick_unknown_stock_is_stock_unknown_not_substituted():
    sel = select_product([_p("a", StockLevel.UNKNOWN), _p("b", StockLevel.UNKNOWN)], fulfillment="pickup")
    assert sel.status == MatchStatus.STOCK_UNKNOWN
    assert sel.chosen.upc == "a"


def test_no_fulfillment_eligible_is_not_found():
    p = Product(upc="a", description="a", stock_level=StockLevel.HIGH, pickup=False, delivery=True, instore=True)
    sel = select_product([p], fulfillment="pickup")
    assert sel.status == MatchStatus.NOT_FOUND
    assert sel.chosen is None


def test_missing_fulfillment_data_is_not_excluded():
    # Kroger omitted fulfillment entirely (all flags false) — don't disqualify.
    p = Product(upc="a", description="a", stock_level=StockLevel.HIGH, pickup=False, delivery=False, instore=False)
    sel = select_product([p], fulfillment="pickup")
    assert sel.status == MatchStatus.MATCHED
    assert sel.chosen.upc == "a"


def test_confirmed_stock_preferred_over_earlier_unknown():
    ranked = [_p("a", StockLevel.UNKNOWN), _p("b", StockLevel.MEDIUM)]
    sel = select_product(ranked, fulfillment="pickup")
    assert sel.status == MatchStatus.SUBSTITUTED
    assert sel.chosen.upc == "b"


def test_empty_ranked_is_not_found():
    """When P5 returns none_acceptable, _rank yields [] and the walk must produce
    not_found (no chosen product) so the review UI offers a manual search."""
    sel = select_product([], fulfillment="pickup")
    assert sel.status == MatchStatus.NOT_FOUND
    assert sel.chosen is None
    assert sel.alternatives == []
