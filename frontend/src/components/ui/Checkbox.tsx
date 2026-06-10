import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

type CheckboxProps = InputHTMLAttributes<HTMLInputElement>

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      type="checkbox"
      className={cn(
        'h-4 w-4 cursor-pointer rounded border-line text-accent accent-[var(--accent)]',
        'focus:ring-1 focus:ring-accent disabled:cursor-not-allowed disabled:opacity-40',
        className,
      )}
      {...props}
    />
  ),
)
Checkbox.displayName = 'Checkbox'
