"""Typed shapes for the planner's persisted step data and API contracts (T5).

The ``plans`` table stores each step's data in JSON columns (PRD §6). These
Pydantic models define those shapes so the state machine builds and validates
them consistently, and so ``GET /plan/state`` returns one coherent snapshot for
the web UI (DESIGN_BRIEF §4.2–4.6) and the MCP facade (T6). Internally the
machine round-trips columns through these models (validate → mutate → dump) so a
resumed plan reads back exactly what was written.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field

from remy_api.models import PlanStatus

# --- enums -------------------------------------------------------------------


class Origin(enum.StrEnum):
    SAVED = "saved"
    FAVORITE = "favorite"
    WEB = "web"


class MealStatus(enum.StrEnum):
    PENDING = "pending"
    SEARCHING = "searching"
    READY = "ready"
    DEGRADED = "degraded"  # partial results (a source failed) — labeled, never silent
    ERROR = "error"


class SelectionStatus(enum.StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    SAVED = "saved"
    SKIPPED = "skipped"
    ERROR = "error"


class ListStatus(enum.StrEnum):
    PENDING = "pending"
    BUILDING = "building"
    READY = "ready"
    ERROR = "error"


class MatchStage(enum.StrEnum):
    PENDING = "pending"
    MATCHING = "matching"
    READY = "ready"
    ERROR = "error"


class ItemStatus(enum.StrEnum):
    PENDING = "pending"
    MATCHING = "matching"
    MATCHED = "matched"
    SUBSTITUTED = "substituted"
    STOCK_UNKNOWN = "stock_unknown"
    NOT_FOUND = "not_found"
    FAILED = "failed"
    DROPPED = "dropped"


class ExecStatus(enum.StrEnum):
    PENDING = "pending"
    EXECUTING = "executing"
    DONE = "done"
    PARTIAL = "partial"
    FAILED = "failed"


class ListGroup(enum.StrEnum):
    TO_BUY = "to_buy"
    PANTRY_SKIPPED = "pantry_skipped"
    USER_EXCLUDED = "user_excluded"


# --- discover ----------------------------------------------------------------


class Meal(BaseModel):
    id: str
    query: str
    verbatim: str
    is_specific: bool = True
    url: str | None = None


class Candidate(BaseModel):
    id: str
    title: str
    source_domain: str | None = None
    url: str | None = None
    saved_recipe_id: str | None = None
    thumbnail: str | None = None
    total_time: str | None = None
    origin: Origin = Origin.WEB
    preselected: bool = False


class MealCandidates(BaseModel):
    meal_id: str
    status: MealStatus = MealStatus.PENDING
    candidates: list[Candidate] = Field(default_factory=list)
    source_errors: list[str] = Field(default_factory=list)


# --- select ------------------------------------------------------------------


class SelectionState(BaseModel):
    meal_id: str
    choice: str = "pending"  # "candidate" | "url" | "skip" | "pending"
    candidate_id: str | None = None
    url: str | None = None
    recipe_id: str | None = None
    recipe_title: str | None = None
    status: SelectionStatus = SelectionStatus.PENDING
    error: str | None = None


# --- list --------------------------------------------------------------------


class ContributingRef(BaseModel):
    recipe_id: str
    recipe_title: str
    raw: str
    quantity: float | None = None
    unit: str | None = None


class SegmentModel(BaseModel):
    unit: str | None = None
    quantity: float | None = None
    display: str


class ListLine(BaseModel):
    id: str
    food: str
    display: str
    quantity: float | None = None
    unit: str | None = None
    note: str | None = None
    group: ListGroup = ListGroup.TO_BUY
    included: bool = True
    conflict: bool = False
    segments: list[SegmentModel] = Field(default_factory=list)
    contributing: list[ContributingRef] = Field(default_factory=list)
    free_text: bool = False


class ListState(BaseModel):
    status: ListStatus = ListStatus.PENDING
    lines: list[ListLine] = Field(default_factory=list)
    error: str | None = None


# --- match / cart ------------------------------------------------------------


class ProductRef(BaseModel):
    """A snapshot of a Kroger product for the cart draft (stable across the plan)."""

    upc: str
    description: str | None = None
    brand: str | None = None
    size: str | None = None
    price: float | None = None
    image_url: str | None = None
    stock_level: str = "UNKNOWN"
    department: str | None = None
    pickup: bool = False
    delivery: bool = False


class Alternative(ProductRef):
    alternative_id: str


class MatchItem(BaseModel):
    id: str
    line_id: str
    search_term: str
    target_size: str | None = None
    count: int = 1
    status: ItemStatus = ItemStatus.PENDING
    chosen: ProductRef | None = None
    alternatives: list[Alternative] = Field(default_factory=list)
    error: str | None = None
    confidence: float | None = None


class CartState(BaseModel):
    status: MatchStage = MatchStage.PENDING
    estimated_total: float = 0.0
    items: list[MatchItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


# --- execute -----------------------------------------------------------------


class ExecItem(BaseModel):
    upc: str
    description: str | None = None
    quantity: int = 1
    price: float | None = None
    status: str = "added"  # added | substituted | stock_unknown | failed | unavailable
    reason: str | None = None


class ExecutionState(BaseModel):
    status: ExecStatus = ExecStatus.PENDING
    items: list[ExecItem] = Field(default_factory=list)
    estimated_total: float = 0.0
    order_id: str | None = None
    kroger_cart_url: str = "https://www.kroger.com/cart"
    warnings: list[str] = Field(default_factory=list)


# --- full snapshot (GET /plan/state) -----------------------------------------


class PlanSnapshot(BaseModel):
    plan_id: str
    status: PlanStatus
    created_at: str
    updated_at: str
    needs_input: bool = False
    meals: list[Meal] = Field(default_factory=list)
    candidates: dict[str, MealCandidates] = Field(default_factory=dict)
    selections: dict[str, SelectionState] = Field(default_factory=dict)
    # ``shopping_list`` (not ``list``): a field literally named ``list`` shadows the
    # ``list[...]`` builtin inside this model's own annotation evaluation.
    shopping_list: ListState = Field(default_factory=ListState)
    cart: CartState = Field(default_factory=CartState)
    execution: ExecutionState | None = None


# --- request bodies ----------------------------------------------------------


class PlanCreate(BaseModel):
    text: str = Field(min_length=1)


class MealChoice(BaseModel):
    meal_id: str
    choice: str = Field(description="'candidate' | 'url' | 'skip'")
    candidate_id: str | None = None
    url: str | None = None


class SelectRequest(BaseModel):
    choices: list[MealChoice] = Field(default_factory=list)


class ListEdit(BaseModel):
    op: str = Field(description="'include' | 'exclude' | 'set_quantity' | 'add' | 'delete'")
    line_id: str | None = None
    quantity: float | None = None
    unit: str | None = None
    text: str | None = None  # for 'add'


class ListEditRequest(BaseModel):
    ops: list[ListEdit] = Field(default_factory=list)


class CartEdit(BaseModel):
    op: str = Field(description="'swap' | 'drop' | 'set_count' | 'manual_search'")
    item_id: str
    alternative_id: str | None = None
    count: int | None = None
    term: str | None = None  # for 'manual_search'


class CartEditRequest(BaseModel):
    ops: list[CartEdit] = Field(default_factory=list)


class RetryRequest(BaseModel):
    scope: str = Field(description="'meal' | 'item'")
    id: str = Field(description="meal_id (scope=meal) or match item id (scope=item)")
