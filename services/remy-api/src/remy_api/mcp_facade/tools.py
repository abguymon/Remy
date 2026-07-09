"""The MCP tool surface (PRD §7.4).

Coarse-grained tools mirroring the pipeline gates. All deterministic logic
(search + listicle filtering, parsing, consolidation, pantry bypass, product
extraction, ranking, substitution, cart writes) runs *inside* the tools by
calling the very same ``planner``/``recipes``/``kroger`` functions the web app
uses — there is no divergent logic here (PRD §4). The calling agent only
orchestrates between gates and relays the human's choices.

Safety structure — the **draft-id chain**:

* ``find_recipes`` returns a ``plan_draft_id`` (the plan's id). Every plan tool
  requires it and rejects a value that isn't the caller's active plan.
* ``match_products`` returns a distinct ``cart_draft_id``. ``swap_product`` and
  ``execute_cart`` require it; ``execute_cart`` — the only real-cart write —
  accepts *only* the id currently on the plan (a re-match mints a new one), so an
  agent can never fabricate a cart execution.

Async gates (``find_recipes`` discovery, ``match_products`` matching) run as
background steps; these tools **wait internally** for completion (up to ~120s)
and return the finished result in one call, because agents poll poorly. On the
rare timeout they return progress-so-far and tell you to call ``plan_status``.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field
from sqlalchemy import select

from remy_api.config import get_settings as get_app_settings
from remy_api.errors import APIError
from remy_api.kroger import KrogerError, KrogerNotConnectedError, get_location, get_locations
from remy_api.mcp_facade import serialize
from remy_api.mcp_facade.context import load_snapshot, tool_context, wait_for_step
from remy_api.models import FulfillmentMethod, KrogerToken, Plan, PlanStatus, UserSettings
from remy_api.planner import deps, machine
from remy_api.planner.schemas import CartEdit, ListEdit, MealChoice
from remy_api.recipes import store

_WAIT_TIMEOUT = 120.0


# --- tool input models -------------------------------------------------------


class RecipeChoiceInput(BaseModel):
    meal_id: str = Field(description="The meal_id from find_recipes.")
    candidate_id: str | None = Field(default=None, description="Chosen candidate_id for this meal.")
    url: str | None = Field(default=None, description="A recipe URL to use instead of a candidate.")
    skip: bool = Field(default=False, description="Skip this meal entirely.")


class ListEditInput(BaseModel):
    op: str = Field(description="'include' | 'exclude' | 'set_quantity' | 'add' | 'delete'.")
    line_id: str | None = Field(default=None, description="Target line_id (not needed for 'add').")
    quantity: float | None = Field(default=None, description="New quantity for 'set_quantity'.")
    unit: str | None = None
    text: str | None = Field(default=None, description="Free-text line for 'add', e.g. 'a bunch of cilantro'.")


# --- helpers -----------------------------------------------------------------


def _fail(message: str) -> ToolError:
    return ToolError(message)


async def _active_plan(session, user_id: str, plan_draft_id: str | None) -> Plan:  # noqa: ANN001
    plan = await machine.get_active_plan(session, user_id)
    if plan is None:
        raise _fail("No active plan. Start one with find_recipes.")
    if plan_draft_id and plan.id != plan_draft_id:
        raise _fail("plan_draft_id does not match your active plan. Call plan_status to get the current plan_draft_id.")
    return plan


async def _read(user_id: str) -> object:
    """Open a fresh session and return the current plan snapshot (or None)."""
    async with tool_context() as (session, _user):
        return await load_snapshot(session, user_id)


def _kroger_error_message(exc: KrogerError) -> str:
    if isinstance(exc, KrogerNotConnectedError):
        return "Kroger is not connected. Connect your Kroger account in Remy Settings (web app) first, then retry."
    return getattr(exc, "message", str(exc))


# --- server + tools ----------------------------------------------------------


def build_mcp_server() -> FastMCP:
    """Construct the FastMCP server and register every PRD §7.4 tool."""
    settings = get_app_settings()
    # DNS-rebinding protection: enabled only when the operator lists allowed
    # hosts/origins (their deploy domain). Otherwise off — the facade already
    # enforces bearer auth and sits behind the reverse proxy (see config.py).
    strict = bool(settings.mcp_allowed_hosts or settings.mcp_allowed_origins)
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=strict,
        allowed_hosts=list(settings.mcp_allowed_hosts),
        allowed_origins=list(settings.mcp_allowed_origins),
    )
    mcp = FastMCP(
        "remy",
        instructions=(
            "Remy turns a week of meals into a filled Kroger pickup cart. Drive the flow gate by gate: "
            "find_recipes -> select_recipes -> build_shopping_list (edit_shopping_list to adjust) -> "
            "match_products (swap_product to adjust) -> execute_cart. At every gate, present the options to "
            "the human and let THEM choose before proceeding. Always relay substitutions, out-of-stock items, "
            "and failures verbatim — never smooth them over. plan_status resumes an in-flight plan."
        ),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=transport_security,
    )

    # -- flow: discover -------------------------------------------------------

    @mcp.tool(
        description=(
            "Start a meal plan. Input `meals`: a list of free-text meal descriptions and/or recipe URLs "
            "(e.g. ['chicken tikka masala', 'some kind of salmon dish', 'https://site.com/tacos']). Remy "
            "extracts distinct meals and, for each, gathers up to 5 recipe candidates from the user's saved "
            "cookbook (ranked first) and the web (favorite sites badged), dropping listicles/roundups.\n\n"
            "This runs discovery as a background step and WAITS for it to finish (up to ~120s), returning "
            "the complete candidate set plus a `plan_draft_id` you pass to every later tool. Each candidate "
            "has a `candidate_id`, title, source, url, and thumbnail. A meal whose web search failed is marked "
            "`degraded` with `source_errors` — surface that to the user, don't hide it. If it times out you get "
            "partial results; call plan_status to get the rest.\n\n"
            "PRESENT the candidates to the human and let them pick one per meal before calling select_recipes. "
            "Only one active plan per user — if one exists, use plan_status or abandon it first."
        )
    )
    async def find_recipes(meals: list[str]) -> dict:
        if not meals or not any(m and m.strip() for m in meals):
            raise _fail("Provide at least one meal (free text or a recipe URL).")
        text = "\n".join(m.strip() for m in meals if m and m.strip())
        async with tool_context() as (session, user):
            try:
                await machine.create_plan(session, user, text)
            except APIError as exc:
                raise _fail(exc.message) from exc
            user_id = user.id
        await wait_for_step(user_id, _WAIT_TIMEOUT)
        snapshot = await _read(user_id)
        if snapshot is None:
            raise _fail("Plan disappeared unexpectedly. Try find_recipes again.")
        if snapshot.needs_input:
            return {
                "plan_draft_id": snapshot.plan_id,
                "needs_input": True,
                "message": "No meals were recognized in that text. Ask the user what they'd like to cook.",
            }
        return serialize.candidates_view(snapshot)

    # -- flow: select ---------------------------------------------------------

    @mcp.tool(
        description=(
            "Record the user's recipe choices for a plan. `choices` is one entry per meal, each with the "
            "`meal_id` and exactly one of: `candidate_id` (a candidate from find_recipes), `url` (a specific "
            "recipe URL to use instead), or `skip: true`. Remy scrapes/parses the chosen recipes, saves them to "
            "the cookbook, and — once every meal is resolved — consolidates their ingredients into a shopping "
            "list. Returns the per-meal parse status; a meal that failed to parse stays selectable so you can "
            "retry it with a different choice. Relay any parse errors to the user."
        )
    )
    async def select_recipes(plan_draft_id: str, choices: list[RecipeChoiceInput]) -> dict:
        async with tool_context() as (session, user):
            plan = await _active_plan(session, user.id, plan_draft_id)
            if plan.status != PlanStatus.SELECTING:
                raise _fail(
                    f"Plan is in '{plan.status}', not selecting. Selections can only be made right after find_recipes."
                )
            mapped: list[MealChoice] = []
            for c in choices:
                if c.skip:
                    choice = "skip"
                elif c.candidate_id:
                    choice = "candidate"
                elif c.url:
                    choice = "url"
                else:
                    raise _fail(f"Meal {c.meal_id}: provide candidate_id, url, or skip.")
                mapped.append(MealChoice(meal_id=c.meal_id, choice=choice, candidate_id=c.candidate_id, url=c.url))
            try:
                await machine.submit_selection(session, user, mapped)
            except APIError as exc:
                raise _fail(exc.message) from exc
            user_id = user.id
        snapshot = await _read(user_id)
        result = serialize.selections_view(snapshot)
        if snapshot.status == PlanStatus.REVIEWING_LIST:
            result["shopping_list"] = serialize.shopping_list_view(snapshot)
        return result

    # -- flow: shopping list --------------------------------------------------

    @mcp.tool(
        description=(
            "Get the consolidated shopping list for a plan. Ingredients from the selected recipes are parsed, "
            "duplicate foods merged with combined quantities (each line lists which recipes contributed), and "
            "pantry staples separated into `pantry_skipped` (not deleted — re-includable). `to_buy` is what will "
            "be matched to products; `excluded` are lines the user removed. Show all three groups to the user "
            "for review before matching products."
        )
    )
    async def build_shopping_list(plan_draft_id: str) -> dict:
        async with tool_context() as (session, user):
            plan = await _active_plan(session, user.id, plan_draft_id)
            if plan.status in (PlanStatus.DISCOVERING, PlanStatus.SELECTING):
                raise _fail(f"The shopping list isn't ready (plan is '{plan.status}'). Finish select_recipes first.")
            user_id = user.id
        snapshot = await _read(user_id)
        return serialize.shopping_list_view(snapshot)

    @mcp.tool(
        description=(
            "Edit the shopping list before matching. `edits` is a list of operations:\n"
            "- {op:'exclude', line_id} — remove a line from the buy list\n"
            "- {op:'include', line_id} — re-include an excluded or pantry line\n"
            "- {op:'set_quantity', line_id, quantity, unit?} — change amount\n"
            "- {op:'delete', line_id} — delete a line entirely\n"
            "- {op:'add', text} — add a free-text line (e.g. 'a bunch of cilantro')\n"
            "Returns the updated list. Confirm changes with the user before matching products."
        )
    )
    async def edit_shopping_list(plan_draft_id: str, edits: list[ListEditInput]) -> dict:
        async with tool_context() as (session, user):
            plan = await _active_plan(session, user.id, plan_draft_id)
            if plan.status != PlanStatus.REVIEWING_LIST:
                raise _fail(f"The list can only be edited while reviewing it (plan is '{plan.status}').")
            ops = [ListEdit(op=e.op, line_id=e.line_id, quantity=e.quantity, unit=e.unit, text=e.text) for e in edits]
            try:
                await machine.list_edits(session, user, ops)
            except APIError as exc:
                raise _fail(exc.message) from exc
            user_id = user.id
        snapshot = await _read(user_id)
        return serialize.shopping_list_view(snapshot)

    # -- flow: match ----------------------------------------------------------

    @mcp.tool(
        description=(
            "Match every to-buy line to a real Kroger product at the user's preferred store and return a cart "
            "draft with a `cart_draft_id`. For each line Remy picks the best product (avoiding multipacks, "
            "preferring the right form/size) and reports the product name, size, PRICE, stock status, and up to "
            "3 alternatives (each with an `alternative_id` for swap_product). Lines where the top pick was out of "
            "stock are marked `is_substitution: true`; lines with no good match are `not_found`.\n\n"
            "This runs matching as a background step and WAITS for it (up to ~120s), returning the full cart in "
            "one call; on timeout you get progress-so-far — call plan_status for the rest. A `warnings` entry of "
            "'kroger_not_connected' means the user must connect Kroger in Settings before execute_cart will work.\n\n"
            "PRESENT every line, its price, and any substitutions to the user VERBATIM. The `estimated_total` is "
            "an estimate — say so. Let the user swap or drop items (swap_product) before execute_cart."
        )
    )
    async def match_products(plan_draft_id: str) -> dict:
        async with tool_context() as (session, user):
            plan = await _active_plan(session, user.id, plan_draft_id)
            user_id = user.id
            if plan.status == PlanStatus.REVIEWING_CART:
                # Already matched — return the existing draft (idempotent).
                return serialize.cart_view(machine.snapshot(plan))
            if plan.status != PlanStatus.REVIEWING_LIST:
                raise _fail(f"Can't match products from '{plan.status}'. Build/approve the shopping list first.")
            try:
                await machine.approve_list(session, user)
            except APIError as exc:
                # e.g. no_store_selected — actionable message straight through.
                raise _fail(exc.message) from exc
        await wait_for_step(user_id, _WAIT_TIMEOUT)
        snapshot = await _read(user_id)
        return serialize.cart_view(snapshot)

    @mcp.tool(
        description=(
            "Swap or drop one line in the cart draft. Pass the `cart_draft_id` from match_products and the "
            "`line_id` of the cart line. Either set `alternative_id` to swap in one of that line's listed "
            "alternatives, or `drop: true` to remove the line. Returns the updated cart with a refreshed "
            "estimated total. The cart_draft_id is unchanged by edits (only a re-match issues a new one). "
            "Confirm the swap reflects what the user asked for."
        )
    )
    async def swap_product(
        cart_draft_id: str, line_id: str, alternative_id: str | None = None, drop: bool = False
    ) -> dict:
        if not drop and not alternative_id:
            raise _fail("Provide alternative_id to swap, or drop=true to remove the line.")
        async with tool_context() as (session, user):
            plan = await _active_plan(session, user.id, None)
            if plan.status != PlanStatus.REVIEWING_CART:
                raise _fail(f"No cart to edit (plan is '{plan.status}'). Run match_products first.")
            current = (plan.matches or {}).get("cart_draft_id")
            if not current or current != cart_draft_id:
                raise _fail(
                    "Unknown or stale cart_draft_id. Call match_products (or plan_status) to get the current "
                    "cart_draft_id."
                )
            if drop:
                op = CartEdit(op="drop", item_id=line_id)
            else:
                op = CartEdit(op="swap", item_id=line_id, alternative_id=alternative_id)
            try:
                await machine.cart_edits(session, user, [op])
            except APIError as exc:
                raise _fail(exc.message) from exc
            user_id = user.id
        snapshot = await _read(user_id)
        return serialize.cart_view(snapshot)

    # -- flow: execute --------------------------------------------------------

    @mcp.tool(
        description=(
            "Add the confirmed cart draft to the user's REAL Kroger cart (pickup). This is the only tool that "
            "writes the real cart. Pass the `cart_draft_id` from match_products — it must be the current draft "
            "(a re-match invalidates old ids), or the write is rejected. Only do this after the user has "
            "explicitly approved the cart.\n\n"
            "Returns a truthful per-item report: `added`, `substituted`, `stock_unknown`, `unavailable`, or "
            "`failed`, plus a kroger.com/cart link. RELAY every non-added outcome to the user VERBATIM — a "
            "failed or unavailable item must never be presented as success. The Kroger API is add-only and "
            "cannot check out: tell the user to open the link to schedule pickup and pay. If Kroger isn't "
            "connected you'll get a clear error pointing to Settings."
        )
    )
    async def execute_cart(cart_draft_id: str) -> dict:
        async with tool_context() as (session, user):
            plan = await _active_plan(session, user.id, None)
            if plan.status != PlanStatus.REVIEWING_CART:
                raise _fail(f"Nothing to execute (plan is '{plan.status}'). Run match_products first.")
            try:
                executed = await machine.execute_cart(session, user, cart_draft_id=cart_draft_id)
            except KrogerError as exc:
                raise _fail(_kroger_error_message(exc)) from exc
            except APIError as exc:
                raise _fail(exc.message) from exc
            # The plan is now terminal (done), so serialize the returned plan
            # directly — get_active_plan would no longer find it.
            return serialize.execution_view(machine.snapshot(executed))

    # -- resume / inspect -----------------------------------------------------

    @mcp.tool(
        description=(
            "Get the current state of the active plan: its step, meals, candidates, selections, shopping list, "
            "cart draft (with cart_draft_id), and execution report as applicable. Use this to resume a plan "
            "started earlier or in the web UI, to recover a plan_draft_id/cart_draft_id, or to fetch results "
            "after a tool timed out. Returns a `no_active_plan` marker if there is none."
        )
    )
    async def plan_status() -> dict:
        async with tool_context() as (session, user):
            snapshot = await load_snapshot(session, user.id)
        if snapshot is None:
            return {"no_active_plan": True, "message": "No active plan. Start one with find_recipes."}
        return {
            "plan_draft_id": snapshot.plan_id,
            "status": str(snapshot.status),
            "needs_input": snapshot.needs_input,
            "created_at": snapshot.created_at,
            "updated_at": snapshot.updated_at,
            "candidates": serialize.candidates_view(snapshot)["meals"],
            "selections": serialize.selections_view(snapshot)["selections"],
            "shopping_list": serialize.shopping_list_view(snapshot),
            "cart": serialize.cart_view(snapshot),
            "execution": serialize.execution_view(snapshot),
        }

    # -- cookbook -------------------------------------------------------------

    @mcp.tool(
        description=(
            "Search the user's saved recipe cookbook by keyword (title + ingredients). Returns matching recipes "
            "with id, title, source, and image. Use get_recipe for full details."
        )
    )
    async def search_my_recipes(query: str, limit: int = 10) -> dict:
        async with tool_context() as (session, user):
            recipes = await store.search_recipes(session, query, limit, user_id=user.id)
            return {
                "recipes": [
                    {
                        "id": r.id,
                        "title": r.title,
                        "source_url": r.source_url,
                        "total_time": r.total_time,
                        "last_cooked_at": r.last_cooked_at.isoformat() if r.last_cooked_at else None,
                    }
                    for r in recipes
                ]
            }

    @mcp.tool(description="Get one saved recipe by id, with its ingredients and instructions.")
    async def get_recipe(id: str) -> dict:  # noqa: A002 - matches PRD tool signature
        async with tool_context() as (session, user):
            try:
                recipe = await store.get_recipe(session, user.id, id)
            except APIError as exc:
                raise _fail(exc.message) from exc
            return {
                "id": recipe.id,
                "title": recipe.title,
                "source_url": recipe.source_url,
                "recipe_yield": recipe.recipe_yield,
                "total_time": recipe.total_time,
                "ingredients": [ing.raw for ing in recipe.ingredients],
                "instructions": list(recipe.instructions or []),
                "last_cooked_at": recipe.last_cooked_at.isoformat() if recipe.last_cooked_at else None,
            }

    @mcp.tool(
        description=(
            "Save a recipe from a URL into the user's cookbook (scrape/parse + download image). Returns the "
            "saved recipe id and title. Use this for one-off saves outside a plan; recipes chosen during "
            "select_recipes are saved automatically."
        )
    )
    async def save_recipe(url: str) -> dict:
        async with tool_context() as (session, user):
            try:
                parsed = await deps.scrape_recipe(url, llm=deps.get_prompt_id_llm())
                recipe = await deps.create_recipe(session, user.id, parsed)
                if parsed.image_url:
                    stored = await deps.download_recipe_image(recipe.id, parsed.image_url)
                    if stored:
                        recipe.image_path = stored
                        await session.commit()
                        await session.refresh(recipe)
            except APIError as exc:
                raise _fail(exc.message) from exc
            except Exception as exc:  # noqa: BLE001 - surface parse failures clearly, never silently
                raise _fail(f"Could not save that recipe: {exc}") from exc
            return {"id": recipe.id, "title": recipe.title, "source_url": recipe.source_url}

    # -- settings -------------------------------------------------------------

    @mcp.tool(
        description=(
            "Get the user's settings: pantry staples, favorite recipe sites, preferred store, fulfillment "
            "method, and whether Kroger is connected. Kroger must be connected via the web Settings screen "
            "(OAuth needs a browser) before execute_cart can write the real cart."
        )
    )
    async def get_settings() -> dict:
        async with tool_context() as (session, user):
            settings = (
                await session.execute(select(UserSettings).where(UserSettings.user_id == user.id))
            ).scalar_one_or_none()
            token = (
                await session.execute(select(KrogerToken).where(KrogerToken.user_id == user.id))
            ).scalar_one_or_none()
            return {
                "pantry_items": list(settings.pantry_items) if settings else [],
                "favorite_sites": list(settings.favorite_sites) if settings else [],
                "store_location_id": settings.store_location_id if settings else None,
                "store_name": settings.store_name if settings else None,
                "zip_code": settings.zip_code if settings else None,
                "fulfillment_method": (settings.fulfillment_method.value if settings else "PICKUP"),
                "kroger_connected": token is not None,
            }

    @mcp.tool(
        description=(
            "Set the preferred Kroger store. Two-step: call with `zip` to get nearby store choices (each with a "
            "`location_id`, name, and address); present them to the user, then call again with the chosen "
            "`location_id` to save it. Passing both `zip` and `location_id` selects directly."
        )
    )
    async def set_store(zip: str | None = None, location_id: str | None = None) -> dict:  # noqa: A002
        if location_id:
            async with tool_context() as (session, user):
                try:
                    loc = await get_location(location_id)
                except KrogerError as exc:
                    raise _fail(_kroger_error_message(exc)) from exc
                if loc is None:
                    raise _fail("That store location_id was not found. Search again with a zip.")
                settings = (
                    await session.execute(select(UserSettings).where(UserSettings.user_id == user.id))
                ).scalar_one_or_none()
                if settings is None:
                    settings = UserSettings(user_id=user.id, fulfillment_method=FulfillmentMethod.PICKUP)
                    session.add(settings)
                settings.store_location_id = loc.id
                settings.store_name = loc.name
                if loc.zip_code:
                    settings.zip_code = loc.zip_code
                await session.commit()
                return {
                    "selected": True,
                    "store_location_id": loc.id,
                    "store_name": loc.name,
                    "zip_code": settings.zip_code,
                }
        if zip:
            try:
                locations = await get_locations(zip, limit=8)
            except KrogerError as exc:
                raise _fail(_kroger_error_message(exc)) from exc
            return {
                "selected": False,
                "choices": [
                    {
                        "location_id": loc.id,
                        "name": loc.name,
                        "address": loc.address,
                        "zip_code": loc.zip_code,
                    }
                    for loc in locations
                ],
                "message": "Present these to the user, then call set_store again with the chosen location_id.",
            }
        raise _fail("Provide a zip to search for stores, or a location_id to select one.")

    @mcp.tool(
        description=(
            "Edit the pantry-staples list (items auto-skipped from shopping lists). `add` and `remove` are lists "
            "of food names. Returns the updated pantry list. Matching is case-insensitive."
        )
    )
    async def edit_pantry(add: list[str] | None = None, remove: list[str] | None = None) -> dict:
        add = add or []
        remove = remove or []
        if not add and not remove:
            raise _fail("Provide items to add and/or remove.")
        async with tool_context() as (session, user):
            settings = (
                await session.execute(select(UserSettings).where(UserSettings.user_id == user.id))
            ).scalar_one_or_none()
            if settings is None:
                settings = UserSettings(user_id=user.id, pantry_items=[], favorite_sites=[])
                session.add(settings)
            items = list(settings.pantry_items or [])
            existing = {i.lower() for i in items}
            for a in add:
                a = a.strip()
                if a and a.lower() not in existing:
                    items.append(a)
                    existing.add(a.lower())
            remove_lower = {r.strip().lower() for r in remove if r.strip()}
            items = [i for i in items if i.lower() not in remove_lower]
            settings.pantry_items = items
            await session.commit()
            return {"pantry_items": items}

    return mcp
