#!/usr/bin/env python3
"""Manual, interactive live test for the Kroger integration (T2 human gate).

This script talks to the REAL Kroger Public API and writes to a REAL cart. It is
meant to be run by a human with real credentials — it is the "Done when" check
for V2_PLAN.md T2:

    connect OAuth → find the Fred Meyer by ZIP → search "black beans" there →
    add one can to the real cart → print truthful results.

------------------------------------------------------------------------------
PREREQUISITES
------------------------------------------------------------------------------
1. A configured `.env` at the repo root (see `.env.template`) with real:
       JWT_SECRET, ENCRYPTION_KEY, KROGER_CLIENT_ID, KROGER_CLIENT_SECRET,
       KROGER_REDIRECT_URI
   The redirect URI registered in the Kroger developer console MUST exactly
   match KROGER_REDIRECT_URI (default http://localhost:8080/kroger/callback).

2. The API running so the OAuth callback can be received. In one terminal:
       cd services/remy-api
       uv run uvicorn remy_api.main:app --host 0.0.0.0 --port 8080
   (or `docker compose up`). You also need a user + a logged-in session:
       uv run python -m remy_api create-user --username you

------------------------------------------------------------------------------
HOW TO RUN
------------------------------------------------------------------------------
   cd services/remy-api
   uv run python scripts/kroger_live_test.py

The script drives everything through the same internal Kroger module the API
uses (it does NOT go through HTTP), so it needs the same env. It will:

  Step 1  Build the authorize URL and print it. Open it in a browser, log in to
          Kroger, and approve. Your browser is redirected to
          KROGER_REDIRECT_URI?code=...&state=...  — if the API is running, the
          callback stores the token automatically and redirects you to
          /settings?kroger=connected. Otherwise, copy the FULL redirect URL from
          the address bar and paste it here; this script will exchange the code.
  Step 2  Prompt for a ZIP, find the nearest Fred Meyer, and pick it.
  Step 3  Search "black beans" at that store; print the top matches.
  Step 4  Ask for confirmation, then add ONE can to your real Kroger cart.
  Step 5  Print the truthful per-item outcome and the kroger.com/cart link.

Nothing is added without an explicit "yes" at Step 4.
"""

from __future__ import annotations

import asyncio
import sys
from urllib.parse import parse_qs, urlparse

# Ensure `src/` is importable when run directly from the service directory.
sys.path.insert(0, "src")

from remy_api.db import dispose_engine, get_session_factory, init_db  # noqa: E402
from remy_api.kroger import (  # noqa: E402
    KrogerError,
    add_items_to_cart,
    close_client,
    generate_pkce,
    generate_state,
    get_client,
    get_locations,
    search_products,
    store_tokens,
)
from remy_api.kroger.client import DEFAULT_SCOPES  # noqa: E402
from remy_api.user_service import create_user  # noqa: E402


