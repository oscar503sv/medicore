import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  suffix?: ReactNode
  error?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, suffix, error, className, ...props }, ref) => (
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
        />
        {suffix && (
          <span className="absolute right-3 text-[13px] text-tx-3 font-mono">{suffix}</span>
        )}
      </div>
      {error && <span className="mt-1 block text-xs text-danger">{error}</span>}
    </label>
  ),
)
Input.displayName = 'Input'

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string }
>(({ label, className, ...props }, ref) => (
  <label className="block">
    {label && <span className="mb-1.5 block text-[13px] font-medium text-tx-2">{label}</span>}
    <textarea
      ref={ref}
      className={cn(
        'w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-tx',
        'placeholder:text-tx-4 transition-colors resize-none',
        'focus:border-accent focus:outline-none',
        className,
      )}
      {...props}
    />
  </label>
))
Textarea.displayName = 'Textarea'

export const Select = forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string }
>(({ label, className, children, ...props }, ref) => (
  <label className="block">
    {label && <span className="mb-1.5 block text-[13px] font-medium text-tx-2">{label}</span>}
    <select
      ref={ref}
      className={cn(
        'h-10 w-full rounded-lg border border-line bg-bg px-3 text-sm text-tx',
        'focus:border-accent focus:outline-none',
        className,
      )}
      {...props}
    >
      {children}
    </select>
  </label>
))
Select.displayName = 'Select'
