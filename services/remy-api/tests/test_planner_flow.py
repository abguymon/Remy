"""Full planner pipeline + state-machine integration tests (T5).

Drives the golden path through the HTTP API with mocked LLM, search, and Kroger
collaborators (patched once on ``remy_api.planner.deps``), exercising: discover
(degraded source + listicle dropped + dedup), select (one saved, one web-scraped),
list (consolidation + word-boundary pantry), match (ranked pick, substitution,
not_found, alternatives, estimated total), cart edits (swap + drop), execute
(truthful outcomes incl. a failure), plus one-active-plan 409, wrong-state 409,
abandon, and resume-snapshot fidelity.
"""

import json
import re

import pytest
import pytest_asyncio

from remy_api.db import get_session_factory
from remy_api.kroger.models import CartItemOutcome, Modality, OutcomeStatus, Price, Product, StockLevel
from remy_api.models import KrogerToken, Order
from remy_api.planner import deps, machine
from remy_api.prompts import (
    ingredient_parsing,
    listicle_filter,
    meal_extraction,
    product_extraction,
    product_ranking,
    saved_recipe_relevance,
)
from remy_api.recipes import store
from remy_api.recipes.schemas import ParsedIngredient, ParsedRecipe
from remy_api.search.base import SearchError, SearchResult
from remy_api.user_service import create_user

USERNAME = "owner"
PASSWORD = "sup3r-secret-pw"


# --- deterministic ingredient parse table -----------------------------------

_PARSE = {
    "1 onion": (1.0, None, "onion", None),
    "1 tsp salt": (1.0, "tsp", "salt", None),
    "1 lb chicken thighs": (1.0, "lb", "chicken thigh", None),
    "2 onions": (2.0, None, "onion", None),
    "1/2 tsp salt": (0.5, "tsp", "salt", None),
    "1 cup sliced almonds": (1.0, "cup", "sliced almond", "sliced"),
    "1 can black beans": (1.0, "can", "black bean", "drained"),
}


def _tail_json(user: str):
    starts = [i for i in (user.find("["), user.find("{")) if i != -1]
    return json.loads(user[min(starts) :])


# --- fakes -------------------------------------------------------------------


class FakeLLM:
    """Dispatches structured() by prompt_id; input-aware where consolidation needs it."""

    def __init__(self):
        # term -> (ranked_indices | None, none_acceptable)
        self.ranking = {"chicken thigh": (None, True)}

    async def structured(self, prompt, schema):
        pid = prompt.prompt_id
        if pid == meal_extraction.PROMPT_ID:
            return meal_extraction.MealExtractionOutput(
                meals=[
                    meal_extraction.Meal(
                        query="chicken tikka masala", verbatim="chicken tikka masala", is_specific=True
                    ),
                    meal_extraction.Meal(query="tacos", verbatim="tacos", is_specific=True),
                ]
            )
        if pid == saved_recipe_relevance.PROMPT_ID:
            return saved_recipe_relevance.SavedRecipeRelevanceOutput(relevant_indices=[0])
        if pid == listicle_filter.PROMPT_ID:
            rows = _tail_json(prompt.user)
            return listicle_filter.ListicleFilterOutput(keep_indices=list(range(len(rows))))
        if pid == ingredient_parsing.PROMPT_ID:
            rows = _tail_json(prompt.user)
            out = []
            for r in rows:
                q, u, f, n = _PARSE.get(r["value"], (None, None, r["value"].lower(), None))
                out.append(ingredient_parsing.ParsedIngredient(index=r["index"], quantity=q, unit=u, food=f, note=n))
            return ingredient_parsing.IngredientParsingOutput(ingredients=out)
        if pid == product_extraction.PROMPT_ID:
            rows = _tail_json(prompt.user)
            items = [
                product_extraction.ProductExtractionItem(
                    index=r["index"],
                    products=[
                        product_extraction.ExtractedProduct(search_term=r["food"], package_quantity=1, confidence=0.9)
                    ],
                )
                for r in rows
            ]
            return product_extraction.ProductExtractionOutput(items=items)
        if pid == product_ranking.PROMPT_ID:
            term = re.search(r'Search term:\s*"([^"]+)"', prompt.user).group(1)
            products = _tail_json(prompt.user)
            ranked_idx, none_acceptable = self.ranking.get(term, (None, False))
            if none_acceptable:
                return product_ranking.ProductRankingOutput(ranked=[], none_acceptable=True)
            order = ranked_idx if ranked_idx is not None else list(range(len(products)))
            return product_ranking.ProductRankingOutput(
                ranked=[product_ranking.RankedProduct(index=i, reason="ok") for i in order]
            )
        raise AssertionError(f"unexpected prompt id {pid}")


