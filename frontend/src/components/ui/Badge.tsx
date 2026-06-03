import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import type { Tone } from './badgeTone'

const tones: Record<Tone, string> = {
  neutral: 'bg-surface-2 text-tx-2',
  ok: 'text-ok',
  warn: 'text-warn',
  danger: 'text-danger',
  info: 'text-info',
  accent: 'text-accent',
}

const toneBg: Record<Tone, string> = {
  neutral: '',
  ok: 'bg-[var(--ok-10)]',
  warn: 'bg-[var(--warn-10)]',
  danger: 'bg-[var(--danger-10)]',
  info: 'bg-[var(--info-10)]',
  accent: 'bg-[var(--accent-10)]',
}

export function Badge({
  children,
  tone = 'neutral',
  className,
}: {
  children: ReactNode
  tone?: Tone
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-pill px-2.5 py-0.5 text-xs font-medium',
        tones[tone],
        toneBg[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
