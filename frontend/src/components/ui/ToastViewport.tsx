import { CheckCircle2, XCircle } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useToast } from './Toast'

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
