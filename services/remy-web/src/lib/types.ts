// TypeScript mirror of remy-api's planner/schemas.py PlanSnapshot + related
// request bodies, plus the auth/settings/kroger shapes T7 consumes. Kept in sync
// with services/remy-api/src/remy_api/planner/schemas.py.

export type PlanStatus =
  | 'discovering'
  | 'selecting'
  | 'reviewing_list'
  | 'matching'
  | 'reviewing_cart'
  | 'executing'
  | 'done'
  | 'abandoned'

export type Origin = 'saved' | 'favorite' | 'web'
export type MealStatus = 'pending' | 'searching' | 'ready' | 'degraded' | 'error'
export type SelectionStatus = 'pending' | 'parsing' | 'saved' | 'skipped' | 'error'
export type ListStatus = 'pending' | 'building' | 'ready' | 'error'
export type MatchStage = 'pending' | 'matching' | 'ready' | 'error'
export type ItemStatus =
  | 'pending'
  | 'matching'
  | 'matched'
  | 'substituted'
  | 'stock_unknown'
  | 'not_found'
  | 'failed'
  | 'dropped'
export type ExecStatus = 'pending' | 'executing' | 'done' | 'partial' | 'failed'
export type ListGroup = 'to_buy' | 'pantry_skipped' | 'user_excluded'

export interface Meal {
  id: string
  query: string
  verbatim: string
  is_specific: boolean
  url: string | null
}

export interface Candidate {
  id: string
  title: string
  source_domain: string | null
  url: string | null
  saved_recipe_id: string | null
  thumbnail: string | null
  total_time: string | null
  origin: Origin
  preselected: boolean
}

export interface MealCandidates {
  meal_id: string
  status: MealStatus
  candidates: Candidate[]
  source_errors: string[]
}

export interface SelectionState {
  meal_id: string
  choice: string // "candidate" | "url" | "skip" | "pending"
  candidate_id: string | null
  url: string | null
  recipe_id: string | null
  recipe_title: string | null
  status: SelectionStatus
  error: string | null
}

export interface ContributingRef {
  recipe_id: string
  recipe_title: string
  raw: string
  quantity: number | null
  unit: string | null
}

export interface SegmentModel {
  unit: string | null
  quantity: number | null
  display: string
}

export interface ListLine {
  id: string
  food: string
  display: string
  quantity: number | null
  unit: string | null
  note: string | null
  group: ListGroup
  included: boolean
  conflict: boolean
  segments: SegmentModel[]
  contributing: ContributingRef[]
  free_text: boolean
}

export interface ListState {
  status: ListStatus
  lines: ListLine[]
  error: string | null
}

export interface ProductRef {
  upc: string
  description: string | null
  brand: string | null
  size: string | null
  price: number | null
  image_url: string | null
  stock_level: string // HIGH | LOW | MEDIUM | UNKNOWN | ...
  department: string | null
  pickup: boolean
  delivery: boolean
}

export interface Alternative extends ProductRef {
  alternative_id: string
}

export interface MatchItem {
  id: string
  line_id: string
  search_term: string
  target_size: string | null
  count: number
  status: ItemStatus
  chosen: ProductRef | null
  alternatives: Alternative[]
  error: string | null
  confidence: number | null
}

export interface CartState {
  cart_draft_id: string | null
  status: MatchStage
  estimated_total: number
  items: MatchItem[]
  warnings: string[]
  error: string | null
}

export interface ExecItem {
  upc: string
  description: string | null
  quantity: number
  price: number | null
  status: string // added | substituted | stock_unknown | failed | unavailable
  reason: string | null
}

export interface ExecutionState {
  status: ExecStatus
  items: ExecItem[]
  estimated_total: number
  order_id: string | null
  kroger_cart_url: string
  warnings: string[]
}

export interface PlanSnapshot {
  plan_id: string
  status: PlanStatus
  created_at: string
  updated_at: string
  needs_input: boolean
  meals: Meal[]
  candidates: Record<string, MealCandidates>
  selections: Record<string, SelectionState>
  shopping_list: ListState
  cart: CartState
  execution: ExecutionState | null
}

// --- request bodies ---
export interface MealChoice {
  meal_id: string
  choice: 'candidate' | 'url' | 'skip'
  candidate_id?: string | null
  url?: string | null
}

export interface ListEdit {
  op: 'include' | 'exclude' | 'set_quantity' | 'add' | 'delete'
  line_id?: string | null
  quantity?: number | null
  unit?: string | null
  text?: string | null
}

export interface CartEdit {
  op: 'swap' | 'drop' | 'set_count' | 'manual_search'
  item_id: string
  alternative_id?: string | null
  count?: number | null
  term?: string | null
}

export interface RetryRequest {
  scope: 'meal' | 'item'
  id: string
}

// --- auth / settings / kroger ---
export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface KrogerStatus {
  connected: boolean
  expires_at: string | null
  expired: boolean
}

export type FulfillmentMethod = 'PICKUP' | 'DELIVERY'

export interface SettingsResponse {
  pantry_items: string[]
  favorite_sites: string[]
  store_location_id: string | null
  store_name: string | null
  zip_code: string | null
  fulfillment_method: FulfillmentMethod
}
