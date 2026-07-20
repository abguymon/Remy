"""Purchase memory ("usuals") data access — writers, reader, and queries.

One place for every read/write of the ``product_memory`` table so the planner
(execute writer, swap writer, match short-circuit reader), the usuals endpoints,
and the receipt import all share the same upsert + selection semantics. None of
these helpers commit; the caller owns the transaction (matching the rest of the
planner, which commits once per step).

Selection rule for the match short-circuit and the usuals list (in order):

1. a ``preferred=True`` row (set on swap / manual pin);
2. else the highest ``times_ordered >= 2`` row (frequent buy);
3. else any ``source in ('pinned', 'import')`` row (explicitly seeded).

Hidden rows never participate in matching or the usuals list.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.models import ProductMemory

# Sources that count as an explicit user seed even without an order/swap history.
_SEEDED_SOURCES = ("pinned", "import")


def _now() -> datetime:
    return datetime.now(UTC)


def food_key(term: str | None) -> str:
    """Canonical lookup key: the trimmed, lowercased search-term/ingredient."""
    return (term or "").strip().lower()


def _refresh_fields(
    row: ProductMemory,
    *,
    description: str | None,
    size: str | None,
    image_url: str | None,
    price: float | None,
) -> None:
    """Refresh the cached product snapshot, keeping existing values when a field
    is missing (a later search that dropped an image shouldn't blank it)."""
    if description is not None:
        row.description = description
    if size is not None:
        row.size = size
    if image_url is not None:
        row.image_url = image_url
    if price is not None:
        row.last_price = price
    row.updated_at = _now()


async def _rows_for_food(session: AsyncSession, user_id: str, fkey: str) -> list[ProductMemory]:
    result = await session.execute(
        select(ProductMemory).where(ProductMemory.user_id == user_id, ProductMemory.food_key == fkey)
    )
    return list(result.scalars().all())


async def rows_for_upc(session: AsyncSession, user_id: str, upc: str) -> list[ProductMemory]:
    """All memory rows (any food_key) for a UPC — used by hide/unhide/delete/add_upc."""
    result = await session.execute(
        select(ProductMemory).where(ProductMemory.user_id == user_id, ProductMemory.upc == upc)
    )
    return list(result.scalars().all())


def pick_usual(rows: list[ProductMemory] | None) -> ProductMemory | None:
    """Choose the memory row that should win the match short-circuit (see rule)."""
    if not rows:
        return None
    visible = [r for r in rows if not r.hidden]
    if not visible:
        return None
    preferred = [r for r in visible if r.preferred]
    if preferred:
        # Most recently touched preferred row wins if several are flagged.
        return max(preferred, key=lambda r: r.updated_at or datetime.min.replace(tzinfo=UTC))
    frequent = [r for r in visible if r.times_ordered >= 2]
    if frequent:
        return max(
            frequent,
            key=lambda r: (r.times_ordered, r.last_ordered_at or datetime.min.replace(tzinfo=UTC)),
        )
    seeded = [r for r in visible if r.source in _SEEDED_SOURCES]
    if seeded:
        return max(seeded, key=lambda r: r.updated_at or datetime.min.replace(tzinfo=UTC))
    return None


async def load_usuals_map(session: AsyncSession, user_id: str) -> dict[str, list[ProductMemory]]:
    """All non-hidden memory rows grouped by ``food_key`` for the match reader.

    Preloaded once at the start of a match run so the concurrent per-item search
    phase never touches the DB just to check for a usual.
    """
    result = await session.execute(
        select(ProductMemory).where(ProductMemory.user_id == user_id, ProductMemory.hidden.is_(False))
    )
    grouped: dict[str, list[ProductMemory]] = {}
    for row in result.scalars().all():
        grouped.setdefault(row.food_key, []).append(row)
    return grouped


# --- writers -----------------------------------------------------------------


async def record_ordered(
    session: AsyncSession,
    user_id: str,
    *,
    search_term: str,
    upc: str,
    description: str | None = None,
    size: str | None = None,
    image_url: str | None = None,
    price: float | None = None,
) -> None:
    """Upsert on a successful cart add: bump ``times_ordered`` + stamp the time."""
    fkey = food_key(search_term)
    if not upc or not fkey:
        return
    rows = await _rows_for_food(session, user_id, fkey)
    row = next((r for r in rows if r.upc == upc), None)
    now = _now()
    if row is None:
        session.add(
            ProductMemory(
                user_id=user_id,
                food_key=fkey,
                upc=upc,
                description=description,
                size=size,
                image_url=image_url,
                last_price=price,
                times_ordered=1,
                last_ordered_at=now,
                source="order",
            )
        )
        return
    row.times_ordered += 1
    row.last_ordered_at = now
    row.hidden = False  # ordering it again un-hides a previously hidden usual
    _refresh_fields(row, description=description, size=size, image_url=image_url, price=price)


async def record_swap(
    session: AsyncSession,
    user_id: str,
    *,
    search_term: str,
    upc: str,
    description: str | None = None,
    size: str | None = None,
    image_url: str | None = None,
    price: float | None = None,
) -> None:
    """Upsert on a cart swap: mark the new UPC ``preferred`` and clear siblings.

    No ``times_ordered`` increment — a swap is a preference signal, not a buy.
    """
    fkey = food_key(search_term)
    if not upc or not fkey:
        return
    rows = await _rows_for_food(session, user_id, fkey)
    target: ProductMemory | None = None
    for row in rows:
        if row.upc == upc:
            target = row
        else:
            row.preferred = False
    if target is None:
        session.add(
            ProductMemory(
                user_id=user_id,
                food_key=fkey,
                upc=upc,
                description=description,
                size=size,
                image_url=image_url,
                last_price=price,
                times_ordered=0,
                source="swap",
                preferred=True,
            )
        )
        return
    target.preferred = True
    target.hidden = False
    _refresh_fields(target, description=description, size=size, image_url=image_url, price=price)


async def pin(
    session: AsyncSession,
    user_id: str,
    *,
    food_key: str,
    upc: str,
    description: str | None = None,
    size: str | None = None,
    image_url: str | None = None,
    price: float | None = None,
    source: str = "pinned",
) -> ProductMemory:
    """Manually pin (or import) a product as a usual: preferred, non-hidden."""
    fkey = food_key.strip().lower()
    rows = await _rows_for_food(session, user_id, fkey)
    for row in rows:
        if row.upc != upc:
            row.preferred = False
    target = next((r for r in rows if r.upc == upc), None)
    if target is None:
        target = ProductMemory(
            user_id=user_id,
            food_key=fkey,
            upc=upc,
            description=description,
            size=size,
            image_url=image_url,
            last_price=price,
            times_ordered=0,
            source=source,
            preferred=True,
        )
        session.add(target)
        return target
    target.preferred = True
    target.hidden = False
    # A re-pin of an order-derived row promotes it to a deliberate seed.
    if source in _SEEDED_SOURCES:
        target.source = source
    _refresh_fields(target, description=description, size=size, image_url=image_url, price=price)
    return target


async def set_hidden(session: AsyncSession, user_id: str, upc: str, hidden: bool) -> int:
    """Hide/unhide every memory row for a UPC. Returns the count touched."""
    rows = await rows_for_upc(session, user_id, upc)
    for row in rows:
        row.hidden = hidden
    return len(rows)


async def remove(session: AsyncSession, user_id: str, upc: str) -> int:
    """Remove a usual by UPC. Hard-delete seeded (pinned/import) rows; hide
    order/swap-derived rows (they carry buy history worth keeping). Returns the
    number of rows affected (0 → not found → caller 404s)."""
    rows = await rows_for_upc(session, user_id, upc)
    for row in rows:
        if row.source in _SEEDED_SOURCES:
            await session.delete(row)
        else:
            row.hidden = True
    return len(rows)


async def list_usuals(session: AsyncSession, user_id: str, limit: int) -> list[ProductMemory]:
    """The visible usuals list: non-hidden rows that are frequent, preferred, or
    seeded — ordered preferred/seeded first, then most-ordered, then most-recent."""
    result = await session.execute(
        select(ProductMemory).where(ProductMemory.user_id == user_id, ProductMemory.hidden.is_(False))
    )
    rows = [r for r in result.scalars().all() if r.preferred or r.times_ordered >= 2 or r.source in _SEEDED_SOURCES]

    def sort_key(r: ProductMemory) -> tuple:
        seeded_first = 0 if (r.preferred or r.source in _SEEDED_SOURCES) else 1
        last = r.last_ordered_at or datetime.min.replace(tzinfo=UTC)
        return (seeded_first, -r.times_ordered, -last.timestamp())

    rows.sort(key=sort_key)
    return rows[:limit]
