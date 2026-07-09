// Auth store: holds the JWT (persisted to localStorage) and drives the
// login-redirect. The API client reads getToken() to inject the Bearer header
// and calls clearToken() on a 401 (T8 restyles the login screen).
import { create } from 'zustand'

const STORAGE_KEY = 'remy.token'

interface AuthState {
  token: string | null
  setToken: (token: string) => void
  clearToken: () => void
}

export const useAuth = create<AuthState>((set) => ({
  token: localStorage.getItem(STORAGE_KEY),
  setToken: (token) => {
    localStorage.setItem(STORAGE_KEY, token)
    set({ token })
  },
  clearToken: () => {
    localStorage.removeItem(STORAGE_KEY)
    set({ token: null })
  },
}))

// Non-hook accessors for use inside the plain-fetch API client.
export function getToken(): string | null {
  return useAuth.getState().token
}

export function clearToken(): void {
  useAuth.getState().clearToken()
}
