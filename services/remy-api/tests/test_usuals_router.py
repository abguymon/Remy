"""Usuals API round-trip: list/filter/order, pin, hide/unhide/remove, product
search, and the receipt-import extract → review → confirm flow (mocked LLM +
Kroger)."""

from __future__ import annotations

import pytest_asyncio

from remy_api import memory
from remy_api.db import get_session_factory
from remy_api.kroger.models import Price, Product, StockLevel
from remy_api.planner import deps
from remy_api.prompts import receipt_items
from remy_api.user_service import create_user

USERNAME = "usuals-owner"
PASSWORD = "sup3r-secret-pw"


@pytest_asyncio.fixture
async def auth(client):
    factory = get_session_factory()
    async with factory() as s:
        user = await create_user(s, USERNAME, PASSWORD)
        user_id = user.id
    resp = await client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # A selected store so product search / import don't 409.
    await client.put("/users/me/settings", json={"store_location_id": "store-1"}, headers=headers)
    return client, headers, user_id


def _product(upc, desc, price=1.0, stock=StockLevel.HIGH):
    return Product(upc=upc, description=desc, price=Price(regular=price), stock_level=stock, pickup=True)


async def _seed(user_id):
    factory = get_session_factory()
    async with factory() as s:
        await memory.record_ordered(s, user_id, search_term="pasta", upc="pasta1", description="Spaghetti")
        await memory.record_ordered(s, user_id, search_term="pasta", upc="pasta1", description="Spaghetti")
        await memory.record_ordered(s, user_id, search_term="rice", upc="rice1")  # once only → excluded
        await s.commit()


async def test_requires_auth(client):
    assert (await client.get("/users/me/usuals")).status_code == 401


async def test_list_filters_and_orders(auth):
    client, headers, user_id = auth
    await _seed(user_id)
    resp = await client.get("/users/me/usuals", headers=headers)
    assert resp.status_code == 200
    upcs = [u["upc"] for u in resp.json()]
    assert upcs == ["pasta1"]  # rice1 (single order) excluded


async def test_pin_then_list_then_remove(auth):
    client, headers, _ = auth
    created = await client.post(
        "/users/me/usuals",
        json={"upc": "oil1", "description": "Olive Oil", "size": "500 ml", "price": 6.99, "food_key": "Olive Oil"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source"] == "pinned" and body["preferred"] is True and body["food_key"] == "olive oil"

    listed = await client.get("/users/me/usuals", headers=headers)
    assert any(u["upc"] == "oil1" for u in listed.json())

    # Pinned rows hard-delete → gone from the list.
    removed = await client.delete("/users/me/usuals/oil1", headers=headers)
    assert removed.status_code == 204
    assert (await client.get("/users/me/usuals", headers=headers)).json() == []
    assert (await client.delete("/users/me/usuals/oil1", headers=headers)).status_code == 404


async def test_hide_unhide_order_derived(auth):
    client, headers, user_id = auth
    await _seed(user_id)
    assert (await client.post("/users/me/usuals/pasta1/hide", headers=headers)).status_code == 204
    assert [u["upc"] for u in (await client.get("/users/me/usuals", headers=headers)).json()] == []
    assert (await client.post("/users/me/usuals/pasta1/unhide", headers=headers)).status_code == 204
    assert [u["upc"] for u in (await client.get("/users/me/usuals", headers=headers)).json()] == ["pasta1"]
    assert (await client.post("/users/me/usuals/ghost/hide", headers=headers)).status_code == 404


async def test_product_search_requires_store(client):
    factory = get_session_factory()
    async with factory() as s:
        await create_user(s, "nostore", PASSWORD)
    token = (await client.post("/auth/login", json={"username": "nostore", "password": PASSWORD})).json()[
        "access_token"
    ]
    resp = await client.get("/kroger/products?term=onion", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "no_store_selected"


async def test_product_search(auth, monkeypatch):
    client, headers, _ = auth

    async def fake_search(session, term, location_id, limit=10, fulfillment=None, **kw):
        return [_product("p1", "Yellow Onion", price=1.29), _product("p2", "Sweet Onion", price=1.99)]

    monkeypatch.setattr(deps, "kroger_search_products", fake_search)
    # The kroger router imports search_products directly; patch there too.
    monkeypatch.setattr("remy_api.routers.kroger.search_products", fake_search)
    resp = await client.get("/kroger/products?term=onion&limit=5", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["upc"] == "p1" and body[0]["price"] == 1.29


async def test_import_extract_review_confirm_roundtrip(auth, monkeypatch):
    client, headers, user_id = auth

    class FakeLLM:
        async def structured(self, prompt, schema):
            assert prompt.prompt_id == receipt_items.PROMPT_ID
            return receipt_items.ReceiptItemsOutput(
                found_items=True,
                items=[
                    receipt_items.ReceiptLineItem(name="KRO WHOLE MILK", quantity=1, price=3.49),
                    receipt_items.ReceiptLineItem(name="BANANAS", price=0.59),
                ],
            )

    async def fake_search(session, term, location_id, limit=10, fulfillment=None, **kw):
        if "MILK" in term:
            return [_product("milk1", "Kroger Whole Milk", price=3.49), _product("milk2", "Organic Milk", price=4.99)]
        if "BANANA" in term:
            return [_product("ban1", "Bananas", price=0.59)]
        return []

    monkeypatch.setattr(deps, "get_llm_client", lambda: FakeLLM())
    monkeypatch.setattr(deps, "kroger_search_products", fake_search)

    review = await client.post("/users/me/usuals/import", data={"text": "MILK 3.49\nBANANAS 0.59\nTOTAL 4.08"}, headers=headers)
    assert review.status_code == 200, review.text
    payload = review.json()
    assert payload["found_items"] is True
    by_name = {it["extracted_name"]: it for it in payload["items"]}
    assert by_name["KRO WHOLE MILK"]["matched"]["upc"] == "milk1"
    assert by_name["KRO WHOLE MILK"]["food_key"] == "kro whole milk"
    assert len(by_name["KRO WHOLE MILK"]["alternatives"]) == 1  # milk2
    assert by_name["BANANAS"]["matched"]["upc"] == "ban1"

    # Confirm the two matched picks → seeded as import usuals.
    confirm = await client.post(
        "/users/me/usuals/import/confirm",
        json={
            "selections": [
                {"food_key": "kro whole milk", "upc": "milk1", "description": "Kroger Whole Milk", "price": 3.49},
                {"food_key": "bananas", "upc": "ban1", "description": "Bananas", "price": 0.59},
            ]
        },
        headers=headers,
    )
    assert confirm.status_code == 200
    assert confirm.json()["seeded"] == 2

    usuals = {u["upc"] for u in (await client.get("/users/me/usuals", headers=headers)).json()}
    assert usuals == {"milk1", "ban1"}


async def test_import_no_content_is_422(auth):
    client, headers, _ = auth
    resp = await client.post("/users/me/usuals/import", data={}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "no_import_content"


async def test_import_found_false_returns_empty(auth, monkeypatch):
    client, headers, _ = auth

    class FakeLLM:
        async def structured(self, prompt, schema):
            return receipt_items.ReceiptItemsOutput(found_items=False, items=[])

    monkeypatch.setattr(deps, "get_llm_client", lambda: FakeLLM())
    resp = await client.post("/users/me/usuals/import", data={"text": "just some random text"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"found_items": False, "items": []}
