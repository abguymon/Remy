// TanStack Query hooks over the plan API. The plan-state query self-polls
// (~1.5s) only while a long operation is running (discovering/matching/
// executing) and otherwise refetches on window focus — DESIGN_BRIEF §2.5
// (granular progress, never a dead spinner) without hammering the API at rest.
import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import type {
  CartEdit,
  KrogerStatus,
  ListEdit,
  MealChoice,
  PlanSnapshot,
  RetryRequest,
  SettingsResponse,
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
