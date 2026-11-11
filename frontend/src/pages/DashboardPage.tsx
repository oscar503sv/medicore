import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { addDays, format, parseISO } from 'date-fns'
import { Activity, CalendarCheck, Hourglass, Users } from 'lucide-react'
import { analyticsApi } from '@/api/analytics'
import { appointmentsApi } from '@/api/appointments'
import { MetricTiles } from '@/components/analytics/MetricTiles'
import { dashboardApi } from '@/api/dashboard'
import { patientsApi } from '@/api/patients'
import { GettingStarted } from '@/components/onboarding/GettingStarted'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { statusTone } from '@/components/ui/badgeTone'
import { Card, CardHeader } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { clinicToday, fmtDate, fmtNow, fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { greetingName } from '@/lib/user'
import { useAuthStore } from '@/stores/auth'

export function DashboardPage() {
  const t = useT()
  const session = useAuthStore((s) => s.session)
  const today = clinicToday()

  const hour = new Date().getHours()
  const greetingKey =
    hour < 12 ? 'dash.greeting_morning' : hour < 19 ? 'dash.greeting_afternoon' : 'dash.greeting_evening'
  const who = greetingName(session?.name ?? '', session?.role, session?.sex)

  // Next appointments still to be attended — from now on, so the card is never empty just
  // because today's agenda is over (evenings, weekends).
  const { data: upcoming, isLoading } = useQuery({
    queryKey: ['appointments', 'upcoming'],
    queryFn: () => appointmentsApi.upcoming(6),
  })
  const tomorrow = format(addDays(parseISO(today), 1), 'yyyy-MM-dd')
  const dayLabel = (iso: string) => {
    const day = iso.slice(0, 10)
    if (day === today) return t('dash.today')
    if (day === tomorrow) return t('dash.tomorrow')
    return fmtDate(iso, 'EEE d MMM')
  }
  const { data: patients } = useQuery({
    queryKey: ['patients', { limit: 5 }],
    queryFn: () => patientsApi.list({ limit: 5 }),
  })

  const { data: summary } = useQuery({
    queryKey: ['dashboard', 'summary'],
    queryFn: dashboardApi.summary,
  })

  // Month to date against the same days of last month: every tier includes it.
  const canMetrics = useAuthStore((s) => s.can('analytics.own') || s.can('analytics.clinic'))
  const { data: month } = useQuery({
    queryKey: ['analytics', { period: 'month' }],
    queryFn: () => analyticsApi.overview({ period: 'month' }),
    enabled: canMetrics,
  })

  if (isLoading) return <PageLoader />

  const appts = upcoming ?? []
  const num = (v: number | null | undefined) => (v == null ? '—' : String(v))

  return (
    <div className="space-y-6 p-8">
      <PageHeader eyebrow={fmtNow('EEEE, d MMMM')} title={`${t(greetingKey)}, ${who}`} />

      <GettingStarted />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={CalendarCheck}
          label={t('dash.today_appointments')}
          value={num(summary?.appointments_today)}
          delta={summary?.appointments_delta_pct}
        />
        <StatCard
          icon={Users}
          label={t('dash.patients')}
          value={num(summary?.patients_total)}
          delta={summary?.patients_delta_pct}
        />
        <StatCard
          icon={Activity}
          label={t('dash.occupancy')}
          value={summary?.occupancy_pct == null ? '—' : `${summary.occupancy_pct}%`}
          delta={summary?.occupancy_delta_pts}
          deltaSuffix={` ${t('dash.points')}`}
        />
        <StatCard icon={Hourglass} label={t('dash.pending_today')} value={num(summary?.pending_today)} />
      </div>

      {month && (
        <section className="space-y-3">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-tx">{t('an.month_summary')}</h2>
            <Link to="/analytics" className="text-[13px] text-accent hover:underline">
              {t('an.see_metrics')}
            </Link>
          </div>
          <MetricTiles
            compact
            current={month.current}
            previous={month.previous}
            money={month.money}
            compareLabel={t('an.vs_previous')}
          />
        </section>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader title={t('dash.upcoming')} />
          <div className="divide-y divide-line-soft">
            {appts.map((a) => (
              <Link
                key={a.id}
                to={`/appointments?date=${a.scheduled_start.slice(0, 10)}`}
                className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-surface-2"
              >
                <div className="w-20 shrink-0">
                  <p className="text-xs capitalize text-tx-3">{dayLabel(a.scheduled_start)}</p>
                  <p className="font-mono text-[13px] text-tx-2">{fmtTime(a.scheduled_start)}</p>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-tx">{a.patient_name ?? a.code}</p>
                  <p className="truncate text-xs text-tx-3">
                    {a.reason}
                    {session?.role !== 'doctor' && a.doctor_name ? ` · ${a.doctor_name}` : ''}
                  </p>
                </div>
                <Badge tone={statusTone(a.status)}>{t(`status.${a.status}`)}</Badge>
              </Link>
            ))}
            {appts.length === 0 && (
              <p className="px-5 py-8 text-center text-sm text-tx-3">{t('dash.no_upcoming')}</p>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title={t('dash.recent_patients')} />
          <div className="divide-y divide-line-soft">
            {(patients?.items ?? []).map((p) => (
              <div key={p.id} className="flex items-center gap-3 px-5 py-3">
                <Avatar name={`${p.first_name} ${p.last_name}`} size="sm" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-tx">
                    {p.first_name} {p.last_name}
                  </p>
                  <p className="font-mono text-xs text-tx-3">{p.code}</p>
                </div>
                <span className="text-xs text-tx-3">{t('patient.age_years').replace('{n}', String(p.age))}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
