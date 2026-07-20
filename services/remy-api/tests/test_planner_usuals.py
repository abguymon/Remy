"""Match short-circuit tests (purchase memory / usuals).

Drives ``matching._match_one`` directly with a preloaded usuals map and a spy LLM
so we can assert the P5 ranking call is skipped when a remembered obtainable
product is in the results, and taken when it is not.
"""

from __future__ import annotations

import pytest

from remy_api.kroger.models import Price, Product, StockLevel
from remy_api.models import Plan, PlanStatus, ProductMemory
from remy_api.planner import deps, matching
from remy_api.planner.schemas import (
    Alternative,
    CartEdit,
    CartState,
    ItemStatus,
    MatchItem,
    ProductRef,
)
from remy_api.prompts import product_ranking
from remy_api.user_service import create_user


class SpyLLM:
    """Counts product-ranking calls; ranks products in search order."""

    def __init__(self):
        self.rank_calls = 0

    async def structured(self, prompt, schema):
        import json

        assert prompt.prompt_id == product_ranking.PROMPT_ID
        self.rank_calls += 1
        # Rank in given order (the prompt embeds N products as a JSON tail).
        products = json.loads(prompt.user[prompt.user.find("[") :]) if "[" in prompt.user else []
        return product_ranking.ProductRankingOutput(
            ranked=[product_ranking.RankedProduct(index=i, reason="ok") for i in range(len(products))],
            none_acceptable=False,
        )


def _product(upc, desc, stock=StockLevel.HIGH, price=1.0, pickup=True):
    return Product(upc=upc, description=desc, stock_level=stock, price=Price(regular=price), pickup=pickup)


def _mem(upc, food_key="onion", **kw):
    return ProductMemory(user_id="u", food_key=food_key, upc=upc, **kw)


def _item():
    return MatchItem(id="i1", line_id="l1", search_term="onion", count=1, status=ItemStatus.MATCHING)


@pytest.fixture
def spy(monkeypatch):
    llm = SpyLLM()
    monkeypatch.setattr(deps, "get_llm_client", lambda: llm)
    return llm


async def _search_returns(monkeypatch, products):
    async def fake_search(session, term, location_id, limit=10, fulfillment=None, **kw):
        return list(products)

    monkeypatch.setattr(deps, "kroger_search_products", fake_search)


async def test_usual_short_circuits_ranking(spy, monkeypatch):
    products = [_product("on1", "Yellow Onion"), _product("on2", "Sweet Onion"), _product("on3", "Red Onion")]
    await _search_returns(monkeypatch, products)
    usuals = {"onion": [_mem("on2", preferred=True, source="swap")]}

    item = await matching._match_one(_item(), "store-1", "pickup", usuals=usuals)

    assert item.is_usual is True
    assert item.status == ItemStatus.MATCHED
    assert item.chosen.upc == "on2"  # the preferred usual, not the top search result
    assert spy.rank_calls == 0  # P5 ranking skipped
    assert [a.alternative_id for a in item.alternatives] == ["on1", "on3"]  # next results


async def test_missing_usual_falls_through_to_ranking(spy, monkeypatch):
    products = [_product("on1", "Yellow Onion")]
    await _search_returns(monkeypatch, products)
    # Remembered UPC is not in the search results.
    usuals = {"onion": [_mem("ghost", preferred=True, source="swap")]}

    item = await matching._match_one(_item(), "store-1", "pickup", usuals=usuals)

    assert item.is_usual is False
    assert item.chosen.upc == "on1"
    assert spy.rank_calls == 1  # normal ranking ran


async def test_out_of_stock_usual_falls_through_to_ranking(spy, monkeypatch):
    products = [
        _product("on1", "Yellow Onion", stock=StockLevel.HIGH),
        _product("on2", "Sweet Onion", stock=StockLevel.TEMPORARILY_OUT_OF_STOCK),
    ]
    await _search_returns(monkeypatch, products)
    usuals = {"onion": [_mem("on2", preferred=True, source="swap")]}

    item = await matching._match_one(_item(), "store-1", "pickup", usuals=usuals)

    assert item.is_usual is False
    assert item.chosen.upc == "on1"  # ranked pick, not the out-of-stock usual
    assert spy.rank_calls == 1