class FakeSearch:
    async def search(self, query, site=None, max_results=10):
        if query == "chicken tikka masala":
            # Web fully fails for this meal -> degraded (saved source still yields).
            raise SearchError("web down")
        if query == "tacos":
            if site is not None:
                return [SearchResult(title="Best Street Tacos", url="https://fav.com/tacos", snippet="")]
            return [
                SearchResult(title="21 Best Taco Recipes", url="https://roundup.com/21-best", snippet="listicle"),
                SearchResult(title="Easy Street Tacos", url="https://tacos.com/street", snippet=""),
                SearchResult(title="Easy Street Tacos", url="https://tacos.com/street", snippet=""),  # dup
            ]
        return []


def _price(p):
    return Price(regular=p, promo=None, on_sale=False)


class FakeKroger:
    def __init__(self):
        self.cart_calls = []
        self.products = {
            "onion": [
                Product(
                    upc="on1", description="Yellow Onion", stock_level=StockLevel.HIGH, price=_price(1.00), pickup=True
                )
            ],
            "chicken thigh": [
                Product(
                    upc="ck1", description="Chicken Thighs", stock_level=StockLevel.HIGH, price=_price(5.0), pickup=True
                )
            ],
            "sliced almond": [
                Product(
                    upc="al1",
                    description="Sliced Almonds",
                    stock_level=StockLevel.TEMPORARILY_OUT_OF_STOCK,
                    price=_price(4.0),
                    pickup=True,
                ),
                Product(
                    upc="al2",
                    description="Sliced Almonds Store Brand",
                    stock_level=StockLevel.HIGH,
                    price=_price(3.5),
                    pickup=True,
                ),
            ],
            "black bean": [
                Product(
                    upc="bb1",
                    description="Canned Black Beans",
                    stock_level=StockLevel.HIGH,
                    price=_price(1.19),
                    pickup=True,
                ),
                Product(
                    upc="bb2",
                    description="Organic Black Beans",
                    stock_level=StockLevel.HIGH,
                    price=_price(2.0),
                    pickup=True,
                ),
                Product(
                    upc="bb3",
                    description="Low Sodium Black Beans",
                    stock_level=StockLevel.HIGH,
                    price=_price(3.0),
                    pickup=True,
                ),
            ],
        }

    async def search_products(self, session, term, location_id, limit=10, fulfillment=None, **kw):
        return list(self.products.get(term, []))

    async def add_items_to_cart(self, session, user_id, items, **kw):
        self.cart_calls.append(list(items))
        outcomes = []
        for it in items:
            upc = it["upc"] if isinstance(it, dict) else it.upc
            qty = it["quantity"] if isinstance(it, dict) else it.quantity
            # bb2 fails, everything else is added -> a truthful partial outcome.
            status = OutcomeStatus.FAILED if upc == "bb2" else OutcomeStatus.ADDED
            reason = "Out of stock at checkout" if status == OutcomeStatus.FAILED else None
            outcomes.append(
                CartItemOutcome(upc=upc, quantity=qty, modality=Modality.PICKUP, status=status, reason=reason)
            )
        return outcomes


# --- fixtures ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_fts_cache():
    store._fts_available = None
    yield
    store._fts_available = None


