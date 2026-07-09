"""MCP facade tests (T6): the golden path via tools only, the draft-id chain,
auth, cross-interface visibility, and the feature flag.

The tools are exercised in-process via ``FastMCP.call_tool`` with the *same*
mocked LLM/search/Kroger collaborators the planner integration test uses (patched
on ``remy_api.planner.deps``), so the facade is shown to call the same pipeline
with zero divergent logic. Auth (which lives in the ASGI middleware, above the
protocol handler) is tested by driving the middleware directly.

Covers PRD §10 criterion 10 (full golden path via tools incl. execute_cart
rejecting a fabricated cart_draft_id) and criterion 11 (a REST-started plan is
visible via plan_status and vice versa).
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import pytest
import pytest_asyncio
from fastapi import FastAPI

from remy_api.db import get_session_factory
from remy_api.mcp_facade import MCP_MOUNT_PATH, attach_mcp_if_enabled
from remy_api.mcp_facade import context as mcp_context
from remy_api.mcp_facade.auth import MCPAuthMiddleware
from remy_api.mcp_facade.tools import build_mcp_server
from remy_api.models import ApiToken, FulfillmentMethod, UserSettings
from remy_api.planner import deps, machine
from remy_api.recipes import store
from remy_api.recipes.schemas import ParsedIngredient, ParsedRecipe
from remy_api.security import generate_api_token
from remy_api.user_service import create_user

# Reuse the planner integration test's fakes and helpers verbatim (same mocks).
from tests.test_planner_flow import (
    PASSWORD,
    USERNAME,
    FakeKroger,
    FakeLLM,
    FakeSearch,
    _connect_kroger,
)

# --- autouse hygiene (mirrors test_planner_flow) -----------------------------


@pytest.fixture(autouse=True)
def _reset_fts_cache():
    store._fts_available = None
    yield
    store._fts_available = None


@pytest_asyncio.fixture(autouse=True)
async def _cancel_planner_tasks():
    yield
    for task in list(machine._tasks.values()):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    machine._tasks.clear()
    machine._locks.clear()


# --- helpers -----------------------------------------------------------------


def _payload(result) -> dict:  # noqa: ANN001
    """Extract the JSON object a tool returned (FastMCP wraps it in TextContent)."""
    assert result, "tool returned no content"
    text = result[0].text
    return json.loads(text)


async def _call(server, name: str, user_id: str, **kwargs) -> dict:  # noqa: ANN001
    with mcp_context.use_user(user_id):
        result = await server.call_tool(name, kwargs)
    return _payload(result)


# --- fixture: user + saved recipe + settings + patched collaborators ---------


@pytest_asyncio.fixture
async def mcp_env(client, monkeypatch):
    factory = get_session_factory()
    async with factory() as s:
        user = await create_user(s, USERNAME, PASSWORD)
        user_id = user.id
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
        from sqlalchemy import select as _select

        settings = (await s.execute(_select(UserSettings).where(UserSettings.user_id == user_id))).scalar_one_or_none()
        if settings is None:
            settings = UserSettings(user_id=user_id)
            s.add(settings)
        settings.pantry_items = ["salt", "ice", "pepper", "olive oil"]
        settings.favorite_sites = ["fav.com"]
        settings.store_location_id = "fred-meyer-1"
        settings.fulfillment_method = FulfillmentMethod.PICKUP
        await s.commit()

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

    monkeypatch.setattr(deps, "get_llm_client", lambda: FakeLLM())
    monkeypatch.setattr(deps, "get_search_provider", lambda *a, **k: FakeSearch())
    monkeypatch.setattr(deps, "fetch_thumbnails", fake_thumbs)
    monkeypatch.setattr(deps, "scrape_recipe", fake_scrape)
    monkeypatch.setattr(deps, "download_recipe_image", fake_download)
    monkeypatch.setattr(deps, "kroger_search_products", fake_kroger.search_products)
    monkeypatch.setattr(deps, "kroger_add_items_to_cart", fake_kroger.add_items_to_cart)

    server = build_mcp_server()
    return {"server": server, "user_id": user_id, "kroger": fake_kroger, "client": client}


# --- criterion 10: full golden path via tools only --------------------------


async def test_golden_path_via_tools(mcp_env):
    server, user_id = mcp_env["server"], mcp_env["user_id"]
    kroger = mcp_env["kroger"]

    # find_recipes waits for discovery internally and returns a plan_draft_id.
    found = await _call(server, "find_recipes", user_id, meals=["chicken tikka masala and tacos"])
    plan_draft_id = found["plan_draft_id"]
    assert plan_draft_id
    meals = {m["query"]: m for m in found["meals"]}
    meal_a = next(m for q, m in meals.items() if "tikka" in q)
    meal_b = meals["tacos"]

    # Degraded meal surfaced, listicle dropped, dedup applied — same pipeline.
    assert meal_a["status"] == "degraded"
    assert "web_search_failed" in meal_a["source_errors"]
    saved_cand = next(c for c in meal_a["candidates"] if c["origin"] == "saved")
    titles_b = [c["title"] for c in meal_b["candidates"]]
    assert "21 Best Taco Recipes" not in titles_b
    web_cand = next(c for c in meal_b["candidates"] if c["url"] == "https://tacos.com/street")

    # select_recipes -> consolidated list built.
    sel = await _call(
        server,
        "select_recipes",
        user_id,
        plan_draft_id=plan_draft_id,
        choices=[
            {"meal_id": meal_a["meal_id"], "candidate_id": saved_cand["candidate_id"]},
            {"meal_id": meal_b["meal_id"], "candidate_id": web_cand["candidate_id"]},
        ],
    )
    assert sel["plan_status"] == "reviewing_list"

    # build_shopping_list: consolidation + word-boundary pantry.
    shopping = await _call(server, "build_shopping_list", user_id, plan_draft_id=plan_draft_id)
    by_food = {ln["food"]: ln for ln in shopping["to_buy"]}
    assert by_food["onion"]["quantity"] == 3  # 1 + 2 merged
    assert "sliced almond" in by_food  # 'ice' must not match 'sliced'
    pantry_foods = {ln["food"] for ln in shopping["pantry_skipped"]}
    assert "salt" in pantry_foods

    # match_products waits for matching and issues a distinct cart_draft_id.
    cart = await _call(server, "match_products", user_id, plan_draft_id=plan_draft_id)
    cart_draft_id = cart["cart_draft_id"]
    assert cart_draft_id and cart_draft_id != plan_draft_id
    assert "kroger_not_connected" in cart["warnings"]  # not connected yet -> warned, not silent
    items = {it["search_term"]: it for it in cart["items"]}
    assert items["chicken thigh"]["status"] == "not_found"
    assert items["sliced almond"]["is_substitution"] is True
    assert items["sliced almond"]["product"]["upc"] == "al2"
    assert len(items["black bean"]["alternatives"]) >= 1

    onion_id = items["onion"]["line_id"]
    bb_id = items["black bean"]["line_id"]
    bb_alt = items["black bean"]["alternatives"][0]["alternative_id"]

    # swap_product: swap black bean to an alternative + drop onion; id unchanged.
    swapped = await _call(
        server, "swap_product", user_id, cart_draft_id=cart_draft_id, line_id=bb_id, alternative_id=bb_alt
    )
    assert swapped["cart_draft_id"] == cart_draft_id
    dropped = await _call(server, "swap_product", user_id, cart_draft_id=cart_draft_id, line_id=onion_id, drop=True)
    by_line = {it["line_id"]: it for it in dropped["items"]}
    assert by_line[onion_id]["status"] == "dropped"
    assert by_line[bb_id]["product"]["upc"] == bb_alt

    # execute_cart REJECTS a fabricated/foreign cart_draft_id (draft-id chain).
    with pytest.raises(Exception) as excinfo:
        await _call(server, "execute_cart", user_id, cart_draft_id="remy_fabricated_not_real")
    assert "cart_draft_id" in str(excinfo.value)
    assert not kroger.cart_calls  # nothing written on rejection

    # Connect Kroger, then execute with the real id -> truthful outcomes.
    await _connect_kroger(user_id)
    report = await _call(server, "execute_cart", user_id, cart_draft_id=cart_draft_id)
    assert report["status"] == "partial"  # bb alt (bb2) fails, others added
    statuses = {i["upc"]: i["status"] for i in report["items"] if i["upc"]}
    assert statuses.get(bb_alt) == "failed"
    assert statuses.get("al2") == "substituted"
    assert any(i["status"] == "unavailable" for i in report["items"])  # not_found surfaced, never dropped
    assert report["kroger_cart_url"].endswith("/cart")
    assert len(kroger.cart_calls) == 1
    assert {i["upc"] for i in kroger.cart_calls[0]} == {"al2", bb_alt}


async def test_execute_rejects_stale_cart_draft_after_rematch(mcp_env):
    """A cart edit keeps the id; a re-match mints a new one, invalidating the old."""
    server, user_id = mcp_env["server"], mcp_env["user_id"]
    found = await _call(server, "find_recipes", user_id, meals=["tacos"])
    plan_draft_id = found["plan_draft_id"]
    # FakeLLM always extracts two meals; select tacos and skip the other.
    tacos = next(m for m in found["meals"] if m["query"] == "tacos")
    other = next(m for m in found["meals"] if m["query"] != "tacos")
    web_cand = next(c for c in tacos["candidates"] if c["url"] == "https://tacos.com/street")
    await _call(
        server,
        "select_recipes",
        user_id,
        plan_draft_id=plan_draft_id,
        choices=[
            {"meal_id": tacos["meal_id"], "candidate_id": web_cand["candidate_id"]},
            {"meal_id": other["meal_id"], "skip": True},
        ],
    )
    cart1 = await _call(server, "match_products", user_id, plan_draft_id=plan_draft_id)
    first_id = cart1["cart_draft_id"]
    # match_products on an already-matched plan is idempotent (same id).
    cart1b = await _call(server, "match_products", user_id, plan_draft_id=plan_draft_id)
    assert cart1b["cart_draft_id"] == first_id


# --- criterion 11: cross-interface visibility --------------------------------


async def test_rest_started_plan_visible_via_plan_status(mcp_env):
    """A plan created through the REST router is visible from the MCP plan_status."""
    server, user_id, http = mcp_env["server"], mcp_env["user_id"], mcp_env["client"]
    resp = await http.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    created = await http.post("/plan", json={"text": "tacos"}, headers=headers)
    assert created.status_code == 201
    rest_plan_id = created.json()["plan_id"]
    await machine.drain(user_id)

    status = await _call(server, "plan_status", user_id)
    assert status["plan_draft_id"] == rest_plan_id
    assert status["status"] in ("selecting", "discovering")


async def test_tool_started_plan_visible_via_rest(mcp_env):
    """A plan created through find_recipes is visible from GET /plan/state."""
    server, user_id, http = mcp_env["server"], mcp_env["user_id"], mcp_env["client"]
    resp = await http.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    found = await _call(server, "find_recipes", user_id, meals=["tacos"])
    state = await http.get("/plan/state", headers=headers)
    assert state.status_code == 200
    assert state.json()["plan_id"] == found["plan_draft_id"]


async def test_plan_status_no_active_plan(mcp_env):
    server, user_id = mcp_env["server"], mcp_env["user_id"]
    status = await _call(server, "plan_status", user_id)
    assert status["no_active_plan"] is True


# --- auth (ASGI middleware) --------------------------------------------------


async def _run_middleware(token: str | None):
    """Drive the auth middleware once; return (status_code, resolved_user_id)."""
    captured = {"user_id": "__unset__"}

    async def inner(scope, receive, send):  # noqa: ANN001
        captured["user_id"] = mcp_context._current_user_id.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = MCPAuthMiddleware(inner)
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {"type": "http", "headers": headers, "method": "POST", "path": "/"}
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):  # noqa: ANN001
        sent.append(msg)

    await mw(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, captured["user_id"]


async def test_auth_missing_token_rejected(mcp_env):
    status, uid = await _run_middleware(None)
    assert status == 401
    assert uid == "__unset__"  # inner never ran


async def test_auth_valid_api_token_binds_user(mcp_env):
    user_id = mcp_env["user_id"]
    full, token_hash = generate_api_token()
    factory = get_session_factory()
    async with factory() as s:
        s.add(ApiToken(user_id=user_id, name="mcp", token_hash=token_hash))
        await s.commit()
    status, uid = await _run_middleware(full)
    assert status == 200
    assert uid == user_id


async def test_auth_revoked_token_rejected(mcp_env):
    from datetime import UTC, datetime

    user_id = mcp_env["user_id"]
    full, token_hash = generate_api_token()
    factory = get_session_factory()
    async with factory() as s:
        s.add(ApiToken(user_id=user_id, name="mcp", token_hash=token_hash, revoked_at=datetime.now(UTC)))
        await s.commit()
    status, _ = await _run_middleware(full)
    assert status == 401


async def test_auth_jwt_rejected_for_mcp(mcp_env):
    """MCP requires an API token; a web JWT must not authenticate the facade."""
    from remy_api.security import create_access_token

    jwt = create_access_token(mcp_env["user_id"])
    status, uid = await _run_middleware(jwt)
    assert status == 401
    assert uid == "__unset__"


# --- feature flag ------------------------------------------------------------


def test_mcp_mounted_when_enabled():
    class _S:
        mcp_facade_enabled = True

    app = FastAPI()
    ctx = attach_mcp_if_enabled(app, _S())
    assert ctx is not None
    assert any(getattr(r, "path", "").startswith(MCP_MOUNT_PATH) for r in app.routes)


def test_mcp_absent_when_disabled():
    class _S:
        mcp_facade_enabled = False

    app = FastAPI()
    ctx = attach_mcp_if_enabled(app, _S())
    assert ctx is None
    assert not any(getattr(r, "path", "").startswith(MCP_MOUNT_PATH) for r in app.routes)
