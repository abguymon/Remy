import axios from 'axios'
import { useAuthStore } from '../store/auth'

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

// Handle 401 responses
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
  login: async (username: string, password: string) => {
    const formData = new URLSearchParams()
    formData.append('username', username)
    formData.append('password', password)

    const response = await api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    return response.data
  },

  register: async (username: string, email: string, password: string, inviteCode: string) => {
    const response = await api.post('/auth/register', {
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
  getProfile: async () => {
    const response = await api.get('/users/me')
    return response.data
  },

  getSettings: async () => {
    const response = await api.get('/users/me/settings')
    return response.data
  },

  updateSettings: async (settings: Record<string, unknown>) => {
    const response = await api.put('/users/me/settings', settings)
    return response.data
  },

  connectMealie: async (apiKey: string) => {
    const response = await api.put('/users/me/mealie', { api_key: apiKey })
    return response.data
  },
}

// Recipe API
export const recipeApi = {
  search: async (query: string) => {
    const response = await api.post('/recipes/search', { query })
    return response.data
  },

  startPlan: async (message: string) => {
    const response = await api.post('/recipes/plan', { message })
    return response.data
  },

  getPlanState: async () => {
    const response = await api.get('/recipes/plan/state')
    return response.data
  },

  selectRecipes: async (selected: unknown[]) => {
    const response = await api.post('/recipes/plan/select', selected)
    return response.data
  },

  approveCart: async (items: unknown[]) => {
    const response = await api.post('/recipes/plan/approve', items)
    return response.data
  },

  resetPlan: async () => {
    const response = await api.delete('/recipes/plan')
    return response.data
  },
}

// Cart API
export const cartApi = {
  getCart: async () => {
    const response = await api.get('/cart')
    return response.data
  },

  addItem: async (productId: string, quantity: number = 1) => {
    const response = await api.post('/cart/add', { product_id: productId, quantity })
    return response.data
  },

  removeItem: async (productId: string) => {
    const response = await api.delete(`/cart/${productId}`)
    return response.data
  },

  searchProducts: async (query: string) => {
    const response = await api.get(`/cart/search?q=${encodeURIComponent(query)}`)
    return response.data
  },
}

// Kroger API
export const krogerApi = {
  getStatus: async () => {
    const response = await api.get('/kroger/status')
    return response.data
  },

  startAuth: async () => {
    const response = await api.get('/kroger/auth')
    return response.data
  },

  searchStores: async (zipCode?: string) => {
    const url = zipCode ? `/kroger/stores?zip_code=${zipCode}` : '/kroger/stores'
    const response = await api.get(url)
    return response.data
  },

  selectStore: async (locationId: string) => {
    const response = await api.post(`/kroger/stores/${locationId}/select`)
    return response.data
  },

  disconnect: async () => {
    const response = await api.delete('/kroger/disconnect')
    return response.data
  },
}
