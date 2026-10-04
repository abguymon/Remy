// Appearance preference (system / light / dark), persisted per device. The
// resolved theme is applied as `html.dark`; index.html runs the same logic
// inline before first paint so there is no light flash on load.
import { create } from 'zustand'

export type ThemePref = 'system' | 'light' | 'dark'

const KEY = 'remy-theme'
const media = window.matchMedia('(prefers-color-scheme: dark)')

function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch {
    // storage blocked — fall through to system
  }
  return 'system'
}

function apply(pref: ThemePref) {
  const dark = pref === 'dark' || (pref === 'system' && media.matches)
  document.documentElement.classList.toggle('dark', dark)
}

interface ThemeState {
  pref: ThemePref
  setPref: (pref: ThemePref) => void
}

export const useTheme = create<ThemeState>((set) => ({
  pref: readPref(),
  setPref: (pref) => {
    try {
      localStorage.setItem(KEY, pref)
    } catch {
      // not persisted; still applies for this session
    }
    apply(pref)
    set({ pref })
  },
}))

apply(useTheme.getState().pref)
media.addEventListener('change', () => apply(useTheme.getState().pref))
