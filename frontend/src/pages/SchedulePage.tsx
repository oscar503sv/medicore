import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { addDays, format, parseISO, startOfWeek } from 'date-fns'
import { es } from 'date-fns/locale'
import { appointmentsApi } from '@/api/appointments'
import { PageHeader } from '@/components/PageHeader'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { cn } from '@/lib/cn'
import { useT } from '@/lib/i18n'

const HOURS = Array.from({ length: 11 }, (_, i) => i + 8) // 08:00–18:00
const TYPE_COLORS: Record<string, string> = {
  consult: 'bg-[var(--accent-10)] text-accent border-accent',
  procedure: 'bg-[var(--warn-10)] text-warn border-warn',
  follow_up: 'bg-[var(--info-10)] text-info border-info',
  check_up: 'bg-[var(--ok-10)] text-ok border-ok',
}

export function SchedulePage() {
  const t = useT()
  const [weekStart, setWeekStart] = useState(() =>
    startOfWeek(new Date(), { weekStartsOn: 1 }),
  )
  const weekStartStr = format(weekStart, 'yyyy-MM-dd')

  const { data: schedule, isLoading } = useQuery({
    queryKey: ['schedule', weekStartStr],
    queryFn: () => appointmentsApi.weeklySchedule(weekStartStr),
  })

  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        title={t('appt.week_view')}
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setWeekStart(addDays(weekStart, -7))}
              className="rounded-md p-2 text-tx-2 hover:bg-surface-2"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm text-tx-2">
              {format(weekStart, 'd MMM', { locale: es })} –{' '}
              {format(addDays(weekStart, 6), 'd MMM', { locale: es })}
            </span>
            <button
              onClick={() => setWeekStart(addDays(weekStart, 7))}
              className="rounded-md p-2 text-tx-2 hover:bg-surface-2"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        }
      />

      {isLoading ? (
        <PageLoader />
      ) : (
        <Card className="overflow-hidden">
          <div className="grid grid-cols-[56px_repeat(7,1fr)] border-b border-line">
            <div />
            {days.map((d) => (
              <div key={d.toISOString()} className="border-l border-line px-2 py-2 text-center">
                <p className="text-[11px] uppercase text-tx-3">{format(d, 'EEE', { locale: es })}</p>
                <p className="text-sm font-medium text-tx">{format(d, 'd')}</p>
              </div>
            ))}
          </div>
          <div className="relative grid grid-cols-[56px_repeat(7,1fr)]">
            {/* Hour labels */}
            <div>
              {HOURS.map((h) => (
                <div key={h} className="h-16 border-b border-line-soft pr-2 pt-1 text-right">
                  <span className="font-mono text-[11px] text-tx-4">{String(h).padStart(2, '0')}:00</span>
                </div>
              ))}
            </div>
            {/* Day columns */}
            {days.map((d) => {
              const dayKey = format(d, 'yyyy-MM-dd')
              const appts = schedule?.[dayKey] ?? []
              return (
                <div key={dayKey} className="relative border-l border-line">
                  {HOURS.map((h) => (
                    <div key={h} className="h-16 border-b border-line-soft" />
                  ))}
                  {appts.map((a) => {
                    const start = parseISO(a.scheduled_start)
                    const top = ((start.getHours() - 8) * 60 + start.getMinutes()) * (64 / 60)
                    const height = a.duration_minutes * (64 / 60)
                    return (
                      <div
                        key={a.id}
                        className={cn(
                          'absolute inset-x-1 overflow-hidden rounded-md border-l-2 px-1.5 py-1 text-[11px]',
                          TYPE_COLORS[a.type] ?? 'bg-surface-2 text-tx-2 border-line',
                        )}
                        style={{ top, height: Math.max(height, 24) }}
                      >
                        <p className="truncate font-medium">
                          {format(start, 'HH:mm')} · {a.patient_name ?? a.reason}
                        </p>
                        <p className="truncate">{a.reason}</p>
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}
