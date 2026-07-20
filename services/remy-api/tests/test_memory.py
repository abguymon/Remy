"""Unit tests for the purchase-memory module (writers, reader, queries).

Drives ``remy_api.memory`` directly against a raw async session (no HTTP), so the
upsert / selection semantics are covered independently of the planner and router.
"""

from __future__ import annotations

from remy_api import memory
from remy_api.models import ProductMemory
from remy_api.user_service import create_user


async def _user(session) -> str:
    user = await create_user(session, "mem-owner", "password-123")
    return user.id


async def _rows(session, user_id, food_key):
    from sqlalchemy import select

    result = await session.execute(
        select(ProductMemory).where(ProductMemory.user_id == user_id, ProductMemory.food_key == food_key)
    )
    return list(result.scalars().all())


async def test_record_ordered_increments_times_ordered(session):
    user_id = await _user(session)
    for _ in range(2):
        await memory.record_ordered(
            session, user_id, search_term="Onion", upc="on1", description="Yellow Onion", price=1.0
        )
    await session.commit()
    rows = await _rows(session, user_id, "onion")
    assert len(rows) == 1
    row = rows[0]
    assert row.times_ordered == 2
    assert row.source == "order"
    assert row.last_ordered_at is not None
    assert row.food_key == "onion"  # lowercased search term


async def test_record_swap_sets_preferred_and_clears_siblings(session):
    user_id = await _user(session)
    # Two ordered products for the same food; then swap to a third.
    await memory.record_ordered(session, user_id, search_term="black beans", upc="bb1", description="Canned")
    await memory.record_ordered(session, user_id, search_term="black beans", upc="bb1", description="Canned")
    await memory.record_swap(session, user_id, search_term="black beans", upc="bb2", description="Organic")
    await session.commit()

    rows = {r.upc: r for r in await _rows(session, user_id, "black beans")}
    assert rows["bb2"].preferred is True
    assert rows["bb2"].source == "swap"
    assert rows["bb2"].times_ordered == 0  # a swap is a preference, not a buy
    assert rows["bb1"].preferred is False  # sibling preference cleared
    assert rows["bb1"].times_ordered == 2


async def test_swap_onto_existing_row_keeps_history_flips_preferred(session):
    user_id = await _user(session)
    await memory.record_ordered(session, user_id, search_term="milk", upc="m1")
    await memory.record_ordered(session, user_id, search_term="milk", upc="m1")
    await memory.record_ordered(session, user_id, search_term="milk", upc="m2")
    await memory.record_ordered(session, user_id, search_term="milk", upc="m2")
    await memory.record_swap(session, user_id, search_term="milk", upc="m1")
    await session.commit()

    rows = {r.upc: r for r in await _rows(session, user_id, "milk")}
    assert rows["m1"].preferred is True and rows["m1"].times_ordered == 2  # history kept
    assert rows["m2"].preferred is False


def test_pick_usual_prefers_preferred_then_frequent_then_seeded():
    def row(**kw):
        return ProductMemory(user_id="u", food_key="f", upc=kw.pop("upc"), **kw)

    preferred = row(upc="p", preferred=True, times_ordered=1, source="swap")
    frequent = row(upc="q", preferred=False, times_ordered=5, source="order")
    seeded = row(upc="r", preferred=False, times_ordered=0, source="pinned")
    once = row(upc="s", preferred=False, times_ordered=1, source="order")

    assert memory.pick_usual([once, frequent, seeded, preferred]).upc == "p"
    assert memory.pick_usual([once, frequent, seeded]).upc == "q"  # highest times_ordered>=2
    assert memory.pick_usual([once, seeded]).upc == "r"  # seeded over a single order
    assert memory.pick_usual([once]) is None  # a single order is not yet a usual
    assert memory.pick_usual([]) is None


async def test_list_usuals_filters_and_orders(session):
    user_id = await _user(session)
    # once-ordered → excluded; twice-ordered → included; pinned → included first.
    await memory.record_ordered(session, user_id, search_term="rice", upc="rice1")
    await memory.record_ordered(session, user_id, search_term="pasta", upc="pasta1")
    await memory.record_ordered(session, user_id, search_term="pasta", upc="pasta1")
    await memory.pin(session, user_id, food_key="oil", upc="oil1", description="Olive Oil", source="pinned")
    await session.commit()

    usuals = await memory.list_usuals(session, user_id, limit=12)
    upcs = [u.upc for u in usuals]
    assert "rice1" not in upcs  # only ordered once
    assert set(upcs) == {"oil1", "pasta1"}
    assert upcs[0] == "oil1"  # preferred/seeded first


async def test_hide_unhide_and_remove_semantics(session):
    user_id = await _user(session)
    await memory.record_ordered(session, user_id, search_term="eggs", upc="egg1")
    await memory.record_ordered(session, user_id, search_term="eggs", upc="egg1")
    await memory.pin(session, user_id, food_key="salt", upc="salt1", source="pinned")
    await session.commit()

    # hide/unhide toggles the flag.
    await memory.set_hidden(session, user_id, "egg1", True)
    await session.commit()
    assert (await _rows(session, user_id, "eggs"))[0].hidden is True
    await memory.set_hidden(session, user_id, "egg1", False)
    await session.commit()
    assert (await _rows(session, user_id, "eggs"))[0].hidden is False

    # remove: pinned row hard-deleted, ordered row hidden (history kept).
    await memory.remove(session, user_id, "salt1")
    await memory.remove(session, user_id, "egg1")
    await session.commit()
    assert await _rows(session, user_id, "salt") == []  # pinned hard-deleted
    egg_rows = await _rows(session, user_id, "eggs")
    assert len(egg_rows) == 1 and egg_rows[0].hidden is True  # order-derived hidden


async def test_remove_missing_returns_zero(session):
    user_id = await _user(session)
    assert await memory.remove(session, user_id, "nope") == 0
    assert await memory.set_hidden(session, user_id, "nope", True) == 0
