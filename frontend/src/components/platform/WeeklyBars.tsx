import { useState } from 'react'
import { fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'

/** One series per week: thin accent bars anchored to the baseline, a hover tooltip per bar
 * and the latest week labelled directly. The title outside names the series (no legend). */
export function WeeklyBars({ weeks }: { weeks: { week: string; count: number }[] }) {
  const t = useT()
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(1, ...weeks.map((w) => w.count))
  const last = weeks.length - 1
  const label = (i: number) =>
    `${t('biz.week_of').replace('{date}', fmtDate(weeks[i].week, 'd MMM'))} · ${t(
      'biz.records',
    ).replace('{n}', String(weeks[i].count))}`

  return (
    <div>
      <div className="relative flex h-40 items-end gap-[2px] border-b border-line" role="list">
        {weeks.map((w, i) => (
          <div
            key={w.week}
            role="listitem"
            aria-label={label(i)}
            tabIndex={0}
            className="group relative flex h-full flex-1 items-end justify-center outline-none"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(i)}
            onBlur={() => setHover(null)}
          >
            <div className="flex h-full w-3/5 max-w-6 flex-col items-center justify-end">
              {i === last && hover === null && (
                <span className="mb-1 font-mono text-xs text-tx-2">{w.count}</span>
              )}
              <div
                className="w-full rounded-t bg-accent transition-opacity"
                style={{
                  height: `${(w.count / max) * 100}%`,
                  minHeight: w.count ? 2 : 0,
                  opacity: hover === null || hover === i ? 1 : 0.45,
                }}
              />
            </div>
            {hover === i && (
              <div className="pointer-events-none absolute bottom-full z-10 mb-2 whitespace-nowrap rounded-md border border-line bg-surface px-2 py-1 text-xs text-tx shadow-sm">
                {label(i)}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-tx-4">
        <span>{weeks.length ? fmtDate(weeks[0].week, 'd MMM') : ''}</span>
        <span>{weeks.length ? fmtDate(weeks[last].week, 'd MMM') : ''}</span>
      </div>
    </div>
  )
}
