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
  // Chosen from purchase memory (a "usual") — the match short-circuit skipped
  // ranking, or it was added from the usuals strip.
  is_usual: boolean
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
  op: 'swap' | 'drop' | 'set_count' | 'manual_search' | 'add_upc'
  item_id?: string | null
  alternative_id?: string | null
  count?: number | null
  term?: string | null
  upc?: string | null // for 'add_upc' (add a remembered usual to the cart)
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
  store_chain: string | null
  zip_code: string | null
  fulfillment_method: FulfillmentMethod
  // Banner-aware Kroger cart handoff URL for the selected store (kroger.com if none).
  cart_url: string
}

export interface SettingsUpdate {
  pantry_items?: string[]
  favorite_sites?: string[]
  store_location_id?: string | null
  store_name?: string | null
  store_chain?: string | null
  zip_code?: string | null
  fulfillment_method?: FulfillmentMethod
}

export interface PasswordChange {
  current_password: string
  new_password: string
}

// --- recipes (T8: cookbook + detail) ---
export interface RecipeSummary {
  id: string
  title: string
  slug: string
  source_url: string | null
  image_url: string | null
  total_time: string | null
  created_at: string
  last_cooked_at: string | null
}

export interface Ingredient {
  id: string
  position: number
  raw: string
  quantity: number | null
  unit: string | null
  food: string | null
  note: string | null
}

export interface RecipeDetail extends RecipeSummary {
  recipe_yield: string | null
  prep_time: string | null
  cook_time: string | null
  instructions: string[]
  ingredients: Ingredient[]
}

export interface RecipeUpdate {
  title?: string
  source_url?: string | null
  recipe_yield?: string | null
  prep_time?: string | null
  cook_time?: string | null
  total_time?: string | null
  instructions?: string[]
  ingredients?: { raw: string }[]
}

// --- orders (T8: cart-as-record) ---
export interface OrderItem {
  upc: string
  description: string | null
  quantity: number
  price: number | null
  status: string
  reason: string | null
}

export interface OrderRecord {
  id: string
  plan_id: string | null
  items: OrderItem[]
  estimated_total: number | null
  created_at: string
}

// --- usuals (purchase memory) ---
export interface Usual {
  upc: string
  description: string | null
  size: string | null
  image_url: string | null
  last_price: number | null
  food_key: string
  source: string // 'order' | 'swap' | 'pinned' | 'import'
  times_ordered: number
  preferred: boolean
}

export interface UsualPin {
  upc: string
  description?: string | null
  size?: string | null
  image_url?: string | null
  price?: number | null
  food_key: string
}

// A Kroger product card (usuals pin-search results).
export interface ProductSearchResult {
  upc: string
  description: string | null
  brand: string | null
  size: string | null
  price: number | null
  image_url: string | null
  stock_level: string
}

// Import review payload (receipt / order-history → matched products).
export interface ImportProductMatch {
  upc: string
  description: string | null
  brand: string | null
  size: string | null
  price: number | null
  image_url: string | null
}

export interface ImportReviewItem {
  extracted_name: string
  food_key: string
  quantity: number | null
  matched: ImportProductMatch | null
  alternatives: ImportProductMatch[]
}

export interface ImportReviewResponse {
  found_items: boolean
  items: ImportReviewItem[]
}

export interface ImportConfirmSelection {
  food_key: string
  upc: string
  description?: string | null
  size?: string | null
  image_url?: string | null
  price?: number | null
}

// --- kroger store search ---
export interface StoreLocation {
  id: string
  name: string | null
  chain: string | null
  address: string | null
  city: string | null
  state: string | null
  zip_code: string | null
  full_address: string | null
  distance: number | null
}

// --- api tokens (T8: settings) ---
export interface ApiTokenInfo {
  id: string
  name: string
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
}

export interface ApiTokenCreated extends ApiTokenInfo {
  token: string
}

export interface KrogerAuthResponse {
  auth_url: string
}

// --- current user + admin (user management) ---
export interface UserProfile {
  id: string
  username: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}

export interface AdminUserInfo {
  id: string
  username: string
  is_admin: boolean
  is_active: boolean
  created_at: string
  kroger_connected: boolean
}

export interface AdminUserCreated {
  id: string
  username: string
  temp_password: string
}

export interface TempPasswordResponse {
  temp_password: string
}
