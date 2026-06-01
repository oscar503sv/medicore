import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">{children}</table>
    </div>
  )
}

export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <th
      className={cn(
        'border-b border-line px-4 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-tx-3',
        className,
      )}
    >
      {children}
    </th>
  )
}

export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={cn('border-b border-line-soft px-4 py-3 text-tx-2', className)}>{children}</td>
}

export function Tr({
  children,
  onClick,
  className,
}: {
  children: ReactNode
  onClick?: () => void
  className?: string
}) {
  return (
    <tr
      onClick={onClick}
      className={cn(onClick && 'cursor-pointer hover:bg-surface-2 transition-colors', className)}
    >
      {children}
    </tr>
  )
}
