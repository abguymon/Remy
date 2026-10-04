"""Product ranking via TypeSafe Jev (PRODUCT_RANKER=jev), with LLM fallback."""

import httpx
import pytest

from remy_api.config import get_settings
from remy_api.decisions import jev
from remy_api.kroger.models import Price, Product
from remy_api.planner import matching

PRODUCTS = [
    Product(upc="1", description="Kroger 2% Milk", size="1 gal", price=Price(regular=3.49), department="Dairy"),
    Product(upc="2", description="Kroger Whole Milk", size="1/2 gal", price=Price(regular=2.29, promo=1.99)),
    Product(upc="3", description="Silk Almondmilk", size="1/2 gal", price=Price(regular=3.99)),
]


@pytest.fixture
def use_jev(monkeypatch):
    monkeypatch.setattr(get_settings(), "product_ranker", "jev")
    monkeypatch.setattr(get_settings(), "typesafe_api_key", "test-key")


def _fake_choice(answer: jev.ChoiceAnswer, seen: dict | None = None):
    async def fake(state, instructions, criteria, **kw):
        if seen is not None:
            seen.update(state=state, criteria=criteria)
        return answer

    return fake


async def test_jev_orders_by_probability_and_reports_confidence(use_jev, monkeypatch):
    seen: dict = {}
    answer = jev.ChoiceAnswer(
        choice="p1", confidence=0.62, probabilities={"p0": 0.2, "p1": 0.75, "p2": 0.0, "none": 0.05}
    )
    monkeypatch.setattr(jev, "choice", _fake_choice(answer, seen))
    ranked, confidence = await matching._rank("whole milk", "1 cup", 1, PRODUCTS)
    assert [p.upc for p in ranked] == ["2", "1"]  # almond milk (p=0) dropped
    assert confidence == 0.62
    assert seen["criteria"]["p1"] == "Kroger Whole Milk · 1/2 gal · $2.29 (sale $1.99)"
    assert "none" in seen["criteria"]
    assert "Target size: 1 cup" in seen["state"]


async def test_jev_none_means_not_found(use_jev, monkeypatch):
    answer = jev.ChoiceAnswer(choice="none", confidence=0.8, probabilities={"none": 0.9, "p0": 0.1})
    monkeypatch.setattr(jev, "choice", _fake_choice(answer))
    ranked, confidence = await matching._rank("fresh carrots", None, 1, PRODUCTS)
    assert ranked == [] and confidence == 0.8


async def test_jev_failure_falls_back_to_llm(use_jev, monkeypatch):
    async def broken(*a, **kw):
        raise jev.JevError("down")

    async def llm_rank(term, target_size, package_qty, products):
        return [products[2]]

    monkeypatch.setattr(jev, "choice", broken)
    monkeypatch.setattr(matching, "_rank_with_llm", llm_rank)
    ranked, confidence = await matching._rank("almond milk", None, 1, PRODUCTS)
    assert [p.upc for p in ranked] == ["3"] and confidence is None


async def test_llm_ranker_is_default(monkeypatch):
    async def must_not_call(*a, **kw):
        raise AssertionError("Jev called with PRODUCT_RANKER=llm")

    async def llm_rank(term, target_size, package_qty, products):
        return products[:1]

    monkeypatch.setattr(jev, "choice", must_not_call)
    monkeypatch.setattr(matching, "_rank_with_llm", llm_rank)
    ranked, confidence = await matching._rank("milk", None, 1, PRODUCTS)
    assert [p.upc for p in ranked] == ["1"] and confidence is None


async def test_jev_client_errors_are_typed(monkeypatch):
    monkeypatch.setattr(get_settings(), "typesafe_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.path == "/v1/systemone"
        return httpx.Response(429, text="slow down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://jev.test") as client:
        with pytest.raises(jev.JevError, match="429"):
            await jev.choice("state", "pick", {"a": None}, client=client)

    monkeypatch.setattr(get_settings(), "typesafe_api_key", "")
    with pytest.raises(jev.JevError, match="TYPESAFE_API_KEY"):
        await jev.choice("state", "pick", {"a": None})
