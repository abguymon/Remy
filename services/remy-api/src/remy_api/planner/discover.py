"""Discover step (FR-1–FR-5): per-meal recipe candidate discovery.

For each extracted meal, concurrently (bounded by a semaphore) search the user's
saved recipes (FTS + P2 relevance filter) and the web (favorite sites first via
``site:`` restriction, then general fill), drop listicles (regex prefilter + P3),
dedup per Appendix A.7 (URL first, then name+domain; saved > favorite > web), and
fetch thumbnails. Each meal's results are persisted as it completes so
``GET /plan/state`` streams granular per-meal progress. A source failure is
recorded as a per-meal degraded marker — search never silently empties (§9.1).
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from sqlalchemy import select

from remy_api.llm.errors import LLMError
from remy_api.models import Plan, PlanStatus, UserSettings
from remy_api.planner import deps
from remy_api.planner.schemas import Candidate, Meal, MealCandidates, MealStatus, Origin
from remy_api.prompts import listicle_filter, saved_recipe_relevance
from remy_api.search.base import SearchError, SearchResult

logger = logging.getLogger("remy.planner.discover")

_MEAL_CONCURRENCY = 6
_MAX_CANDIDATES = 5
_MAX_FAVORITE_SITES = 4
_SAVED_SEARCH_LIMIT = 8


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc or None


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    path = parsed.path.rstrip("/").lower()
    return f"{host}{path}" if host else url.rstrip("/").lower()


def _dedup(candidates: list[Candidate]) -> list[Candidate]:
    """Dedup by normalized URL, then (name, domain). Input order = priority (A.7)."""
    seen_urls: set[str] = set()
    seen_name_domain: set[tuple[str, str]] = set()
    out: list[Candidate] = []
    for c in candidates:
        nurl = _normalize_url(c.url) if c.url else None
        name_key = (c.title.strip().lower(), (c.source_domain or "").lower())
        if nurl and nurl in seen_urls:
            continue
        # Only collapse by name+domain when both are present (two sites' "Tacos"
        # are legitimately different recipes — do not merge across domains).
        if name_key[0] and name_key[1] and name_key in seen_name_domain:
            continue
        if nurl:
            seen_urls.add(nurl)
        if name_key[0] and name_key[1]:
            seen_name_domain.add(name_key)
        out.append(c)
    return out


# --- saved-recipe source -----------------------------------------------------


async def _discover_saved(meal: Meal, user_id: str) -> list[Candidate]:
    """Saved recipes via FTS, filtered by P2 relevance (loosened when vague)."""
    from remy_api.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        recipes = await deps.search_recipes(session, meal.query, _SAVED_SEARCH_LIMIT, user_id=user_id)
        if not recipes:
            return []
        # Materialize the fields we need before the session closes.
        rows = [
            {
                "id": r.id,
                "title": r.title,
                "total_time": r.total_time,
                "has_image": bool(r.image_path),
                "key_ingredients": [ing.food or ing.raw for ing in r.ingredients][:8],
            }
            for r in recipes
        ]

    candidates_in = [
        saved_recipe_relevance.RecipeCandidate(title=row["title"], key_ingredients=row["key_ingredients"])
        for row in rows
    ]
    keep = set(range(len(rows)))
    try:
        out = await deps.get_llm_client().structured(
            saved_recipe_relevance.render(
                saved_recipe_relevance.SavedRecipeRelevanceInput(
                    query=meal.query or meal.verbatim,
                    is_specific=meal.is_specific,
                    candidates=candidates_in,
                )
            ),
            saved_recipe_relevance.SavedRecipeRelevanceOutput,
        )
        keep = {i for i in out.relevant_indices if 0 <= i < len(rows)}
    except LLMError as exc:
        # Relevance is a refinement, not a gate: on LLM failure keep FTS order
        # rather than dropping the whole saved source.
        logger.info("saved relevance filter failed for %r: %s", meal.query, exc)

    return [
        Candidate(
            id=f"saved:{row['id']}",
            title=row["title"],
            source_domain="saved",
            saved_recipe_id=row["id"],
            thumbnail=f"/recipes/{row['id']}/image" if row["has_image"] else None,
            total_time=row["total_time"],
            origin=Origin.SAVED,
        )
        for i, row in enumerate(rows)
        if i in keep
    ]


# --- web source --------------------------------------------------------------


async def _web_search(meal: Meal, favorite_sites: list[str]) -> list[tuple[SearchResult, bool]]:
    """Run favorite-site and general searches concurrently; partial results OK.

    Returns ``(result, is_favorite)`` pairs, favorites first. Raises
    :class:`SearchError` only when *every* underlying search failed.
    """
    provider = deps.get_search_provider()
    sites = favorite_sites[:_MAX_FAVORITE_SITES]

    async def fav(site: str) -> tuple[str, list[SearchResult] | SearchError]:
        try:
            return site, await provider.search(meal.query, site=site, max_results=3)
        except SearchError as exc:
            return site, exc

    async def general() -> list[SearchResult] | SearchError:
        try:
            return await provider.search(meal.query, site=None, max_results=8)
        except SearchError as exc:
            return exc

    fav_out, gen_out = await asyncio.gather(
        asyncio.gather(*(fav(s) for s in sites)) if sites else _empty(),
        general(),
    )

    any_ok = False
    pairs: list[tuple[SearchResult, bool]] = []
    for _site, res in fav_out:
        if isinstance(res, SearchError):
            continue
        any_ok = True
        pairs.extend((r, True) for r in res)
    if isinstance(gen_out, SearchError):
        if not any_ok:
            raise gen_out
    else:
        any_ok = True
        favorite_domains = {_domain(f"https://{s}") or s for s in favorite_sites}
        for r in gen_out:
            pairs.append((r, (_domain(r.url) in favorite_domains)))
    if not any_ok:
        raise SearchError("All web searches failed for this meal.")
    return pairs


async def _empty() -> list:
    return []


async def _discover_web(meal: Meal, favorite_sites: list[str]) -> list[Candidate]:
    pairs = await _web_search(meal, favorite_sites)
    if not pairs:
        return []

    # Regex prefilter + P3 listicle filter over the surviving candidates.
    search_cands = [listicle_filter.SearchCandidate(title=r.title, url=r.url, snippet=r.snippet) for r, _ in pairs]
    survivors, _dropped = listicle_filter.prefilter_listicles(search_cands)
    keep = set(survivors)
    if survivors:
        try:
            out = await deps.get_llm_client().structured(
                listicle_filter.render(
                    listicle_filter.ListicleFilterInput(
                        query=meal.query or meal.verbatim,
                        candidates=[search_cands[i] for i in survivors],
                    )
                ),
                listicle_filter.ListicleFilterOutput,
            )
            kept_local = {survivors[i] for i in out.keep_indices if 0 <= i < len(survivors)}
            keep = kept_local
        except LLMError as exc:
            logger.info("listicle filter failed for %r: %s", meal.query, exc)
            keep = set(survivors)  # keep regex survivors rather than drop the source

    candidates: list[Candidate] = []
    for i, (r, is_fav) in enumerate(pairs):
        if i not in keep:
            continue
        domain = _domain(r.url)
        candidates.append(
            Candidate(
                id=f"web:{i}",
                title=r.title,
                source_domain=domain,
                url=r.url,
                origin=Origin.FAVORITE if is_fav else Origin.WEB,
            )
        )
    # Favorites first, preserving order.
    candidates.sort(key=lambda c: 0 if c.origin == Origin.FAVORITE else 1)
    return candidates


# --- per-meal orchestration --------------------------------------------------


async def discover_meal(meal: Meal, favorite_sites: list[str], user_id: str) -> MealCandidates:
    """Discover candidates for one meal, tolerating single-source failures."""
    if meal.url:
        # URL-type meal (FR-1): the pasted link becomes a pre-selected candidate.
        thumbs = {}
        try:
            thumbs = await deps.fetch_thumbnails([meal.url])
        except Exception:  # noqa: BLE001 - thumbnails are cosmetic
            thumbs = {}
        return MealCandidates(
            meal_id=meal.id,
            status=MealStatus.READY,
            candidates=[
                Candidate(
                    id="url:0",
                    title=meal.verbatim or meal.url,
                    source_domain=_domain(meal.url),
                    url=meal.url,
                    thumbnail=thumbs.get(meal.url),
                    origin=Origin.WEB,
                    preselected=True,
                )
            ],
        )

    source_errors: list[str] = []
    saved: list[Candidate] = []
    web: list[Candidate] = []

    saved_res, web_res = await asyncio.gather(
        _discover_saved(meal, user_id),
        _discover_web(meal, favorite_sites),
        return_exceptions=True,
    )
    if isinstance(saved_res, Exception):
        logger.info("saved discovery failed for %r: %s", meal.query, saved_res)
        source_errors.append("saved_search_failed")
    else:
        saved = saved_res
    if isinstance(web_res, Exception):
        logger.info("web discovery failed for %r: %s", meal.query, web_res)
        source_errors.append("web_search_failed")
    else:
        web = web_res

    merged = _dedup([*saved, *web])[:_MAX_CANDIDATES]

    # Thumbnails for web candidates (cosmetic; never blocks).
    web_urls = [c.url for c in merged if c.url and c.origin != Origin.SAVED]
    if web_urls:
        try:
            thumbs = await deps.fetch_thumbnails(web_urls)
            for c in merged:
                if c.url and c.thumbnail is None:
                    c.thumbnail = thumbs.get(c.url)
        except Exception as exc:  # noqa: BLE001 - cosmetic
            logger.debug("thumbnail fetch failed: %s", exc)

    if source_errors and not merged:
        status = MealStatus.ERROR
    elif source_errors:
        status = MealStatus.DEGRADED
    else:
        status = MealStatus.READY
    return MealCandidates(meal_id=meal.id, status=status, candidates=merged, source_errors=source_errors)


async def run_discover(plan_id: str) -> None:
    """Background entrypoint: fan out per-meal discovery, then open the select gate.

    Runs under its own sessions (the request session is long gone). Per-meal
    results are persisted incrementally, serialized by a write lock so concurrent
    meal tasks can't clobber the shared ``candidates`` JSON column.
    """
    from remy_api.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        plan = await session.get(Plan, plan_id)
        if plan is None or plan.status != PlanStatus.DISCOVERING:
            return
        meals = [Meal(**m) for m in (plan.meals or [])]
        user_id = plan.user_id
        settings_row = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        settings = settings_row.scalar_one_or_none()
        favorite_sites = list(settings.favorite_sites) if settings else []
        # Seed all meals as "searching" so the UI shows per-meal skeletons.
        plan.candidates = {
            m.id: MealCandidates(meal_id=m.id, status=MealStatus.SEARCHING).model_dump(mode="json") for m in meals
        }
        await session.commit()

    if not meals:
        return

    write_lock = asyncio.Lock()
    sem = asyncio.Semaphore(_MEAL_CONCURRENCY)

    async def _one(meal: Meal) -> None:
        async with sem:
            try:
                mc = await discover_meal(meal, favorite_sites, user_id)
            except Exception as exc:  # noqa: BLE001 - never let one meal sink the run
                logger.warning("discover_meal crashed for %r: %s", meal.query, exc)
                mc = MealCandidates(meal_id=meal.id, status=MealStatus.ERROR, source_errors=["discover_error"])
        async with write_lock, factory() as s:
            plan = await s.get(Plan, plan_id)
            if plan is None or plan.status == PlanStatus.ABANDONED:
                return
            current = dict(plan.candidates or {})
            current[meal.id] = mc.model_dump(mode="json")
            plan.candidates = current
            await s.commit()

    await asyncio.gather(*(_one(m) for m in meals))

    async with factory() as session:
        plan = await session.get(Plan, plan_id)
        if plan is not None and plan.status == PlanStatus.DISCOVERING:
            plan.status = PlanStatus.SELECTING
            await session.commit()
