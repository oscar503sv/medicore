import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  suffix?: ReactNode
  error?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, suffix, error, className, ...props }, ref) => {
    const errorId = useId()
    return (
      <label className="block">
        {label && <span className="mb-1.5 block text-[13px] font-medium text-tx-2">{label}</span>}
        <div className="relative flex items-center">
          <input
            ref={ref}
            className={cn(
              'h-10 w-full rounded-lg border border-line bg-bg px-3 text-sm text-tx',
              'placeholder:text-tx-4 transition-colors',
              'focus:border-accent focus:outline-none',
              suffix && 'pr-20',
              error && 'border-danger',
              className,
            )}
            {...props}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : props['aria-describedby']}
          />
          {suffix && (
            <span className="absolute right-3 text-[13px] text-tx-3 font-mono">{suffix}</span>
          )}
        </div>
        {error && (
          <span id={errorId} className="mt-1 block text-xs text-danger">
            {error}
          </span>
        )}
      </label>
    )
  },
)
Input.displayName = 'Input'

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  /** Guidance read with the field (aria-describedby), shown below it. */
  hint?: ReactNode
  /** Announced when it appears (role="alert") and tied to the field. */
  error?: string
  /** Extra content on the hint line that screen readers skip (a character counter). */
  aside?: ReactNode
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, hint, error, aside, className, ...props }, ref) => {
    const hintId = useId()
    const errorId = useId()
    const describedBy =
      [hint ? hintId : null, error ? errorId : null, props['aria-describedby']]
        .filter(Boolean)
        .join(' ') || undefined
    return (
      <div>
        <label className="block">
          {label && (
            <span className="mb-1.5 block text-[13px] font-medium text-tx-2">{label}</span>
          )}
          <textarea
            ref={ref}
            className={cn(
              'w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-tx',
              'placeholder:text-tx-4 transition-colors resize-none',
              'focus:border-accent focus:outline-none',
              error && 'border-danger',
              className,
            )}
            {...props}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
          />
        </label>
        {(hint || aside) && (
          <div className="mt-1 flex items-start justify-between gap-3 text-xs text-tx-3">
            <span id={hintId}>{hint}</span>
            {aside && <span aria-hidden="true">{aside}</span>}
          </div>
        )}
        {error && (
          <span id={errorId} role="alert" className="mt-1 block text-xs text-danger">
            {error}
          </span>
        )}
      </div>
    )
  },
)
Textarea.displayName = 'Textarea'

// The app's own listbox (native <select> popups ignore the theme on some platforms).
export { Select } from './Select'
