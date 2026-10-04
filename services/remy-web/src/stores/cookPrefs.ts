// Per-recipe scale + unit choice for the ingredient list, kept for the session
// so leaving and returning to a recipe keeps the servings you picked.
import { create } from 'zustand'
import type { UnitSystem } from '../lib/ingredients'

export interface CookPref {
  factor: number
  system: UnitSystem | null // null = the recipe's own system
}

interface CookPrefsState {
  prefs: Record<string, CookPref>
  set: (recipeId: string, patch: Partial<CookPref>) => void
}

export const useCookPrefs = create<CookPrefsState>((set) => ({
  prefs: {},
  set: (recipeId, patch) =>
    set((s) => ({
      prefs: {
        ...s.prefs,
        [recipeId]: { ...(s.prefs[recipeId] ?? DEFAULT), ...patch },
      },
    })),
}))

export function useCookPref(recipeId: string | undefined): CookPref {
  return useCookPrefs((s) => (recipeId && s.prefs[recipeId]) || DEFAULT)
}

const DEFAULT: CookPref = { factor: 1, system: null }
