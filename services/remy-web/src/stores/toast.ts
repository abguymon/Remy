// Global toast store — one transient message at a time (DESIGN_BRIEF §6).
// Optionally carries a single action (e.g. "Undo") rendered as a button.
import { create } from 'zustand'

export interface ToastAction {
  label: string
  run: () => void
}

interface ToastState {
  message: string | null
  action: ToastAction | null
  show: (message: string, action?: ToastAction | null) => void
  dismiss: () => void
}

let timer: ReturnType<typeof setTimeout> | null = null

export const useToast = create<ToastState>((set) => ({
  message: null,
  action: null,
  show: (message, action = null) => {
    if (timer) clearTimeout(timer)
    set({ message, action })
    // Give actionable toasts a little longer to be tapped.
    timer = setTimeout(() => set({ message: null, action: null }), action ? 5000 : 3200)
  },
  dismiss: () => {
    if (timer) clearTimeout(timer)
    set({ message: null, action: null })
  },
}))

// Non-hook accessor for firing toasts from event handlers / mutation callbacks.
export function toast(message: string, action?: ToastAction | null): void {
  useToast.getState().show(message, action)
}
