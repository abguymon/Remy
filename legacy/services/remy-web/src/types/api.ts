// Auth types
export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  invite_code: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// User types
export interface User {
  id: string;
  username: string;
  email: string;
  created_at: string;
}

export interface UserSettings {
  pantry_items: string[];
  recipe_sources: RecipeSource[];
  store_location_id: string | null;
  store_name: string | null;
  zip_code: string | null;
  fulfillment_method: string;
  mealie_api_key: string | null;
  mealie_connected: boolean;
}

export interface RecipeSource {
  name: string;
  url: string;
}

// Recipe types
export interface RecipeOption {
  name: string;
  source: string;
  url?: string;
  image_url?: string;
  slug?: string;
}

export interface PlanState {
  recipe_options?: RecipeOption[];
  pending_cart?: CartItem[];
  approved_cart?: CartItem[];
  messages?: string[];
  status?: string;
}

// Cart types
export interface CartItem {
  product_id: string;
  name: string;
  quantity: number;
  price?: number;
  image_url?: string;
}

export interface CartData {
  items: CartItem[];
  total?: number;
}

// Kroger types
export interface KrogerStatus {
  connected: boolean;
  expires_at?: string;
}

export interface StoreLocation {
  locationId: string;
  name?: string;
  chain?: string;
  address?: {
    addressLine1?: string;
    city?: string;
    state?: string;
    zipCode?: string;
  };
}

// API Error
export interface ApiError {
  detail: string;
  status_code?: number;
}
