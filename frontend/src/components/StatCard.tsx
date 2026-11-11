import type { LucideIcon } from 'lucide-react'
import { TrendingDown, TrendingUp } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { useT } from '@/lib/i18n'

export function StatCard({
  icon: Icon,
  label,
  value,
  unit,
  delta,
  deltaSuffix = '%',
  deltaLabel,
  lowerIsBetter = false,
  hint,
}: {
  icon: LucideIcon
  label: string
  value: string
  unit?: string
  /** Change vs. last week; null/undefined hides the trend line (no baseline). */
  delta?: number | null
  deltaSuffix?: string
  /** What the change is measured against (defaults to "vs. last week"). */
  deltaLabel?: string
  /** For rates where going down is good news (no-shows, cancellations). */
  lowerIsBetter?: boolean
  /** Shown on hover over the label. */
  hint?: string
}) {
  const t = useT()
  const good = delta != null && (lowerIsBetter ? delta <= 0 : delta >= 0)
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <span className="eyebrow" title={hint}>
          {label}
        </span>
        <Icon className="h-4 w-4 text-tx-3" />
      </div>
      <p className="mt-2 font-serif text-3xl text-tx">
        {value}
        {unit && <span className="ml-2 font-sans text-sm text-tx-3">{unit}</span>}
      </p>
      {delta != null && (
        <div className="mt-1 flex items-center gap-1 text-[13px]">
          {delta >= 0 ? (
            <TrendingUp className={good ? 'h-3.5 w-3.5 text-ok' : 'h-3.5 w-3.5 text-danger'} />
          ) : (
            <TrendingDown className={good ? 'h-3.5 w-3.5 text-ok' : 'h-3.5 w-3.5 text-danger'} />
          )}
          <span className={good ? 'whitespace-nowrap text-ok' : 'whitespace-nowrap text-danger'}>
            {delta >= 0 ? '+' : ''}
            {delta}
            {deltaSuffix}
          </span>
          <span className="text-tx-4">{deltaLabel ?? t('dash.vs_last_week')}</span>
        </div>
      )}
    </Card>
  )
}
