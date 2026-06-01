import { create } from 'zustand'
import { CheckCircle2, XCircle } from 'lucide-react'
import { cn } from '@/lib/cn'

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

export function ToastViewport() {
  const toasts = useToast((s) => s.toasts)
  return (
    <div className="fixed bottom-6 right-6 z-[60] flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            'flex items-center gap-2.5 rounded-lg border border-line bg-surface px-4 py-3 text-sm shadow-lg animate-pop-in',
          )}
        >
          {t.tone === 'ok' ? (
            <CheckCircle2 className="h-4 w-4 text-ok" />
          ) : (
            <XCircle className="h-4 w-4 text-danger" />
          )}
          <span className="text-tx">{t.message}</span>
        </div>
      ))}
    </div>
  )
}
