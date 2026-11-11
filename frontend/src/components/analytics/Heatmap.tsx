import { useState } from 'react'
import { useT } from '@/lib/i18n'

type Cell = { weekday: number; hour: number; count: number }

// Sequential ramp: one hue (the accent), light to dark, five steps; empty cells recede.
const STEPS = [0.18, 0.36, 0.56, 0.78, 1]

/** Booked appointments per weekday × hour. Rows are days, columns the hours with any
 * activity; a hover tooltip names the cell and its count. */
export function Heatmap({ cells }: { cells: Cell[] }) {
  const t = useT()
  const [hover, setHover] = useState<Cell | null>(null)
  if (cells.length === 0) {
    return <p className="px-5 py-8 text-center text-sm text-tx-3">{t('an.no_data')}</p>
  }
  const byKey = new Map(cells.map((c) => [`${c.weekday}-${c.hour}`, c.count]))
  const first = Math.min(...cells.map((c) => c.hour))
  const last = Math.max(...cells.map((c) => c.hour))
  const hours = Array.from({ length: last - first + 1 }, (_, i) => first + i)
  const days = [0, 1, 2, 3, 4, 5, 6].filter((d) => cells.some((c) => c.weekday === d))
  const max = Math.max(...cells.map((c) => c.count))
  const step = (n: number) =>
    STEPS[Math.min(STEPS.length - 1, Math.floor(((n - 1) / max) * STEPS.length))]
  const label = (c: Cell) =>
    t('an.heatmap_cell')
      .replace('{day}', t(`an.weekday.${c.weekday}`))
      .replace('{hour}', String(c.hour))
      .replace('{n}', String(c.count))

  return (
    <div className="p-5">
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-[2px] text-[11px] text-tx-3">
          <thead>
            <tr>
              <th />
              {hours.map((h) => (
                <th key={h} className="w-8 text-center font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d}>
                <th className="pr-2 text-left font-normal">{t(`an.weekday.${d}`)}</th>
                {hours.map((h) => {
                  const count = byKey.get(`${d}-${h}`) ?? 0
                  const cell = { weekday: d, hour: h, count }
                  return (
                    <td
                      key={h}
                      tabIndex={count ? 0 : -1}
                      aria-label={label(cell)}
                      onMouseEnter={() => setHover(cell)}
                      onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover(cell)}
                      onBlur={() => setHover(null)}
                      className="h-7 w-8 rounded bg-surface-2 p-0 outline-none focus:ring-1 focus:ring-accent"
                    >
                      {count > 0 && (
                        <div
                          className="h-full w-full rounded bg-accent"
                          style={{ opacity: step(count) }}
                        />
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 text-[11px] text-tx-3">
        <span className="min-h-4 text-tx-2">{hover ? label(hover) : ''}</span>
        <span className="flex items-center gap-1">
          {t('an.heatmap_less')}
          {STEPS.map((o) => (
            <span
              key={o}
              className="inline-block h-3 w-3 rounded-sm bg-accent"
              style={{ opacity: o }}
            />
          ))}
          {t('an.heatmap_more')}
        </span>
      </div>
    </div>
  )
}
