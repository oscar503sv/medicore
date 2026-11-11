import { fmtIncome } from '@/lib/analytics'
import { useT } from '@/lib/i18n'

export interface BreakdownItem {
  key: string
  label: string
  count: number
  income?: string | null
}

/** One measure split by category: a thin horizontal bar per row, sorted by size, the value
 * written beside it (and the income when the user may see it). */
export function BreakdownBars({ items }: { items: BreakdownItem[] }) {
  const t = useT()
  const total = items.reduce((sum, i) => sum + i.count, 0)
  const max = Math.max(1, ...items.map((i) => i.count))
  if (items.length === 0)
    return <p className="px-5 py-8 text-center text-sm text-tx-3">{t('an.no_data')}</p>
  return (
    <ul className="space-y-3 p-5">
      {items.map((i) => (
        <li
          key={i.key}
          title={t('an.share').replace(
            '{pct}',
            String(Math.round((i.count * 100) / Math.max(1, total))),
          )}
        >
          <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
            <span className="truncate text-tx-2">{i.label}</span>
            <span className="shrink-0 font-mono text-tx">
              {i.count}
              {i.income != null && <span className="ml-2 text-tx-3">{fmtIncome(i.income)}</span>}
            </span>
          </div>
          <div className="h-2 rounded-full bg-surface-2">
            <div
              className="h-2 rounded-full bg-accent"
              style={{ width: `${(i.count / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}
