#!/usr/bin/env python3
"""Compare LLM vs TypeSafe Jev on the two discovery decisions, using real meals.

For each distinct meal from past plans:

- **saved_recipes** — which of the user's saved recipes (FTS hits) match the
  meal: P2 prompt vs Jev yes/no per recipe.
- **listicles** — which web-search results are single recipe pages (after the
  regex prefilter): P3 prompt vs Jev yes/no per result.

There are no ground-truth labels, so the script reports agreement and prints
every disagreement for a human to judge. Read-only (web search + model calls).
Run inside the API image on the compose network (needs SEARXNG_URL, the LLM key
and TYPESAFE_API_KEY), e.g.

    docker compose run --rm --no-deps remy-api python scripts/eval_discovery_decisions.py
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

from sqlalchemy import select

from remy_api.config import get_settings
from remy_api.db import get_session_factory
from remy_api.models import Plan, UserSettings
from remy_api.planner import deps, discover
from remy_api.planner.schemas import Meal
from remy_api.prompts import listicle_filter


async def _meals(limit: int) -> list[tuple[Meal, str, list[str]]]:
    factory = get_session_factory()
    async with factory() as session:
        settings = {s.user_id: s for s in (await session.execute(select(UserSettings))).scalars()}
        plans = (await session.execute(select(Plan).order_by(Plan.created_at.desc()))).scalars().all()
    seen: set[str] = set()
    out = []
    for plan in plans:
        for m in plan.meals or []:
            meal = Meal(**m)
            key = (meal.query or meal.verbatim).lower()
            if key in seen or meal.url:
                continue
            seen.add(key)
            favs = list(settings[plan.user_id].favorite_sites or []) if plan.user_id in settings else []
            out.append((meal, plan.user_id, favs))
    return out[:limit]


async def _timed(coro):
    t = time.perf_counter()
    result = await coro
    return result, (time.perf_counter() - t) * 1000


def _with_jev(steps: str):
    get_settings().jev_steps = steps


async def _saved(meal: Meal, user_id: str) -> dict:
    _with_jev("")
    llm, llm_ms = await _timed(discover._discover_saved(meal, user_id))
    _with_jev("saved_recipes")
    jv, jev_ms = await _timed(discover._discover_saved(meal, user_id))
    _with_jev("")
    return {
        "llm": {c.title for c in llm},
        "jev": {c.title for c in jv},
        "llm_ms": llm_ms,
        "jev_ms": jev_ms,
    }


async def _web(meal: Meal, favs: list[str]) -> dict | None:
    pairs = await discover._web_search(meal, favs)
    cands = [listicle_filter.SearchCandidate(title=r.title, url=r.url, snippet=r.snippet) for r, _ in pairs]
    survivors, _ = listicle_filter.prefilter_listicles(cands)
    if not survivors:
        return None
    pool = [cands[i] for i in survivors]
    out, llm_ms = await _timed(
        deps.get_llm_client().structured(
            listicle_filter.render(
                listicle_filter.ListicleFilterInput(query=meal.query or meal.verbatim, candidates=pool)
            ),
            listicle_filter.ListicleFilterOutput,
        )
    )
    llm_keep = {i for i in out.keep_indices if 0 <= i < len(pool)}
    jev_keep, jev_ms = await _timed(discover._single_recipe_pages_jev(meal.query or meal.verbatim, pool))
    return {"pool": pool, "llm": llm_keep, "jev": jev_keep, "llm_ms": llm_ms, "jev_ms": jev_ms}


async def main(limit: int) -> None:
    meals = await _meals(limit)
    print(f"{len(meals)} distinct meals from past plans\n")

    saved_rows, web_rows = [], []
    for meal, user_id, favs in meals:
        q = meal.query or meal.verbatim
        s = await _saved(meal, user_id)
        saved_rows.append(s)
        if s["llm"] != s["jev"]:
            print(f"[saved] {q!r} (specific={meal.is_specific})")
            print(f"   LLM only: {sorted(s['llm'] - s['jev'])}   Jev only: {sorted(s['jev'] - s['llm'])}")
        try:
            w = await _web(meal, favs)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"[web] {q!r}: search failed ({exc})")
            continue
        if w is None:
            continue
        web_rows.append(w)
        for i in sorted(w["llm"] ^ w["jev"]):
            who = "LLM keeps, Jev drops" if i in w["llm"] else "Jev keeps, LLM drops"
            print(f"[web] {q!r}: {who}: {w['pool'][i].title} — {w['pool'][i].url}")

    def agree(rows, per_item):
        if per_item:
            total = sum(len(r["pool"]) for r in rows)
            same = sum(len(r["pool"]) - len(r["llm"] ^ r["jev"]) for r in rows)
        else:
            total, same = len(rows), sum(r["llm"] == r["jev"] for r in rows)
        return f"{same}/{total} ({100 * same / total:.0f}%)" if total else "n/a"

    print("\nSaved-recipe relevance: meals with identical decisions", agree(saved_rows, False))
    print("Listicle filter: per-result agreement", agree(web_rows, True))
    for name, rows in (("saved", saved_rows), ("listicles", web_rows)):
        if rows:
            print(
                f"{name:<10} median latency  LLM {statistics.median(r['llm_ms'] for r in rows):.0f} ms"
                f"   Jev {statistics.median(r['jev_ms'] for r in rows):.0f} ms"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=30)
    asyncio.run(main(parser.parse_args().limit))
