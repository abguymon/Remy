// Global toast store — one transient message at a time (DESIGN_BRIEF §6).
import { create } from 'zustand'

interface ToastState {
  message: string | null
  show: (message: string) => void
  dismiss: () => void
}

let timer: ReturnType<typeof setTimeout> | null = null

export const useToast = create<ToastState>((set) => ({
  message: null,
  show: (message) => {
    if (timer) clearTimeout(timer)
    set({ message })
    timer = setTimeout(() => set({ message: null }), 3200)
  },
  dismiss: () => {
    if (timer) clearTimeout(timer)
    set({ message: null })
  },
}))

// Non-hook accessor for firing toasts from event handlers / mutation callbacks.
export function toast(message: string): void {
  useToast.getState().show(message)
}
