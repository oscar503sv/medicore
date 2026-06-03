import { create } from 'zustand'

interface ToastItem {
  id: number
  message: string
  tone: 'ok' | 'danger'
}

interface ToastState {
  toasts: ToastItem[]
  push: (message: string, tone?: 'ok' | 'danger') => void
  remove: (id: number) => void
}

export const useToast = create<ToastState>((set) => ({
  toasts: [],
  push: (message, tone = 'ok') => {
    const id = Date.now() + Math.random()
    set((s) => ({ toasts: [...s.toasts, { id, message, tone }] }))
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 3500)
  },
  remove: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

export function toast(message: string, tone: 'ok' | 'danger' = 'ok') {
  useToast.getState().push(message, tone)
}