@pytest_asyncio.fixture(autouse=True)
async def _cancel_planner_tasks():
    """Cancel any lingering background step tasks so they can't run into the next
    test's schema reset (e.g. a re-plan that launches discover without draining)."""
    yield
    import asyncio
    import contextlib

    for task in list(machine._tasks.values()):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    machine._tasks.clear()
    machine._locks.clear()


@pytest_asyncio.fixture
async def env(client, monkeypatch):
    factory = get_session_factory()
    async with factory() as s:
        user = await create_user(s, USERNAME, PASSWORD)
        user_id = user.id
        # A saved recipe so meal A has a saved candidate.
        await store.create_recipe(
            s,
            user_id,
            ParsedRecipe(
                title="Chicken Tikka Masala",
                source_url="https://saved.example/tikka",
                ingredients=[
                    ParsedIngredient(raw="1 onion"),
                    ParsedIngredient(raw="1 tsp salt"),
                    ParsedIngredient(raw="1 lb chicken thighs"),
                ],
                instructions=["cook"],
            ),
        )

    resp = await client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    await client.put(
        "/users/me/settings",
        json={
            "pantry_items": ["salt", "ice", "pepper", "olive oil"],
            "favorite_sites": ["fav.com"],
            "store_location_id": "fred-meyer-1",
            "fulfillment_method": "PICKUP",
        },
        headers=headers,
    )

    fake_llm = FakeLLM()
    fake_search = FakeSearch()
    fake_kroger = FakeKroger()

    async def fake_scrape(url, *, llm=None, client=None):
        return ParsedRecipe(
            title="Street Tacos",
            source_url=url,
            image_url=None,
            ingredients=[
                ParsedIngredient(raw="2 onions"),
                ParsedIngredient(raw="1/2 tsp salt"),
                ParsedIngredient(raw="1 cup sliced almonds"),
                ParsedIngredient(raw="1 can black beans"),
            ],
            instructions=["assemble"],
        )

    async def fake_thumbs(urls, **kw):
        return {}

    async def fake_download(recipe_id, image_url, **kw):
        return None

    monkeypatch.setattr(deps, "get_llm_client", lambda: fake_llm)
    monkeypatch.setattr(deps, "get_search_provider", lambda *a, **k: fake_search)
    monkeypatch.setattr(deps, "fetch_thumbnails", fake_thumbs)
    monkeypatch.setattr(deps, "scrape_recipe", fake_scrape)
    monkeypatch.setattr(deps, "download_recipe_image", fake_download)
    monkeypatch.setattr(deps, "kroger_search_products", fake_kroger.search_products)
    monkeypatch.setattr(deps, "kroger_add_items_to_cart", fake_kroger.add_items_to_cart)

    return {"client": client, "headers": headers, "user_id": user_id, "kroger": fake_kroger}


