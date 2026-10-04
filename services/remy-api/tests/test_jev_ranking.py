"""TypeSafe Jev decisions (JEV_STEPS): product ranking, plus the client itself."""

import json

import httpx
import pytest
from sqlalchemy import select

from remy_api.config import get_settings
from remy_api.db import get_session_factory
from remy_api.decisions import jev
from remy_api.kroger.models import Price, Product
from remy_api.models import Plan, PlanStatus, ProductMemory
from remy_api.planner import discover, matching
from remy_api.planner.schemas import CartEdit, CartState, MatchItem, Meal, ProductRef
from remy_api.prompts.listicle_filter import SearchCandidate
from remy_api.prompts.saved_recipe_relevance import RecipeCandidate
from remy_api.user_service import create_user

PRODUCTS = [
    Product(upc="1", description="Kroger 2% Milk", size="1 gal", price=Price(regular=3.49), department="Dairy"),
    Product(upc="2", description="Kroger Whole Milk", size="1/2 gal", price=Price(regular=2.29, promo=1.99)),
    Product(upc="3", description="Silk Almondmilk", size="1/2 gal", price=Price(regular=3.99)),
]


@pytest.fixture
def use_jev(monkeypatch):
    monkeypatch.setattr(get_settings(), "jev_steps", "products")
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
        raise AssertionError("Jev called with products not in JEV_STEPS")

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


# --- yes/no batches (discovery) ---------------------------------------------


async def test_yes_no_parses_noul_answers(monkeypatch):
    monkeypatch.setattr(get_settings(), "typesafe_api_key", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["questions"]["c0"] == {"type": "noul", "instructions": "first?"}
        return httpx.Response(200, json={"answers": {"c0": {"type": "noul", "noul": 0.9}, "c1": {"noul": 0.2}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://jev.test") as client:
        probs = await jev.yes_no("state", {"c0": "first?", "c1": "second?"}, client=client)
    assert probs == {"c0": 0.9, "c1": 0.2}


async def test_discover_jev_filters_use_threshold(monkeypatch):
    seen = {}

    async def fake_yes_no(state, questions, **kw):
        seen[next(iter(questions))[0]] = (state, questions)
        return {k: (0.8 if k.endswith("0") else 0.3) for k in questions}  # yes only for item 0

    monkeypatch.setattr(jev, "yes_no", fake_yes_no)
    pages = [SearchCandidate(title="Pad Thai", url="https://a/pad-thai"), SearchCandidate(title="25 Thai Dinners")]
    assert await discover._single_recipe_pages_jev("pad thai", pages) == {0}
    meal = Meal(id="m", query="pad thai", verbatim="pad thai", is_specific=True)
    saved = [RecipeCandidate(title="Pad Thai", key_ingredients=["rice noodles"]), RecipeCandidate(title="Curry")]
    assert await discover._relevant_saved_jev(meal, saved) == {0}
    assert "[1] 25 Thai Dinners" in seen["p"][0]
    assert "same dish" in seen["r"][1]["r0"]


# --- "Not sure — check this" ----------------------------------------------------


async def test_confirm_clears_unsure_pick_and_remembers_it(client):
    factory = get_session_factory()
    async with factory() as s:
        user_id = (await create_user(s, "jevconfirm", "sup3r-secret-pw")).id
        item = MatchItem(
            id="i1",
            line_id="l1",
            search_term="whole milk",
            status="matched",
            chosen=ProductRef(upc="2", description="Kroger Whole Milk", size="1/2 gal", price=2.29),
            pick_confidence=0.38,
        )
        plan = Plan(
            user_id=user_id,
            status=PlanStatus.REVIEWING_CART,
            matches=CartState(items=[item]).model_dump(mode="json"),
        )
        s.add(plan)
        await s.commit()
        await matching.apply_cart_edits(s, plan, [CartEdit(op="confirm", item_id="i1")])
        cart = CartState(**plan.matches)
        assert cart.items[0].pick_confidence is None
        remembered = (await s.execute(select(ProductMemory).where(ProductMemory.user_id == user_id))).scalars().all()
        assert [m.upc for m in remembered] == ["2"]
