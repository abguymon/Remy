"""One-shot Mealie → Remy import (PRD §5, FR-9 note).

Pages through a Mealie instance's ``/api/recipes``, fetches each recipe detail,
maps it into the Remy recipe store, and downloads the image. Idempotent by
Mealie slug (``Recipe.mealie_slug``): a re-run skips recipes already imported.

Field mapping note: Mealie *does* provide parsed ``{quantity, unit, food}`` per
ingredient, but we intentionally store only the **raw line** and leave the parsed
fields null. Structured parsing (FR-9, prompt P4a) is the planner's job (T4/T5),
run consistently for every recipe regardless of source. See ``_ingredient_raw``.

Mealie API shapes referenced from ``legacy/services/mealie-mcp-server/src/mealie``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.recipes.images import download_recipe_image
from remy_api.recipes.schemas import ParsedIngredient, ParsedRecipe
from remy_api.recipes.store import create_recipe, find_by_mealie_slug

logger = logging.getLogger("remy.recipes.mealie_import")

_PER_PAGE = 50
_TIMEOUT = 30.0


@dataclass
class ImportStats:
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        line = f"imported={self.imported} skipped={self.skipped} failed={self.failed}"
        if self.errors:
            line += "\n" + "\n".join(f"  - {e}" for e in self.errors)
        return line


def _coerce_time(value: object) -> str | None:
    """Normalize a Mealie time value (int minutes or free string) to a string."""
    if value is None or value == "" or value == 0:
        return None
    if isinstance(value, int | float):
        minutes = int(value)
        if minutes <= 0:
            return None
        hours, mins = divmod(minutes, 60)
        if hours and mins:
            return f"{hours} hr {mins} min"
        return f"{hours} hr" if hours else f"{mins} min"
    return str(value).strip() or None


def _ingredient_raw(item: dict) -> str | None:
    """Best raw line for a Mealie ingredient (parsed fields deliberately dropped)."""
    for key in ("originalText", "display", "note"):
        val = item.get(key)
        if val and str(val).strip():
            return str(val).strip()
    # Last resort: reconstruct from parsed parts.
    parts = [str(item.get(k)) for k in ("quantity", "unit", "food") if item.get(k)]
    joined = " ".join(parts).strip()
    return joined or None


def map_recipe(detail: dict, base_url: str) -> tuple[ParsedRecipe, str, str | None]:
    """Map a Mealie recipe-detail payload to ``(ParsedRecipe, slug, image_url)``."""
    slug = detail.get("slug") or detail.get("id") or ""
    ingredients: list[ParsedIngredient] = []
    for item in detail.get("recipeIngredient", []) or []:
        raw = _ingredient_raw(item)
        if raw:
            ingredients.append(ParsedIngredient(raw=raw))  # parsed fields left null (P4a)
    instructions = [
        str(step.get("text")).strip()
        for step in (detail.get("recipeInstructions") or [])
        if step.get("text") and str(step.get("text")).strip()
    ]
    parsed = ParsedRecipe(
        title=(detail.get("name") or slug or "Untitled").strip(),
        source_url=detail.get("orgURL"),
        recipe_yield=detail.get("recipeYield"),
        prep_time=_coerce_time(detail.get("prepTime")),
        cook_time=_coerce_time(detail.get("cookTime") or detail.get("performTime")),
        total_time=_coerce_time(detail.get("totalTime")),
        ingredients=ingredients,
        instructions=instructions,
    )
    image_url = None
    recipe_id = detail.get("id")
    if recipe_id and detail.get("image"):
        image_url = f"{base_url.rstrip('/')}/api/media/recipes/{recipe_id}/images/original.webp"
    return parsed, slug, image_url


async def _iter_recipe_slugs(client: httpx.AsyncClient) -> list[str]:
    """Page through ``/api/recipes`` and return all recipe slugs."""
    slugs: list[str] = []
    page = 1
    while True:
        resp = await client.get("/api/recipes", params={"page": page, "perPage": _PER_PAGE})
        resp.raise_for_status()
        body = resp.json()
        items = body.get("items", []) if isinstance(body, dict) else []
        if not items:
            break
        for item in items:
            slug = item.get("slug")
            if slug:
                slugs.append(slug)
        total_pages = body.get("total_pages") or body.get("totalPages")
        if total_pages is not None and page >= int(total_pages):
            break
        if len(items) < _PER_PAGE:
            break
        page += 1
    return slugs


async def import_mealie(
    session: AsyncSession,
    user_id: str,
    base_url: str,
    api_key: str,
    *,
    dry_run: bool = False,
    client: httpx.AsyncClient | None = None,
) -> ImportStats:
    """Import all recipes from a Mealie instance for ``user_id``.

    Idempotent: recipes whose Mealie slug already exists for this user are
    skipped. With ``dry_run`` no writes or image downloads happen — it reports
    what *would* be imported.
    """
    stats = ImportStats()
    owns_client = client is None
    auth_headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=auth_headers, timeout=_TIMEOUT)
    try:
        slugs = await _iter_recipe_slugs(client)
        logger.info("Mealie reports %d recipes", len(slugs))
        for slug in slugs:
            try:
                existing = await find_by_mealie_slug(session, user_id, slug)
                if existing is not None:
                    stats.skipped += 1
                    continue
                resp = await client.get(f"/api/recipes/{slug}")
                resp.raise_for_status()
                detail = resp.json()
                parsed, mslug, image_url = map_recipe(detail, base_url)
                if dry_run:
                    stats.imported += 1
                    logger.info("[dry-run] would import '%s' (%d ingredients)", parsed.title, len(parsed.ingredients))
                    continue
                recipe = await create_recipe(session, user_id, parsed, mealie_slug=mslug or slug)
                if image_url:
                    stored = await download_recipe_image(recipe.id, image_url, client=client, headers=auth_headers)
                    if stored:
                        recipe.image_path = stored
                        await session.commit()
                stats.imported += 1
            except httpx.HTTPError as exc:
                stats.failed += 1
                stats.errors.append(f"{slug}: {exc}")
                logger.warning("Failed to import Mealie recipe %s: %s", slug, exc)
            except Exception as exc:  # noqa: BLE001 - keep importing the rest
                stats.failed += 1
                stats.errors.append(f"{slug}: {exc}")
                logger.warning("Unexpected error importing %s: %s", slug, exc)
    finally:
        if owns_client:
            await client.aclose()
    return stats