def _hr(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


async def _get_or_create_user(session, username: str) -> str:
    from sqlalchemy import select

    from remy_api.models import User

    row = await session.execute(select(User).where(User.username == username))
    user = row.scalar_one_or_none()
    if user is None:
        user = await create_user(session, username, "live-test-" + generate_state()[:12])
        print(f"Created throwaway user '{username}' (id={user.id}).")
    return user.id


async def main() -> int:
    await init_db()
    factory = get_session_factory()
    client = get_client()

    try:
        username = input("Local username to attach the Kroger token to [livetest]: ").strip() or "livetest"
        async with factory() as session:
            user_id = await _get_or_create_user(session, username)

        # --- Step 1: OAuth connect -------------------------------------------
        _hr("STEP 1 — Connect Kroger (OAuth2 + PKCE)")
        verifier, challenge = generate_pkce()
        state = generate_state()
        auth_url = client.build_authorize_url(state=state, code_challenge=challenge, scope=DEFAULT_SCOPES)
        print("\nOpen this URL in your browser, log in, and approve:\n")
        print(auth_url)
        print(
            "\nAfter approving you are redirected to your KROGER_REDIRECT_URI.\n"
            "Paste the FULL redirect URL here (or just the ?code=... value).\n"
        )
        redirect = input("Redirect URL (or code): ").strip()
        code = _extract_code(redirect, expected_state=state)
        if not code:
            print("No authorization code found. Aborting.")
            return 1

        bundle = await client.exchange_code(code, verifier)
        async with factory() as session:
            await store_tokens(session, user_id, bundle)
        print("Token exchanged and stored (encrypted at rest). Connected.")

        # --- Step 2: Find Fred Meyer by ZIP ----------------------------------
        _hr("STEP 2 — Find your Fred Meyer")
        zip_code = input("ZIP code to search near: ").strip()
        stores = await get_locations(zip_code, limit=10, chain="Fred Meyer")
        if not stores:
            print(f"No Fred Meyer near {zip_code}; retrying without chain filter...")
            stores = await get_locations(zip_code, limit=10)
        if not stores:
            print("No stores found. Aborting.")
            return 1
        for i, s in enumerate(stores):
            print(f"  [{i}] {s.name}  —  {s.full_address}  (id={s.id})")
        choice = input(f"Pick a store [0-{len(stores) - 1}] (default 0): ").strip() or "0"
        store = stores[int(choice)]
        print(f"Using: {store.name} ({store.id})")

        # --- Step 3: Search black beans --------------------------------------
        _hr("STEP 3 — Search 'black beans' at that store")
        products = await search_products(None, "black beans", store.id, limit=10, fulfillment="pickup")
        if not products:
            print("No products found. Aborting.")
            return 1
        for i, p in enumerate(products):
            price = p.price.regular if p.price else None
            price_str = f"${price:.2f}" if price is not None else "n/a"
            print(
                f"  [{i}] {p.description}  |  {p.size or '?'}  |  {price_str}  |  "
                f"stock={p.stock_level}  pickup={p.pickup}  upc={p.upc}"
            )
        pick = input(f"Pick a product to add [0-{len(products) - 1}] (default 0): ").strip() or "0"
        product = products[int(pick)]

        # --- Step 4: Add one can to the REAL cart ----------------------------
        _hr("STEP 4 — Add ONE can to your REAL Kroger cart")
        print(f"About to add: {product.description} ({product.size}) x1 [PICKUP] upc={product.upc}")
        confirm = input("Type 'yes' to write to your real Kroger cart: ").strip().lower()
        if confirm != "yes":
            print("Not confirmed. No cart write performed.")
            return 0

        async with factory() as session:
            outcomes = await add_items_to_cart(
                session, user_id, [{"upc": product.upc, "quantity": 1, "modality": "PICKUP"}]
            )

        # --- Step 5: Truthful report -----------------------------------------
        _hr("STEP 5 — Result")
        for o in outcomes:
            line = f"  {o.upc}  x{o.quantity}  {o.modality}  ->  {o.status.upper()}"
            if o.reason:
                line += f"  ({o.reason})"
            print(line)
        print("\nOpen https://www.kroger.com/cart to verify and check out.")
        return 0

    except KrogerError as exc:
        print(f"\nKroger error: {type(exc).__name__}: {exc.message}")
        return 1
    finally:
        await close_client()
        await dispose_engine()


def _extract_code(value: str, *, expected_state: str) -> str | None:
    """Pull the ``code`` out of a full redirect URL or accept a bare code."""
    if "code=" in value or value.startswith("http"):
        parsed = urlparse(value)
        params = parse_qs(parsed.query)
        returned_state = (params.get("state") or [None])[0]
        if returned_state and returned_state != expected_state:
            print(f"WARNING: state mismatch (expected {expected_state}, got {returned_state}).")
        return (params.get("code") or [None])[0]
    return value or None


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
