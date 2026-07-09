"""Recipe collection API (FR-19/FR-20, PRD §2.5).

All routes are authed via :data:`CurrentUser` and user-scoped through the store.
Recipe responses carry an ``image_url`` the frontend can use directly; the bytes
are served by ``GET /recipes/{id}/image`` from the local image directory (never
hotlinked, PRD §5).
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from fastapi.responses import FileResponse

from remy_api.deps import CurrentUser, SessionDep
from remy_api.errors import NotFoundError
from remy_api.llm.registry import get_prompt_id_llm
from remy_api.models import Recipe
from remy_api.recipes import store
from remy_api.recipes.images import download_recipe_image, image_path_for
from remy_api.recipes.schemas import (
    IngredientOut,
    RecipeDetail,
    RecipeFromUrl,
    RecipeSummary,
    RecipeUpdate,
)
from remy_api.recipes.scraper import scrape_recipe

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _image_url(recipe: Recipe) -> str | None:
    return f"/recipes/{recipe.id}/image" if recipe.image_path else None


def _to_summary(recipe: Recipe) -> RecipeSummary:
    return RecipeSummary(
        id=recipe.id,
        title=recipe.title,
        slug=recipe.slug,
        source_url=recipe.source_url,
        image_url=_image_url(recipe),
        total_time=recipe.total_time,
        created_at=recipe.created_at,
        last_cooked_at=recipe.last_cooked_at,
    )


def _to_detail(recipe: Recipe) -> RecipeDetail:
    return RecipeDetail(
        id=recipe.id,
        title=recipe.title,
        slug=recipe.slug,
        source_url=recipe.source_url,
        image_url=_image_url(recipe),
        total_time=recipe.total_time,
        created_at=recipe.created_at,
        last_cooked_at=recipe.last_cooked_at,
        recipe_yield=recipe.recipe_yield,
        prep_time=recipe.prep_time,
        cook_time=recipe.cook_time,
        instructions=list(recipe.instructions or []),
        ingredients=[IngredientOut.model_validate(i) for i in recipe.ingredients],
    )


@router.get("", response_model=list[RecipeSummary])
async def list_or_search_recipes(
    user: CurrentUser,
    session: SessionDep,
    q: str | None = Query(default=None, description="Full-text search over title + ingredients."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[RecipeSummary]:
    if q and q.strip():
        recipes = await store.search_recipes(session, q, limit, user_id=user.id)
    else:
        recipes = await store.list_recipes(session, user.id, limit=limit, offset=offset)
    return [_to_summary(r) for r in recipes]


@router.get("/{recipe_id}", response_model=RecipeDetail)
async def get_recipe(recipe_id: str, user: CurrentUser, session: SessionDep) -> RecipeDetail:
    recipe = await store.get_recipe(session, user.id, recipe_id)
    return _to_detail(recipe)


@router.get("/{recipe_id}/image")
async def get_recipe_image(recipe_id: str, user: CurrentUser, session: SessionDep) -> FileResponse:
    recipe = await store.get_recipe(session, user.id, recipe_id)
    path = image_path_for(recipe.id)
    if not recipe.image_path or not path.exists():
        raise NotFoundError("Recipe has no image.")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/from-url", response_model=RecipeDetail, status_code=status.HTTP_201_CREATED)
async def create_recipe_from_url(payload: RecipeFromUrl, user: CurrentUser, session: SessionDep) -> RecipeDetail:
    parsed = await scrape_recipe(payload.url, llm=get_prompt_id_llm())
    recipe = await store.create_recipe(session, user.id, parsed)
    if parsed.image_url:
        stored = await download_recipe_image(recipe.id, parsed.image_url)
        if stored:
            recipe.image_path = stored
            await session.commit()
            await session.refresh(recipe)
    return _to_detail(recipe)


@router.put("/{recipe_id}", response_model=RecipeDetail)
async def update_recipe(recipe_id: str, payload: RecipeUpdate, user: CurrentUser, session: SessionDep) -> RecipeDetail:
    recipe = await store.update_recipe(session, user.id, recipe_id, payload)
    return _to_detail(recipe)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(recipe_id: str, user: CurrentUser, session: SessionDep) -> None:
    await store.delete_recipe(session, user.id, recipe_id)


@router.post("/{recipe_id}/cooked", response_model=RecipeDetail)
async def mark_recipe_cooked(recipe_id: str, user: CurrentUser, session: SessionDep) -> RecipeDetail:
    recipe = await store.mark_cooked(session, user.id, recipe_id)
    return _to_detail(recipe)
