// TanStack Query hooks over the plan API. The plan-state query self-polls
// (~1.5s) only while a long operation is running (discovering/matching/
// executing) and otherwise refetches on window focus — DESIGN_BRIEF §2.5
// (granular progress, never a dead spinner) without hammering the API at rest.
import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import type {
  ApiTokenCreated,
  ApiTokenInfo,
  CartEdit,
  KrogerAuthResponse,
  KrogerStatus,
  ListEdit,
  MealChoice,
  OrderRecord,
  PasswordChange,
  PlanSnapshot,
  RecipeDetail,
  RecipeSummary,
  RetryRequest,
  SettingsResponse,
  SettingsUpdate,
  StoreLocation,
  TokenResponse,
} from './types'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 5_000, refetchOnWindowFocus: true },
  },
})

const POLLING_STATUSES = new Set(['discovering', 'matching', 'executing'])

export const planKey = ['plan', 'state'] as const

export function usePlanState() {
  return useQuery({
    queryKey: planKey,
    queryFn: () => api.get<PlanSnapshot | null>('/plan/state', true),
    refetchInterval: (query) => {
      const data = query.state.data
      if (data && POLLING_STATUSES.has(data.status)) return 1500
      return false
    },
  })
}

export function useKrogerStatus() {
  return useQuery({
    queryKey: ['kroger', 'status'],
    queryFn: () => api.get<KrogerStatus>('/kroger/status'),
  })
}

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get<SettingsResponse>('/users/me/settings'),
  })
}

// --- mutations -------------------------------------------------------------
// Every mutation returns the fresh snapshot; we seed it into the plan-state
// cache so the UI updates immediately without waiting for the next poll.

function usePlanMutation<TArgs = void>(fn: (args: TArgs) => Promise<PlanSnapshot>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (snapshot) => qc.setQueryData(planKey, snapshot),
  })
}

export function useCreatePlan() {
  return usePlanMutation((text: string) => api.post<PlanSnapshot>('/plan', { text }))
}

export function useSubmitSelection() {
  return usePlanMutation((choices: MealChoice[]) =>
    api.post<PlanSnapshot>('/plan/select', { choices }),
  )
}

export function useListEdits() {
  return usePlanMutation((ops: ListEdit[]) => api.post<PlanSnapshot>('/plan/list/edits', { ops }))
}

export function useApproveList() {
  return usePlanMutation(() => api.post<PlanSnapshot>('/plan/list/approve'))
}

export function useCartEdits() {
  return usePlanMutation((ops: CartEdit[]) => api.post<PlanSnapshot>('/plan/cart/edits', { ops }))
}

export function useExecuteCart() {
  return usePlanMutation(() => api.post<PlanSnapshot>('/plan/cart/execute'))
}

export function useRetry() {
  return usePlanMutation((req: RetryRequest) => api.post<PlanSnapshot>('/plan/retry', req))
}

export function useAbandonPlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.del<void>('/plan'),
    onSuccess: () => qc.setQueryData(planKey, null),
  })
}

export function useLogin() {
  return useMutation({
    mutationFn: (creds: { username: string; password: string }) =>
      api.post<TokenResponse>('/auth/login', creds),
  })
}

// --- recipes (cookbook + detail) -------------------------------------------

export function useRecipes(q: string) {
  const query = q.trim()
  return useQuery({
    queryKey: ['recipes', query],
    queryFn: () =>
      api.get<RecipeSummary[]>(`/recipes${query ? `?q=${encodeURIComponent(query)}` : ''}`),
  })
}

export function useRecipe(id: string | undefined) {
  return useQuery({
    queryKey: ['recipe', id],
    queryFn: () => api.get<RecipeDetail>(`/recipes/${id}`),
    enabled: !!id,
  })
}

export function useCreateRecipeFromUrl() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (url: string) => api.post<RecipeDetail>('/recipes/from-url', { url }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recipes'] }),
  })
}

export function useCreateRecipeFromUpload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ files, hint }: { files: File[]; hint: string }) => {
      const form = new FormData()
      for (const file of files) form.append('files', file)
      if (hint.trim()) form.append('hint', hint.trim())
      return api.upload<RecipeDetail>('/recipes/from-upload', form)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recipes'] }),
  })
}

export function useUpdateRecipe(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: import('./types').RecipeUpdate) =>
      api.put<RecipeDetail>(`/recipes/${id}`, body),
    onSuccess: (recipe) => {
      qc.setQueryData(['recipe', id], recipe)
      qc.invalidateQueries({ queryKey: ['recipes'] })
    },
  })
}

export function useDeleteRecipe() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del<void>(`/recipes/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recipes'] }),
  })
}

export function useMarkCooked(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<RecipeDetail>(`/recipes/${id}/cooked`),
    onSuccess: (recipe) => {
      qc.setQueryData(['recipe', id], recipe)
      qc.invalidateQueries({ queryKey: ['recipes'] })
    },
  })
}

// --- orders (cart-as-record) -----------------------------------------------

export function useOrders() {
  return useQuery({
    queryKey: ['orders'],
    queryFn: () => api.get<OrderRecord[]>('/orders'),
  })
}

// --- settings mutations ----------------------------------------------------

export function useUpdateSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SettingsUpdate) => api.put<SettingsResponse>('/users/me/settings', body),
    onSuccess: (settings) => qc.setQueryData(['settings'], settings),
  })
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: PasswordChange) => api.post<void>('/users/me/password', body),
  })
}

// --- kroger connect / store search -----------------------------------------

export function useKrogerAuth() {
  return useMutation({ mutationFn: () => api.get<KrogerAuthResponse>('/kroger/auth') })
}

export function useDisconnectKroger() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.del<void>('/kroger/disconnect'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['kroger', 'status'] }),
  })
}

export function useStoreSearch() {
  return useMutation({
    mutationFn: (zip: string) =>
      api.get<StoreLocation[]>(`/kroger/stores?zip=${encodeURIComponent(zip)}`),
  })
}

export function useSelectStore() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (locationId: string) =>
      api.post<{ store_location_id: string; store_name: string | null; zip_code: string | null }>(
        `/kroger/stores/${locationId}/select`,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })
}

// --- api tokens ------------------------------------------------------------

export function useApiTokens() {
  return useQuery({
    queryKey: ['api-tokens'],
    queryFn: () => api.get<ApiTokenInfo[]>('/users/me/api-tokens'),
  })
}

export function useCreateApiToken() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) =>
      api.post<ApiTokenCreated>('/users/me/api-tokens', { name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-tokens'] }),
  })
}

export function useRevokeApiToken() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del<void>(`/users/me/api-tokens/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-tokens'] }),
  })
}
