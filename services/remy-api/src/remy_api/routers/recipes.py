"""Recipe collection API (FR-19/FR-20, PRD §2.5).

All routes are authed via :data:`CurrentUser` and user-scoped through the store.
Recipe responses carry an ``image_url`` the frontend can use directly; the bytes
are served by ``GET /recipes/{id}/image`` from the local image directory (never
hotlinked, PRD §5).
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse

from remy_api.deps import CurrentUser, SessionDep
from remy_api.errors import NotFoundError
from remy_api.llm.client import get_llm_client
from remy_api.llm.registry import get_prompt_id_llm
from remy_api.models import Recipe
from remy_api.prompts import recipe_extraction, recipe_from_images
from remy_api.recipes import store
from remy_api.recipes.documents import MAX_FILES, RawUpload, build_extraction
from remy_api.recipes.images import download_recipe_image, image_path_for, store_image_bytes
from remy_api.recipes.llm_fallback import recipe_from_extraction
from remy_api.recipes.schemas import (
    IngredientOut,
    LLMRecipeExtraction,
    ParsedRecipe,
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


@router.post("/from-upload", response_model=RecipeDetail, status_code=status.HTTP_201_CREATED)
async def create_recipe_from_upload(
    user: CurrentUser,
    session: SessionDep,
    files: list[UploadFile] = File(..., description=f"1..{MAX_FILES} images and/or a PDF."),
    hint: str | None = Form(default=None, description="Optional hint, e.g. 'the pasta recipe on the left page'."),
) -> RecipeDetail:
    """Create a recipe from uploaded photos or a PDF (FR-6).

    Text-native PDFs route through the text-extraction prompt; images and
    scanned PDFs route through the multimodal vision prompt. Either way the
    result is validated (``found=false`` / incomplete raises a 422 with reasons,
    matching ``/recipes/from-url``) and the first page/photo becomes the image.
    """
    uploads = [
        RawUpload(filename=f.filename or "upload", content_type=f.content_type, data=await f.read()) for f in files
    ]
    extraction = build_extraction(uploads)

    if extraction.mode == "text":
        rendered = recipe_extraction.render(
            recipe_extraction.RecipeExtractionInput(page_text=extraction.text or "", source_url="uploaded PDF")
        )
    else:
        rendered = recipe_from_images.render(
            recipe_from_images.RecipeFromImagesInput(images=extraction.images, hint=hint)
        )
    result = await get_llm_client().structured(rendered, LLMRecipeExtraction)
    parsed: ParsedRecipe = recipe_from_extraction(result, source_url=None)

    recipe = await store.create_recipe(session, user.id, parsed)
    if extraction.cover_jpeg:
        stored = store_image_bytes(recipe.id, extraction.cover_jpeg)
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
