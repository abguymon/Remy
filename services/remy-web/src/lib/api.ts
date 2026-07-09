// Typed fetch client for remy-api. All calls go through the /api proxy (Vite
// dev + nginx prod strip the prefix). Injects the Bearer token, unwraps the
// {error:{code,message}} envelope into a typed ApiError, and clears auth on 401
// so the app redirects to login.
import { clearToken, getToken } from '../stores/auth'

export class ApiError extends Error {
  code: string
  status: number
  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

interface RequestOptions {
  method?: string
  body?: unknown
  // Some endpoints (GET /plan/state when no plan) legitimately 404 — callers can
  // opt out of the error throw for specific statuses and get null instead.
  allow404?: boolean
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'

  const res = await fetch(`/api${path}`, {
    method: opts.method ?? 'GET',
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  })

  if (res.status === 401) {
    clearToken()
    throw new ApiError(401, 'unauthenticated', 'Your session expired. Please sign in again.')
  }

  if (res.status === 404 && opts.allow404) {
    return null as T
  }

  if (res.status === 204) {
    return undefined as T
  }

  let payload: unknown = null
  const text = await res.text()
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (!res.ok) {
    const envelope = payload as { error?: { code?: string; message?: string } } | null
    const code = envelope?.error?.code ?? 'error'
    const message = envelope?.error?.message ?? `Request failed (${res.status})`
    throw new ApiError(res.status, code, message)
  }

  return payload as T
}

export const api = {
  get: <T>(path: string, allow404 = false) => request<T>(path, { allow404 }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
