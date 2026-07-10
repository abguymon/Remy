"""Banner → cart-URL mapping (single source of truth for the handoff link)."""

from __future__ import annotations

import pytest

from remy_api.kroger import DEFAULT_CART_URL, banner_cart_url


@pytest.mark.parametrize(
    ("chain", "expected"),
    [
        ("FRED", "https://www.fredmeyer.com/cart"),
        ("QFC", "https://www.qfc.com/cart"),
        ("RALPHS", "https://www.ralphs.com/cart"),
        ("KINGSOOPERS", "https://www.kingsoopers.com/cart"),
        ("FRYS", "https://www.frysfood.com/cart"),
        ("SMITHS", "https://www.smithsfoodanddrug.com/cart"),
        ("DILLONS", "https://www.dillons.com/cart"),
        ("CITYMARKET", "https://www.citymarket.com/cart"),
        ("HARRISTEETER", "https://www.harristeeter.com/cart"),
        ("KROGER", "https://www.kroger.com/cart"),
    ],
)
def test_chain_code_mapping(chain, expected):
    assert banner_cart_url(chain) == expected
    # Case- and separator-insensitive (e.g. "King Soopers", "king-soopers").
    assert banner_cart_url(chain.lower()) == expected


def test_chain_code_tolerates_spaces_and_punctuation():
    assert banner_cart_url("King Soopers") == "https://www.kingsoopers.com/cart"
    assert banner_cart_url("city market") == "https://www.citymarket.com/cart"


def test_fuzzy_store_name_matching():
    assert banner_cart_url("Fred Meyer - Eagle Island") == "https://www.fredmeyer.com/cart"
    assert banner_cart_url("QFC #1234 - Bellevue") == "https://www.qfc.com/cart"
    assert banner_cart_url("Ralphs Fresh Fare") == "https://www.ralphs.com/cart"
    assert banner_cart_url("Harris Teeter — Cameron Village") == "https://www.harristeeter.com/cart"


@pytest.mark.parametrize("value", [None, "", "   ", "Whole Foods Market", "Trader Joe's", "unknown-banner"])
def test_unknown_or_empty_defaults_to_kroger(value):
    assert banner_cart_url(value) == DEFAULT_CART_URL
    assert DEFAULT_CART_URL == "https://www.kroger.com/cart"
