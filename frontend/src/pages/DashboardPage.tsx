import { useQuery } from '@tanstack/react-query'
import { Activity, CalendarCheck, Clock, Users } from 'lucide-react'
import { appointmentsApi } from '@/api/appointments'
import { patientsApi } from '@/api/patients'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { statusTone } from '@/components/ui/badgeTone'
import { Card, CardHeader } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/Spinner'
import { clinicToday, fmtNow, fmtTime } from '@/lib/format'
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

  const { data: appointments, isLoading } = useQuery({
    queryKey: ['appointments', 'day', today],
    queryFn: () => appointmentsApi.listForDay(today),
  })
  const { data: patients } = useQuery({
    queryKey: ['patients', { limit: 5 }],
    queryFn: () => patientsApi.list({ limit: 5 }),
  })

  if (isLoading) return <PageLoader />

  const appts = appointments ?? []
  const completed = appts.filter((a) => a.status === 'completed').length
  const occupancy = appts.length ? Math.round((completed / appts.length) * 100) : 0

  return (
    <div className="space-y-6 p-8">
      <PageHeader eyebrow={fmtNow('EEEE, d MMMM')} title={`${t(greetingKey)}, ${who}`} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={CalendarCheck} label={t('dash.today_appointments')} value={String(appts.length)} delta={12} />
        <StatCard icon={Users} label={t('dash.patients')} value={String(patients?.total ?? 0)} delta={4} />
        <StatCard icon={Activity} label={t('dash.occupancy')} value={`${occupancy}%`} delta={-3} />
        <StatCard icon={Clock} label={t('dash.avg_wait')} value="12 min" delta={-8} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader title={t('dash.upcoming')} />
          <div className="divide-y divide-line-soft">
            {appts.slice(0, 6).map((a) => (
              <div key={a.id} className="flex items-center gap-3 px-5 py-3">
                <span className="w-14 font-mono text-[13px] text-tx-2">{fmtTime(a.scheduled_start)}</span>
                <div className="flex-1">
                  <p className="text-sm font-medium text-tx">{a.reason}</p>
                  <p className="text-xs text-tx-3">{a.code}</p>
                </div>
                <Badge tone={statusTone(a.status)}>{t(`status.${a.status}`)}</Badge>
              </div>
            ))}
            {appts.length === 0 && (
              <p className="px-5 py-8 text-center text-sm text-tx-3">Sin citas para hoy</p>
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
                <span className="text-xs text-tx-3">{p.age} años</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
