"""Recipe store: CRUD over ``Recipe``/``RecipeIngredient`` + full-text search.

Search design
-------------
An SQLite **FTS5** virtual table (``recipe_fts``) indexes each recipe's title and
the text of its ingredient lines (parsed ``food`` name when present, else the raw
line). We keep it in sync via **explicit sync on write** from this module rather
than SQL triggers, because:

* the indexed text spans two tables (``recipes.title`` + ``recipe_ingredients``),
  which would need multiple cross-table triggers that are easy to get subtly
  wrong; and
* every write already flows through this module, so a single ``_sync_fts`` call
  per create/update/delete is simpler and keeps the logic in one place.

Search results are always re-joined to user-scoped ``recipes`` rows, so a stale
FTS entry (e.g. pointing at a deleted recipe) can never leak another user's data
or a ghost result — it simply matches nothing.

If FTS5 is unavailable (older SQLite, or a Postgres deployment), search degrades
gracefully to an ``ILIKE`` scan over title + ingredient foods.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.errors import NotFoundError
from remy_api.models import Recipe, RecipeIngredient
from remy_api.recipes.images import delete_recipe_image
from remy_api.recipes.schemas import ParsedRecipe, RecipeUpdate

logger = logging.getLogger("remy.recipes.store")

# Cached FTS5-availability probe result (None = not yet probed).
_fts_available: bool | None = None


# --- slug helpers ------------------------------------------------------------


def _slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug or "recipe"


async def _unique_slug(session: AsyncSession, user_id: str, title: str) -> str:
    """Return a per-user-unique slug derived from ``title``."""
    base = _slugify(title)
    slug = base
    n = 2
    while True:
        exists = await session.execute(select(Recipe.id).where(Recipe.user_id == user_id, Recipe.slug == slug))
        if exists.scalar_one_or_none() is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


# --- FTS plumbing ------------------------------------------------------------


async def _ensure_fts(session: AsyncSession) -> bool:
    """Create the FTS5 table if possible; cache and return availability."""
    global _fts_available
    if _fts_available is not None:
        return _fts_available
    if session.bind is None or session.bind.dialect.name != "sqlite":
        _fts_available = False
        return False
    try:
        await session.execute(
            text("CREATE VIRTUAL TABLE IF NOT EXISTS recipe_fts USING fts5(recipe_id UNINDEXED, title, foods)")
        )
        await session.commit()
        _fts_available = True
    except Exception as exc:  # noqa: BLE001 - FTS5 not compiled in
        logger.warning("FTS5 unavailable, falling back to ILIKE search: %s", exc)
        await session.rollback()
        _fts_available = False
    return _fts_available


def _fts_document(recipe: Recipe) -> str:
    """The searchable ingredient text: parsed food names, else raw lines."""
    parts: list[str] = []
    for ing in recipe.ingredients:
        parts.append(ing.food or ing.raw)
    return " ".join(p for p in parts if p)


async def _sync_fts(session: AsyncSession, recipe: Recipe) -> None:
    if not await _ensure_fts(session):
        return
    await session.execute(text("DELETE FROM recipe_fts WHERE recipe_id = :rid"), {"rid": recipe.id})
    await session.execute(
        text("INSERT INTO recipe_fts (recipe_id, title, foods) VALUES (:rid, :title, :foods)"),
        {"rid": recipe.id, "title": recipe.title, "foods": _fts_document(recipe)},
    )


async def _delete_fts(session: AsyncSession, recipe_id: str) -> None:
    if not await _ensure_fts(session):
        return
    await session.execute(text("DELETE FROM recipe_fts WHERE recipe_id = :rid"), {"rid": recipe_id})


def _fts_match_query(query: str) -> str:
    """Build a safe FTS5 MATCH string: quoted prefix terms OR-joined.

    Quoting each token neutralizes FTS5 operators/punctuation; the trailing ``*``
    makes each a prefix match so "chick" finds "chicken". OR-joining favors
    recall — bm25 ranking still surfaces the strongest matches first.
    """
    tokens = re.findall(r"\w+", query.lower())
    if not tokens:
        return ""
    return " OR ".join(f'"{tok}"*' for tok in tokens)


# --- CRUD --------------------------------------------------------------------


async def create_recipe(
    session: AsyncSession,
    user_id: str,
    parsed: ParsedRecipe,
    *,
    image_path: str | None = None,
    mealie_slug: str | None = None,
) -> Recipe:
    """Persist a parsed recipe and its ingredient lines; sync FTS."""
    slug = await _unique_slug(session, user_id, parsed.title)
    recipe = Recipe(
        user_id=user_id,
        title=parsed.title,
        slug=slug,
        source_url=parsed.source_url,
        image_path=image_path,
        mealie_slug=mealie_slug,
        recipe_yield=parsed.recipe_yield,
        prep_time=parsed.prep_time,
        cook_time=parsed.cook_time,
        total_time=parsed.total_time,
        instructions=list(parsed.instructions),
    )
    for position, ing in enumerate(parsed.ingredients):
        recipe.ingredients.append(
            RecipeIngredient(
                position=position,
                raw=ing.raw,
                quantity=ing.quantity,
                unit=ing.unit,
                food=ing.food,
                note=ing.note,
            )
        )
    session.add(recipe)
    await session.flush()
    await _sync_fts(session, recipe)
    await session.commit()
    await session.refresh(recipe)
    return recipe


async def get_recipe(session: AsyncSession, user_id: str, recipe_id: str) -> Recipe:
    """Fetch one user-scoped recipe or raise :class:`NotFoundError`."""
    recipe = await session.get(Recipe, recipe_id)
    if recipe is None or recipe.user_id != user_id:
        raise NotFoundError("Recipe not found.")
    return recipe


async def list_recipes(session: AsyncSession, user_id: str, *, limit: int = 50, offset: int = 0) -> list[Recipe]:
    """List a user's recipes, most-recently-created first."""
    rows = await session.execute(
        select(Recipe).where(Recipe.user_id == user_id).order_by(Recipe.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().all())


async def search_recipes(
    session: AsyncSession,
    query: str,
    limit: int = 10,
    *,
    user_id: str,
) -> list[Recipe]:
    """Ranked full-text search over title + ingredient foods, user-scoped.

    This is the "saved recipes first" source the planner uses (FR-2). Falls back
    to ``ILIKE`` if FTS5 is unavailable. An empty/blank query returns the most
    recent recipes (list behavior).
    """
    query = (query or "").strip()
    if not query:
        return await list_recipes(session, user_id, limit=limit)

    if await _ensure_fts(session):
        match = _fts_match_query(query)
        if match:
            rows = await session.execute(
                text("SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH :q ORDER BY rank LIMIT :lim"),
                {"q": match, "lim": limit},
            )
            ranked_ids = [r[0] for r in rows.all()]
            if not ranked_ids:
                return []
            found = await session.execute(select(Recipe).where(Recipe.user_id == user_id, Recipe.id.in_(ranked_ids)))
            by_id = {r.id: r for r in found.scalars().all()}
            # Preserve FTS rank order; drop ids not owned by this user.
            return [by_id[rid] for rid in ranked_ids if rid in by_id]

    # ILIKE fallback: title match OR any ingredient food/raw match.
    like = f"%{query}%"
    rows = await session.execute(
        select(Recipe)
        .outerjoin(RecipeIngredient, RecipeIngredient.recipe_id == Recipe.id)
        .where(
            Recipe.user_id == user_id,
            or_(
                Recipe.title.ilike(like),
                func.coalesce(RecipeIngredient.food, "").ilike(like),
                RecipeIngredient.raw.ilike(like),
            ),
        )
        .group_by(Recipe.id)
        .order_by(Recipe.created_at.desc())
        .limit(limit)
    )
    return list(rows.scalars().all())


def _apply_updates(recipe: Recipe, updates: RecipeUpdate) -> None:
    data = updates.model_dump(exclude_unset=True, exclude={"ingredients"})
    for field, value in data.items():
        setattr(recipe, field, value)


async def update_recipe(
    session: AsyncSession,
    user_id: str,
    recipe_id: str,
    updates: RecipeUpdate,
) -> Recipe:
    """Edit recipe fields (FR-8); ``updates.ingredients`` replaces all lines."""
    recipe = await get_recipe(session, user_id, recipe_id)
    _apply_updates(recipe, updates)
    if updates.ingredients is not None:
        recipe.ingredients.clear()
        await session.flush()
        for position, ing in enumerate(updates.ingredients):
            recipe.ingredients.append(
                RecipeIngredient(
                    position=position,
                    raw=ing.raw,
                    quantity=ing.quantity,
                    unit=ing.unit,
                    food=ing.food,
                    note=ing.note,
                )
            )
    await session.flush()
    await _sync_fts(session, recipe)
    await session.commit()
    await session.refresh(recipe)
    return recipe


async def mark_cooked(session: AsyncSession, user_id: str, recipe_id: str) -> Recipe:
    """Stamp ``last_cooked_at`` = now (FR-20)."""
    from remy_api.models import _now  # local import to reuse the model clock

    recipe = await get_recipe(session, user_id, recipe_id)
    recipe.last_cooked_at = _now()
    await session.commit()
    await session.refresh(recipe)
    return recipe


async def delete_recipe(session: AsyncSession, user_id: str, recipe_id: str) -> None:
    """Delete a recipe (cascades to ingredients), its FTS row, and its image."""
    recipe = await get_recipe(session, user_id, recipe_id)
    await _delete_fts(session, recipe_id)
    await session.delete(recipe)
    await session.commit()
    delete_recipe_image(recipe_id)


async def find_by_mealie_slug(session: AsyncSession, user_id: str, mealie_slug: str) -> Recipe | None:
    """Lookup used by the Mealie importer for idempotency."""
    rows = await session.execute(select(Recipe).where(Recipe.user_id == user_id, Recipe.mealie_slug == mealie_slug))
    return rows.scalar_one_or_none()
