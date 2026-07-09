import axios from 'axios'
import { useAuthStore } from '../store/auth'
import type {
  TokenResponse,
  User,
  UserSettings,
  RecipeOption,
  CartItem,
  PlanState,
  CartData,
  KrogerStatus,
  StoreLocation,
} from '../types/api'

const API_URL = import.meta.env.VITE_API_URL || '/api'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 responses - logout and redirect to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// Auth API
export const authApi = {
  login: async (username: string, password: string): Promise<TokenResponse> => {
    const response = await api.post<TokenResponse>('/auth/login', { username, password })
    return response.data
  },

  register: async (username: string, email: string, password: string, inviteCode: string): Promise<User> => {
    const response = await api.post<User>('/auth/register', {
      username,
      email,
      password,
      invite_code: inviteCode,
    })
    return response.data
  },
}

// User API
export const userApi = {
  getProfile: async (): Promise<User> => {
    const response = await api.get<User>('/users/me')
    return response.data
  },

  getSettings: async (): Promise<UserSettings> => {
    const response = await api.get<UserSettings>('/users/me/settings')
    return response.data
  },

  updateSettings: async (settings: Partial<UserSettings>): Promise<UserSettings> => {
    const response = await api.put<UserSettings>('/users/me/settings', settings)
    return response.data
  },

  connectMealie: async (apiKey: string): Promise<UserSettings> => {
    const response = await api.put<UserSettings>('/users/me/mealie', { api_key: apiKey })
    return response.data
  },
}

// Recipe API
export const recipeApi = {
  search: async (query: string): Promise<RecipeOption[]> => {
    const response = await api.post<RecipeOption[]>('/recipes/search', { query })
    return response.data
  },

  startPlan: async (message: string): Promise<PlanState> => {
    const response = await api.post<PlanState>('/recipes/plan', { message })
    return response.data
  },

  getPlanState: async (): Promise<PlanState> => {
    const response = await api.get<PlanState>('/recipes/plan/state')
    return response.data
  },

  selectRecipes: async (selected: RecipeOption[]): Promise<PlanState> => {
    const response = await api.post<PlanState>('/recipes/plan/select', selected)
    return response.data
  },

  approveCart: async (items: CartItem[]): Promise<PlanState> => {
    const response = await api.post<PlanState>('/recipes/plan/approve', items)
    return response.data
  },

  resetPlan: async (): Promise<void> => {
    await api.delete('/recipes/plan')
  },
}

// Cart API
export const cartApi = {
  getCart: async (): Promise<CartData> => {
    const response = await api.get<CartData>('/cart')
    return response.data
  },

  addItem: async (productId: string, quantity: number = 1): Promise<CartData> => {
    const response = await api.post<CartData>('/cart/add', { product_id: productId, quantity })
    return response.data
  },

  removeItem: async (productId: string): Promise<CartData> => {
    const response = await api.delete<CartData>(`/cart/${productId}`)
    return response.data
  },

  searchProducts: async (query: string): Promise<CartItem[]> => {
    const response = await api.get<CartItem[]>(`/cart/search?q=${encodeURIComponent(query)}`)
    return response.data
  },
}

// Kroger API
export const krogerApi = {
  getStatus: async (): Promise<KrogerStatus> => {
    const response = await api.get<KrogerStatus>('/kroger/status')
    return response.data
  },

  startAuth: async (): Promise<{ auth_url: string }> => {
    const response = await api.get<{ auth_url: string }>('/kroger/auth')
    return response.data
  },

  searchStores: async (zipCode?: string): Promise<{ stores: StoreLocation[] }> => {
    const url = zipCode ? `/kroger/stores?zip_code=${zipCode}` : '/kroger/stores'
    const response = await api.get<{ stores: StoreLocation[] }>(url)
    return response.data
  },

  selectStore: async (locationId: string): Promise<void> => {
    await api.post(`/kroger/stores/${locationId}/select`)
  },

  disconnect: async (): Promise<void> => {
    await api.delete('/kroger/disconnect')
  },
}
