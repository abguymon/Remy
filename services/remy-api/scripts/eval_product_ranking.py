#!/usr/bin/env python3
"""Compare product rankers (P5 LLM vs TypeSafe Jev) on real purchase history.

For every item in completed plans, re-run the store search the planner would
run and ask each ranker for its top pick. Reported:

- how often each ranker's top pick is the product that was actually bought
  (``chosen`` after any swaps) — biased toward the LLM, which made the original
  picks the user didn't change;
- how often the two rankers agree;
- Jev's accuracy at high vs low confidence (is the confidence useful as a
  "check this one" flag?);
- latency per ranker.

Read-only: it searches products with the app token (no user cart access) and
reads plans from the database. Needs the same env as the API (Kroger app
credentials, LLM key, TYPESAFE_API_KEY). Run inside the API image, e.g.

    docker compose run --rm --no-deps remy-api python scripts/eval_product_ranking.py --limit 40
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

from sqlalchemy import select

from remy_api.db import get_session_factory
from remy_api.models import Plan, PlanStatus, UserSettings
from remy_api.planner import deps, matching

HIGH_CONFIDENCE = 0.6


async def _cases(limit: int) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        settings = {s.user_id: s for s in (await session.execute(select(UserSettings))).scalars()}
        plans = (await session.execute(select(Plan).where(Plan.status == PlanStatus.DONE))).scalars().all()
    seen: set[tuple[str, str | None]] = set()
    out: list[dict] = []
    for plan in plans:
        s = settings.get(plan.user_id)
        if not s or not s.store_location_id or not plan.matches:
            continue
        for item in plan.matches.get("items", []):
            chosen = item.get("chosen") or {}
            key = (item["search_term"].lower(), item.get("target_size"))
            if not chosen.get("upc") or key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "term": item["search_term"],
                    "target_size": item.get("target_size"),
                    "count": item.get("count", 1),
                    "bought_upc": chosen["upc"],
                    "bought": chosen.get("description"),
                    "location_id": s.store_location_id,
                    "fulfillment": str(s.fulfillment_method.value if s.fulfillment_method else "PICKUP"),
                }
            )
    return out[:limit]


async def _timed(coro):
    t = time.perf_counter()
    result = await coro
    return result, (time.perf_counter() - t) * 1000


async def _eval_one(case: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        products = await deps.kroger_search_products(
            None, case["term"], case["location_id"], limit=matching._SEARCH_LIMIT, fulfillment=case["fulfillment"]
        )
        row = dict(case, n_results=len(products), in_results=any(p.upc == case["bought_upc"] for p in products))
        if not products:
            return row
        llm, llm_ms = await _timed(
            matching._rank_with_llm(case["term"], case["target_size"], case["count"], products)
        )
        (jev_ranked, jev_conf), jev_ms = await _timed(
            matching._rank_with_jev(case["term"], case["target_size"], case["count"], products)
        )
        row.update(
            llm_top=llm[0].upc if llm else None,
            llm_top_desc=llm[0].description if llm else "(none acceptable)",
            jev_top=jev_ranked[0].upc if jev_ranked else None,
            jev_top_desc=jev_ranked[0].description if jev_ranked else "(none acceptable)",
            jev_confidence=jev_conf,
            llm_ms=llm_ms,
            jev_ms=jev_ms,
        )
        return row


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


async def main(limit: int, out_path: str | None) -> None:
    cases = await _cases(limit)
    sem = asyncio.Semaphore(4)
    rows = await asyncio.gather(*(_eval_one(c, sem) for c in cases), return_exceptions=True)
    rows = [r for r in rows if isinstance(r, dict) and "llm_top" in r]
    scored = [r for r in rows if r["in_results"]]

    print(f"\n{len(cases)} past purchases, {len(rows)} searched, {len(scored)} where the bought product is in results\n")
    llm_hit = sum(r["llm_top"] == r["bought_upc"] for r in scored)
    jev_hit = sum(r["jev_top"] == r["bought_upc"] for r in scored)
    agree = sum(r["llm_top"] == r["jev_top"] for r in rows)
    print(f"Top pick = what was bought   LLM {_pct(llm_hit, len(scored))}   Jev {_pct(jev_hit, len(scored))}")
    print(f"LLM and Jev agree            {_pct(agree, len(rows))}")
    hi = [r for r in scored if (r["jev_confidence"] or 0) >= HIGH_CONFIDENCE]
    lo = [r for r in scored if (r["jev_confidence"] or 0) < HIGH_CONFIDENCE]
    print(
        f"Jev accuracy by confidence   >= {HIGH_CONFIDENCE}: {_pct(sum(r['jev_top'] == r['bought_upc'] for r in hi), len(hi))}"
        f"   < {HIGH_CONFIDENCE}: {_pct(sum(r['jev_top'] == r['bought_upc'] for r in lo), len(lo))}"
    )
    for name in ("llm_ms", "jev_ms"):
        vals = [r[name] for r in rows]
        print(f"{name[:3].upper()} latency            median {statistics.median(vals):.0f} ms, max {max(vals):.0f} ms")

    print("\nDisagreements:")
    for r in rows:
        if r["llm_top"] != r["jev_top"]:
            mark = lambda upc: "✓" if upc == r["bought_upc"] else " "  # noqa: E731
            print(f"  {r['term'][:28]:<28} conf {r['jev_confidence'] or 0:.2f}")
            print(f"     {mark(r['llm_top'])} LLM: {r['llm_top_desc']}")
            print(f"     {mark(r['jev_top'])} Jev: {r['jev_top_desc']}")
            if r["in_results"] and r["bought_upc"] not in (r["llm_top"], r["jev_top"]):
                print(f"       bought: {r['bought']}")
    if out_path:
        with open(out_path, "w") as fh:
            json.dump(rows, fh, indent=1, default=str)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--out", help="Write per-item results as JSON.")
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.out))
