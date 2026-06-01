import { cn } from '@/lib/cn'
import { initials as toInitials } from '@/lib/format'

const sizes = {
  sm: 'h-7 w-7 text-[11px]',
  md: 'h-9 w-9 text-xs',
  lg: 'h-14 w-14 text-lg',
}

export function Avatar({
  name,
  size = 'md',
  className,
}: {
  name: string
  size?: keyof typeof sizes
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-pill font-semibold',
        'bg-[var(--accent-10)] text-accent',
        sizes[size],
        className,
      )}
    >
      {toInitials(name)}
    </span>
  )
}
