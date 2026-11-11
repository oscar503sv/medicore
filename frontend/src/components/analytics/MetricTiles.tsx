import { CalendarCheck, CircleDollarSign, UserPlus, UserX, XCircle } from 'lucide-react'
import type { AnalyticsTotals } from '@/api/analytics'
import { StatCard } from '@/components/StatCard'
import { fmtIncome, fmtRate, incomeChange, pctChange, ptsChange } from '@/lib/analytics'
import { useT } from '@/lib/i18n'

/** The headline figures of a period against the previous one. Income only with the
 * money permission; rates count "down" as good news. */
export function MetricTiles({
  current,
  previous,
  money,
  compareLabel,
  compact = false,
}: {
  current: AnalyticsTotals
  previous: AnalyticsTotals
  money: boolean
  compareLabel: string
  /** Home page: four tiles, no cancellation rate. */
  compact?: boolean
}) {
  const t = useT()
  const points = ` ${t('dash.points')}`
  const tiles = 3 + (compact ? 0 : 1) + (money ? 1 : 0)
  const cols = { 3: 'lg:grid-cols-3', 4: 'lg:grid-cols-4', 5: 'lg:grid-cols-5' }[tiles]
  return (
    <div className={`grid grid-cols-1 gap-4 sm:grid-cols-2 ${cols}`}>
      <StatCard
        icon={CalendarCheck}
        label={t('an.attended')}
        value={String(current.attended)}
        delta={pctChange(current.attended, previous.attended)}
        deltaLabel={compareLabel}
      />
      <StatCard
        icon={UserPlus}
        label={t('an.new_patients')}
        value={String(current.new_patients)}
        delta={pctChange(current.new_patients, previous.new_patients)}
        deltaLabel={compareLabel}
      />
      <StatCard
        icon={UserX}
        label={t('an.no_show_rate')}
        value={fmtRate(current.no_show_rate)}
        delta={ptsChange(current.no_show_rate, previous.no_show_rate)}
        deltaSuffix={points}
        deltaLabel={compareLabel}
        lowerIsBetter
      />
      {!compact && (
        <StatCard
          icon={XCircle}
          label={t('an.cancellation_rate')}
          value={fmtRate(current.cancellation_rate)}
          delta={ptsChange(current.cancellation_rate, previous.cancellation_rate)}
          deltaSuffix={points}
          deltaLabel={compareLabel}
          lowerIsBetter
        />
      )}
      {money && (
        <StatCard
          icon={CircleDollarSign}
          label={t('an.income')}
          hint={t('an.income_hint')}
          value={fmtIncome(current.income)}
          delta={incomeChange(current, previous)}
          deltaLabel={compareLabel}
        />
      )}
    </div>
  )
}
