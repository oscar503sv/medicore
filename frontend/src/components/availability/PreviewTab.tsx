import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format, parseISO, startOfWeek } from 'date-fns'
import type { AvailabilityScope } from '@/api/availability'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { cn } from '@/lib/cn'
import { clinicToday } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { DAY_KEYS } from './schedule'

export function PreviewTab({ scope, scopeKey }: { scope: AvailabilityScope; scopeKey: string }) {
  const t = useT()
  const weekStart = useMemo(
    () => format(startOfWeek(parseISO(clinicToday()), { weekStartsOn: 1 }), 'yyyy-MM-dd'),
    [],
  )

  const { data, isLoading } = useQuery({
    queryKey: ['availability', 'preview', scopeKey, weekStart],
    queryFn: () => scope.preview(weekStart),
  })

  if (isLoading) return <PageLoader />
  if (!data) return null

  const dayKeys = Object.keys(data).sort()
  // The fixed horizon gives every day the same time axis; take it from the first day.
  const times = (data[dayKeys[0]] ?? []).map((s) => s.start.slice(11, 16))

  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[13px] text-tx-3">{t('avail.preview_hint')}</p>
        <div className="flex items-center gap-3 text-[11px] text-tx-3">
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm bg-[var(--accent-10)]" />
            {t('avail.available')}
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm bg-surface-2" />
            {t('avail.unavailable')}
          </span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-center">
          <thead>
            <tr>
              <th className="w-14" />
              {dayKeys.map((d, i) => (
                <th key={d} className="px-1 py-1 text-[11px] font-medium text-tx-3">
                  {t(DAY_KEYS[i])}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {times.map((time, ti) => (
              <tr key={time}>
                <td className="pr-2 text-right font-mono text-[10px] text-tx-4">{time}</td>
                {dayKeys.map((d) => {
                  const slot = data[d]?.[ti]
                  const available = slot && slot.status !== 'out_of_hours'
                  return (
                    <td key={d} className="px-0.5 py-0.5">
                      <div
                        className={cn(
                          'h-4 rounded-sm',
                          available ? 'bg-[var(--accent-10)]' : 'bg-surface-2',
                        )}
                        title={slot ? `${time} · ${slot.status}` : time}
                      />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
