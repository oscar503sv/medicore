import type { LucideIcon } from 'lucide-react'
import { TrendingDown, TrendingUp } from 'lucide-react'
import { Card } from '@/components/ui/Card'

export function StatCard({
  icon: Icon,
  label,
  value,
  delta,
}: {
  icon: LucideIcon
  label: string
  value: string
  delta?: number
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <span className="eyebrow">{label}</span>
        <Icon className="h-4 w-4 text-tx-3" />
      </div>
      <p className="mt-2 font-serif text-3xl text-tx">{value}</p>
      {delta !== undefined && (
        <div className="mt-1 flex items-center gap-1 text-[13px]">
          {delta >= 0 ? (
            <TrendingUp className="h-3.5 w-3.5 text-ok" />
          ) : (
            <TrendingDown className="h-3.5 w-3.5 text-danger" />
          )}
          <span className={delta >= 0 ? 'text-ok' : 'text-danger'}>
            {delta >= 0 ? '+' : ''}
            {delta}%
          </span>
          <span className="text-tx-4">vs semana anterior</span>
        </div>
      )}
    </Card>
  )
}
