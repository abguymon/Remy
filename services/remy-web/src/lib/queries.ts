// TanStack Query hooks over the plan API. The plan-state query self-polls
// (~1.5s) only while a long operation is running (discovering/matching/
// executing) and otherwise refetches on window focus — DESIGN_BRIEF §2.5
// (granular progress, never a dead spinner) without hammering the API at rest.
import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import type {
  AdminUserCreated,
  AdminUserInfo,
  InvitationCreated,
  InvitationInfo,
  ApiTokenCreated,
  ApiTokenInfo,
  CartEdit,
  ImportConfirmSelection,
  ImportReviewResponse,
  KrogerAuthResponse,
  KrogerStatus,
  ListEdit,
  MealChoice,
  OrderRecord,
  PasswordChange,
  PlanSnapshot,
  ProductSearchResult,
  RecipeDetail,
  RecipeSummary,
  RetryRequest,
  SettingsResponse,
  SettingsUpdate,
  StoreLocation,
  TempPasswordResponse,
  TokenResponse,
  Usual,
  UsualPin,
  UserProfile,
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

export function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: () => api.get<UserProfile>('/users/me'),
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

// --- usuals (purchase memory) ----------------------------------------------

export const usualsKey = ['usuals'] as const

export function useUsuals(limit = 12) {
  return useQuery({
    queryKey: [...usualsKey, limit],
    queryFn: () => api.get<Usual[]>(`/users/me/usuals?limit=${limit}`),
  })
}

export function usePinUsual() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: UsualPin) => api.post<Usual>('/users/me/usuals', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: usualsKey }),
  })
}

export function useRemoveUsual() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (upc: string) => api.del<void>(`/users/me/usuals/${encodeURIComponent(upc)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: usualsKey }),
  })
}

export function useHideUsual() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (upc: string) => api.post<void>(`/users/me/usuals/${encodeURIComponent(upc)}/hide`),
    onSuccess: () => qc.invalidateQueries({ queryKey: usualsKey }),
  })
}

export function useUnhideUsual() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (upc: string) => api.post<void>(`/users/me/usuals/${encodeURIComponent(upc)}/unhide`),
    onSuccess: () => qc.invalidateQueries({ queryKey: usualsKey }),
  })
}

// Product search at the user's store (for pinning a usual).
export function useProductSearch() {
  return useMutation({
    mutationFn: (term: string) =>
      api.get<ProductSearchResult[]>(`/kroger/products?term=${encodeURIComponent(term)}`),
  })
}

// Receipt / order-history import: extract → review (nothing saved yet).
export function useImportUsuals() {
  return useMutation({
    mutationFn: ({ files, text }: { files?: File[]; text?: string }) => {
      const form = new FormData()
      for (const file of files ?? []) form.append('files', file)
      if (text && text.trim()) form.append('text', text.trim())
      return api.upload<ImportReviewResponse>('/users/me/usuals/import', form)
    },
  })
}

export function useConfirmImport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (selections: ImportConfirmSelection[]) =>
      api.post<{ seeded: number }>('/users/me/usuals/import/confirm', { selections }),
    onSuccess: () => qc.invalidateQueries({ queryKey: usualsKey }),
  })
}

// --- admin: user management (admin-only) -----------------------------------

const adminUsersKey = ['admin', 'users'] as const

export function useAdminUsers(enabled: boolean) {
  return useQuery({
    queryKey: adminUsersKey,
    queryFn: () => api.get<AdminUserInfo[]>('/admin/users'),
    enabled,
  })
}

export function useCreateAdminUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (username: string) => api.post<AdminUserCreated>('/admin/users', { username }),
    onSuccess: () => qc.invalidateQueries({ queryKey: adminUsersKey }),
  })
}

export function useResetUserPassword() {
  return useMutation({
    mutationFn: (id: string) => api.post<TempPasswordResponse>(`/admin/users/${id}/reset-password`),
  })
}

export function useSetUserActive() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      api.post<AdminUserInfo>(`/admin/users/${id}/${active ? 'activate' : 'deactivate'}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: adminUsersKey }),
  })
}

// --- admin: invitations -----------------------------------------------------

const invitationsKey = ["admin", "invitations"] as const

export function useInvitations(enabled: boolean) {
  return useQuery({
    queryKey: invitationsKey,
    queryFn: () => api.get<InvitationInfo[]>("/admin/invitations"),
    enabled,
  })
}

export function useCreateInvitation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { recipient_label?: string; expires_in_days?: number }) =>
      api.post<InvitationCreated>("/admin/invitations", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: invitationsKey }),
  })
}

export function useRevokeInvitation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<void>("/admin/invitations/" + id + "/revoke"),
    onSuccess: () => qc.invalidateQueries({ queryKey: invitationsKey }),
  })
}

export function useRegisterWithInvitation() {
  return useMutation({
    mutationFn: (body: { username: string; password: string; invitation_token: string }) =>
      api.post<UserProfile>("/auth/register", body),
  })
}