async def _connect_kroger(user_id):
    from datetime import UTC, datetime, timedelta

    factory = get_session_factory()
    async with factory() as s:
        s.add(
            KrogerToken(
                user_id=user_id,
                access_token="tok",
                refresh_token="ref",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await s.commit()


# --- tests -------------------------------------------------------------------


async def test_full_golden_path(env):
    client, headers, user_id = env["client"], env["headers"], env["user_id"]
    kroger = env["kroger"]

    # --- discover ---
    created = await client.post("/plan", json={"text": "chicken tikka masala and tacos"}, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "discovering"
    await machine.drain(user_id)

    state = (await client.get("/plan/state", headers=headers)).json()
    assert state["status"] == "selecting"
    meals = state["meals"]
    assert len(meals) == 2
    meal_a = next(m for m in meals if "tikka" in m["query"])
    meal_b = next(m for m in meals if m["query"] == "tacos")

    cand_a = state["candidates"][meal_a["id"]]
    # Degraded: web source failed but the saved recipe still appears (never silent).
    assert cand_a["status"] == "degraded"
    assert "web_search_failed" in cand_a["source_errors"]
    assert any(c["origin"] == "saved" for c in cand_a["candidates"])

    cand_b = state["candidates"][meal_b["id"]]
    assert cand_b["status"] == "ready"
    titles_b = [c["title"] for c in cand_b["candidates"]]
    assert "21 Best Taco Recipes" not in titles_b  # listicle dropped
    # Dedup: the duplicated tacos.com/street URL collapses to a single candidate.
    assert sum(1 for c in cand_b["candidates"] if c["url"] == "https://tacos.com/street") == 1
    assert any(c["origin"] == "favorite" for c in cand_b["candidates"])

    saved_cand = next(c for c in cand_a["candidates"] if c["origin"] == "saved")
    web_cand = next(c for c in cand_b["candidates"] if c["url"] == "https://tacos.com/street")

    # --- select (one saved, one web-scraped) ---
    sel = await client.post(
        "/plan/select",
        json={
            "choices": [
                {"meal_id": meal_a["id"], "choice": "candidate", "candidate_id": saved_cand["id"]},
                {"meal_id": meal_b["id"], "choice": "candidate", "candidate_id": web_cand["id"]},
            ]
        },
        headers=headers,
    )
    assert sel.status_code == 200, sel.text
    body = sel.json()
    assert body["status"] == "reviewing_list"

    # --- list: consolidation + pantry word-boundary ---
    lines = body["shopping_list"]["lines"]
    by_food = {ln["food"]: ln for ln in lines}
    assert by_food["onion"]["quantity"] == 3  # 1 + 2 merged
    assert by_food["onion"]["group"] == "to_buy"
    assert by_food["salt"]["group"] == "pantry_skipped"  # pantry staple
    assert by_food["salt"]["included"] is False
    assert by_food["sliced almond"]["group"] == "to_buy"  # 'ice' must NOT match 'sliced'
    assert by_food["black bean"]["group"] == "to_buy"

    # --- approve -> match ---
    approved = await client.post("/plan/list/approve", headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "matching"
    await machine.drain(user_id)

    state = (await client.get("/plan/state", headers=headers)).json()
    assert state["status"] == "reviewing_cart"
    cart = state["cart"]
    assert cart["status"] == "ready"
    items = {it["search_term"]: it for it in cart["items"]}

    assert items["onion"]["status"] == "matched"
    assert items["chicken thigh"]["status"] == "not_found"
    assert items["sliced almond"]["status"] == "substituted"
    assert items["sliced almond"]["chosen"]["upc"] == "al2"
    assert len(items["sliced almond"]["alternatives"]) >= 1
    assert items["black bean"]["status"] == "matched"
    assert len(items["black bean"]["alternatives"]) >= 1
    # estimated: onion 1.00 + almond(sub) 3.5 + black bean 1.19 (chicken not_found excluded)
    assert cart["estimated_total"] == pytest.approx(5.69)

    onion_id = items["onion"]["id"]
    bb_id = items["black bean"]["id"]
    bb_alt = items["black bean"]["alternatives"][0]["alternative_id"]

    # --- cart edits: swap black bean to an alternative + drop onion ---
    edited = await client.post(
        "/plan/cart/edits",
        json={
            "ops": [
                {"op": "swap", "item_id": bb_id, "alternative_id": bb_alt},
                {"op": "drop", "item_id": onion_id},
            ]
        },
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    cart = edited.json()["cart"]
    items = {it["id"]: it for it in cart["items"]}
    assert items[onion_id]["status"] == "dropped"
    assert items[bb_id]["chosen"]["upc"] == bb_alt
    # onion dropped; black bean now the alt price; almond 3.5.
    bb_price = items[bb_id]["chosen"]["price"]
    assert cart["estimated_total"] == pytest.approx(3.5 + bb_price)

    # --- execute (truthful outcomes incl. a failure) ---
    await _connect_kroger(user_id)
    # A Fred Meyer store → the handoff CTA must point at the banner cart, not
    # the generic kroger.com/cart.
    await client.put("/users/me/settings", json={"store_chain": "FRED"}, headers=headers)
    done = await client.post("/plan/cart/execute", headers=headers)
    assert done.status_code == 200, done.text
    result = done.json()
    assert result["status"] == "done"
    execution = result["execution"]
    assert execution["kroger_cart_url"] == "https://www.fredmeyer.com/cart"
    assert execution["status"] == "partial"  # one item failed, others added
    exec_by_upc = {i["upc"]: i for i in execution["items"]}
    assert exec_by_upc[bb_alt]["status"] == "failed"  # bb2 failed truthfully
    assert exec_by_upc["al2"]["status"] == "substituted"
    # the not_found chicken surfaces as unavailable, never silently dropped
    assert any(i["status"] == "unavailable" for i in execution["items"])

    # Cart write attempted with exactly the addable items (almond + black bean).
    assert len(kroger.cart_calls) == 1
    assert {i["upc"] for i in kroger.cart_calls[0]} == {"al2", bb_alt}

    # Order row persisted as the local shadow record.
    factory = get_session_factory()
    async with factory() as s:
        orders = (
            (await s.execute(__import__("sqlalchemy").select(Order).where(Order.user_id == user_id))).scalars().all()
        )
    assert len(orders) == 1
    assert orders[0].plan_id is not None


async def test_one_active_plan_conflict(env):
    client, headers, user_id = env["client"], env["headers"], env["user_id"]
    first = await client.post("/plan", json={"text": "tacos"}, headers=headers)
    assert first.status_code == 201
    await machine.drain(user_id)
    second = await client.post("/plan", json={"text": "pasta"}, headers=headers)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "plan_active"


async def test_wrong_state_operation_conflict(env):
    client, headers, user_id = env["client"], env["headers"], env["user_id"]
    await client.post("/plan", json={"text": "tacos"}, headers=headers)
    await machine.drain(user_id)
    # In 'selecting', execute is invalid.
    resp = await client.post("/plan/cart/execute", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "wrong_state"
    assert "selecting" in resp.json()["error"]["message"]


async def test_abandon_then_replan(env):
    client, headers, user_id = env["client"], env["headers"], env["user_id"]
    await client.post("/plan", json={"text": "tacos"}, headers=headers)
    await machine.drain(user_id)
    deleted = await client.delete("/plan", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get("/plan/state", headers=headers)).status_code == 404
    # A fresh plan is now allowed (no lingering active plan).
    again = await client.post("/plan", json={"text": "chicken tikka masala and tacos"}, headers=headers)
    assert again.status_code == 201


async def test_resume_snapshot_fidelity_midflow(env):
    client, headers, user_id = env["client"], env["headers"], env["user_id"]
    await client.post("/plan", json={"text": "chicken tikka masala and tacos"}, headers=headers)
    await machine.drain(user_id)
    state = (await client.get("/plan/state", headers=headers)).json()
    meal_a = next(m for m in state["meals"] if "tikka" in m["query"])
    meal_b = next(m for m in state["meals"] if m["query"] == "tacos")
    saved_cand = next(c for c in state["candidates"][meal_a["id"]]["candidates"] if c["origin"] == "saved")
    web_cand = next(
        c for c in state["candidates"][meal_b["id"]]["candidates"] if c["url"] == "https://tacos.com/street"
    )
    await client.post(
        "/plan/select",
        json={
            "choices": [
                {"meal_id": meal_a["id"], "choice": "candidate", "candidate_id": saved_cand["id"]},
                {"meal_id": meal_b["id"], "choice": "candidate", "candidate_id": web_cand["id"]},
            ]
        },
        headers=headers,
    )
    # A brand-new GET (as if the browser was killed and reopened) resumes intact.
    resumed = (await client.get("/plan/state", headers=headers)).json()
    assert resumed["status"] == "reviewing_list"
    foods = {ln["food"] for ln in resumed["shopping_list"]["lines"]}
    assert {"onion", "salt", "sliced almond", "black bean"} <= foods
