import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'

export function Modal({
  open,
  onClose,
  title,
  children,
  width = 'max-w-lg',
}: {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children: ReactNode
  width?: string
}) {
  const t = useT()
  const titleId = useId()
  const panel = useRef<HTMLDivElement>(null)

  // Focus moves into the dialog (unless a field already took it) and returns to what opened it.
  useEffect(() => {
    if (!open) return
    const opener = document.activeElement as HTMLElement | null
    const el = panel.current
    if (el && !el.contains(document.activeElement)) {
      const first = el.querySelector<HTMLElement>(
        'input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      )
      ;(first ?? el).focus()
    }
    return () => opener?.focus?.()
  }, [open])

  useEffect(() => {
    if (!open) return
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 animate-fade-in bg-black/40" onClick={onClose} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        className={cn(
          'relative z-10 max-h-[90vh] w-full overflow-y-auto rounded-xl focus:outline-none border border-line bg-surface shadow-lg animate-pop-in',
          width,
        )}
      >
        {title && (
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <h2 id={titleId} className="font-serif text-xl text-tx">{title}</h2>
            <button
              onClick={onClose}
              aria-label={t('app.close')}
              className="rounded-md p-1 text-tx-3 hover:bg-surface-2"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        )}
        {children}
      </div>
    </div>,
    document.body,
  )
}
