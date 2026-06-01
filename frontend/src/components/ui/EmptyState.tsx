import type { LucideIcon } from 'lucide-react'
import { Inbox } from 'lucide-react'
import type { ReactNode } from 'react'

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
}: {
  icon?: LucideIcon
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-pill bg-surface-2">
        <Icon className="h-6 w-6 text-tx-3" />
      </div>
      <div>
        <p className="text-sm font-medium text-tx">{title}</p>
        {description && <p className="mt-1 text-[13px] text-tx-3">{description}</p>}
      </div>
      {action}
    </div>
  )
}
