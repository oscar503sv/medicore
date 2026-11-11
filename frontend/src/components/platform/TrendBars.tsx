import { useState } from 'react'
import { cn } from '@/lib/cn'
import { fmtDate } from '@/lib/format'

export interface TrendPoint {
  /** ISO date of the period (hour, day or week start): key and axis label. */
  date: string
  count: number
  /** Tooltip and accessible label of the bar. */
  label: string
}

/** One series over time: thin bars anchored to the baseline, a hover tooltip per bar and
 * the latest value labelled directly. The card title names the series (no legend). */
export function TrendBars({
  points,
  barClassName = 'bg-accent',
  axisFormat = 'd MMM',
}: {
  points: TrendPoint[]
  barClassName?: string
  /** date-fns pattern of the first and last axis labels ('HH:mm' for hourly series). */
  axisFormat?: string
}) {
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(1, ...points.map((p) => p.count))
  const last = points.length - 1

  return (
    <div>
      <div className="relative flex h-40 items-end gap-[2px] border-b border-line" role="list">
        {points.map((p, i) => (
          <div
            key={p.date}
            role="listitem"
            aria-label={p.label}
            tabIndex={0}
            className="group relative flex h-full flex-1 items-end justify-center outline-none"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(i)}
            onBlur={() => setHover(null)}
          >
            <div className="flex h-full w-3/5 max-w-6 flex-col items-center justify-end">
              {i === last && hover === null && (
                <span className="mb-1 font-mono text-xs text-tx-2">{p.count}</span>
              )}
              <div
                className={cn('w-full rounded-t transition-opacity', barClassName)}
                style={{
                  height: `${(p.count / max) * 100}%`,
                  minHeight: p.count ? 2 : 0,
                  opacity: hover === null || hover === i ? 1 : 0.45,
                }}
              />
            </div>
            {hover === i && (
              <div className="pointer-events-none absolute bottom-full z-10 mb-2 whitespace-nowrap rounded-md border border-line bg-surface px-2 py-1 text-xs text-tx shadow-sm">
                {p.label}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-tx-4">
        <span>{points.length ? fmtDate(points[0].date, axisFormat) : ''}</span>
        <span>{points.length ? fmtDate(points[last].date, axisFormat) : ''}</span>
      </div>
    </div>
  )
}