async def test_no_usuals_map_is_normal_path(spy, monkeypatch):
    products = [_product("on1", "Yellow Onion")]
    await _search_returns(monkeypatch, products)

    item = await matching._match_one(_item(), "store-1", "pickup", usuals=None)

    assert item.is_usual is False
    assert spy.rank_calls == 1


async def test_frequent_usual_short_circuits(spy, monkeypatch):
    products = [_product("on1", "Yellow Onion"), _product("on2", "Sweet Onion")]
    await _search_returns(monkeypatch, products)
    # No preferred row, but on2 was ordered 3x → the frequent usual.
    usuals = {"onion": [_mem("on2", times_ordered=3, source="order")]}

    item = await matching._match_one(_item(), "store-1", "pickup", usuals=usuals)

    assert item.is_usual is True
    assert item.chosen.upc == "on2"
    assert spy.rank_calls == 0


# --- cart edits: add_upc + swap writer ---------------------------------------


async def _plan_with_cart(session, items):
    user = await create_user(session, "cart-owner", "password-123")
    cart = CartState(cart_draft_id="d1", status="ready", items=items)
    cart.estimated_total = matching._estimated_total(items)
    plan = Plan(user_id=user.id, status=PlanStatus.REVIEWING_CART, matches=cart.model_dump(mode="json"))
    session.add(plan)
    await session.commit()
    return user.id, plan


async def test_add_upc_appends_matched_usual_and_updates_total(session):
    existing = MatchItem(
        id="i1",
        line_id="l1",
        search_term="onion",
        count=1,
        status=ItemStatus.MATCHED,
        chosen=ProductRef(upc="on1", description="Onion", price=1.0),
    )
    user_id, plan = await _plan_with_cart(session, [existing])
    # A remembered product the user can add from the usuals strip.
    session.add(
        ProductMemory(
            user_id=user_id, food_key="milk", upc="milk1", description="Whole Milk", last_price=3.5, source="pinned"
        )
    )
    await session.commit()

    await matching.apply_cart_edits(session, plan, [CartEdit(op="add_upc", upc="milk1")])
    cart = CartState(**plan.matches)
    added = next(it for it in cart.items if it.chosen and it.chosen.upc == "milk1")
    assert added.status == ItemStatus.MATCHED
    assert added.is_usual is True
    assert added.chosen.price == 3.5  # price from memory, no Kroger call
    assert cart.estimated_total == pytest.approx(1.0 + 3.5)

    # Re-adding the same UPC is a no-op.
    await matching.apply_cart_edits(session, plan, [CartEdit(op="add_upc", upc="milk1")])
    cart = CartState(**plan.matches)
    assert sum(1 for it in cart.items if it.chosen and it.chosen.upc == "milk1") == 1


async def test_swap_records_preferred_memory(session):
    item = MatchItem(
        id="i1",
        line_id="l1",
        search_term="black bean",
        count=1,
        status=ItemStatus.MATCHED,
        chosen=ProductRef(upc="bb1", description="Canned Black Beans", price=1.19),
        alternatives=[Alternative(alternative_id="bb2", upc="bb2", description="Organic Black Beans", price=2.0)],
    )
    user_id, plan = await _plan_with_cart(session, [item])

    await matching.apply_cart_edits(session, plan, [CartEdit(op="swap", item_id="i1", alternative_id="bb2")])
    rows = {r.upc: r for r in await matching.memory.rows_for_upc(session, user_id, "bb2")}
    assert rows["bb2"].preferred is True
    assert rows["bb2"].food_key == "black bean"
    assert rows["bb2"].source == "swap"
    assert rows["bb2"].times_ordered == 0
