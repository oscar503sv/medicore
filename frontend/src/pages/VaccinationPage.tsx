import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { differenceInMonths, format, parseISO, subYears } from 'date-fns'
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Clock,
  Phone,
  Search,
  Syringe,
} from 'lucide-react'
import {
  vaccinationsApi,
  type DoseStatus,
  type ScheduledDose,
  type VaccinationRecord,
  type WorklistDose,
  type WorklistPatient,
} from '@/api/vaccinations'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { cn } from '@/lib/cn'
import { fmtDate } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { STATUS_TONE, doseLabel, vaccineName } from '@/lib/vaccination'

type View = 'pending' | 'upcoming' | 'today'
type Horizon = '30' | '60' | '90'

/** Severity order: the worst dose decides a patient's row status. */
const SEVERITY: DoseStatus[] = ['overdue', 'due', 'due_soon', 'upcoming']

interface PatientGroup {
  patient: WorklistPatient
  doses: WorklistDose[]
  /** The most recent due date among its doses: what drives the order. */
  lastDue: string | null
  worst: DoseStatus
}

/**
 * One row per patient, their doses as chips. Pending: most recently due first — a baby's
 * dose that fell due last week is more actionable than an adult's Td never on file.
 * Upcoming: soonest first.
 */
function groupByPatient(items: WorklistDose[], newestFirst: boolean): PatientGroup[] {
  const map = new Map<string, PatientGroup>()
  for (const it of items) {
    const g = map.get(it.patient.id) ?? {
      patient: it.patient,
      doses: [],
      lastDue: null,
      worst: it.status,
    }
    g.doses.push(it)
    if (it.due_on && (!g.lastDue || it.due_on > g.lastDue)) g.lastDue = it.due_on
    if (SEVERITY.indexOf(it.status) < SEVERITY.indexOf(g.worst)) g.worst = it.status
    map.set(it.patient.id, g)
  }
  const groups = [...map.values()]
  if (newestFirst) {
    for (const g of groups) g.doses.sort((a, b) => (b.due_on ?? '').localeCompare(a.due_on ?? ''))
  }
  return groups.sort((a, b) =>
    newestFirst
      ? (b.lastDue ?? '').localeCompare(a.lastDue ?? '')
      : (a.doses[0]?.due_on ?? '').localeCompare(b.doses[0]?.due_on ?? ''),
  )
}

const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

/** Babies are counted in months, everyone else in years. */
function useAgeLabel() {
  const t = useT()
  return (p: WorklistPatient, today: string) => {
    const months = differenceInMonths(parseISO(today), parseISO(p.date_of_birth))
    return months < 24
      ? t('vax.age_short_months').replace('{n}', String(months))
      : t('vax.age_short').replace('{n}', String(p.age))
  }
}

export function VaccinationPage() {
  const t = useT()
  const navigate = useNavigate()
  const ageOf = useAgeLabel()
  const [view, setView] = useState<View>('pending')
  const [horizon, setHorizon] = useState<Horizon>('30')
  const [q, setQ] = useState('')

  const { data: catalog } = useQuery({
    queryKey: ['vaccination-catalog'],
    queryFn: vaccinationsApi.catalog,
    staleTime: Infinity,
  })
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['vaccination-worklist', horizon],
    queryFn: () => vaccinationsApi.worklist(Number(horizon)),
    placeholderData: keepPreviousData,
  })

  const doses = useMemo(
    () => new Map<string, ScheduledDose>((catalog?.doses ?? []).map((d) => [d.key, d])),
    [catalog],
  )

  const matches = (p: WorklistPatient, vaccineCodes: string[]) => {
    const needle = fold(q.trim())
    if (!needle) return true
    const hay = fold(
      [p.name, p.code, p.phone ?? '', ...vaccineCodes.map((c) => vaccineName(t, c))].join(' '),
    )
    return needle.split(/\s+/).every((w) => hay.includes(w))
  }

  const pending = useMemo(() => groupByPatient(data?.pending ?? [], true), [data])
  const upcoming = useMemo(() => groupByPatient(data?.upcoming ?? [], false), [data])
  const overdueCount = data?.pending.filter((d) => d.status === 'overdue').length ?? 0
  const dueCount = (data?.pending.length ?? 0) - overdueCount

  const openCard = (patientId: string) => navigate(`/patients/${patientId}?tab=vaccines`)

  return (
    <div className="space-y-5 p-8">
      <PageHeader eyebrow={t('vax.scheme')} title={t('vax.page_title')} />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          icon={AlertTriangle}
          label={t('vax.stat_overdue')}
          value={data ? String(overdueCount) : '—'}
        />
        <StatCard icon={Clock} label={t('vax.stat_due')} value={data ? String(dueCount) : '—'} />
        <StatCard
          icon={CalendarClock}
          label={t('vax.stat_upcoming').replace('{n}', horizon)}
          value={data ? String(data.upcoming.length) : '—'}
        />
        <StatCard
          icon={CheckCircle2}
          label={t('vax.stat_today')}
          value={data ? String(data.given_today.length) : '—'}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Segmented<View>
          value={view}
          onChange={setView}
          options={[
            {
              value: 'pending',
              label: (
                <Count
                  label={t('vax.tab_pending')}
                  n={pending.length}
                  active={view === 'pending'}
                  alert
                />
              ),
            },
            {
              value: 'upcoming',
              label: (
                <Count
                  label={t('vax.tab_upcoming')}
                  n={upcoming.length}
                  active={view === 'upcoming'}
                />
              ),
            },
            {
              value: 'today',
              label: (
                <Count
                  label={t('vax.tab_today')}
                  n={data?.given_today.length ?? 0}
                  active={view === 'today'}
                />
              ),
            },
          ]}
        />
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('vax.search_ph')}
            className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
          />
        </div>
        {view === 'upcoming' && (
          <Segmented<Horizon>
            value={horizon}
            onChange={setHorizon}
            options={(['30', '60', '90'] as const).map((h) => ({
              value: h,
              label: t('vax.days').replace('{n}', h),
            }))}
          />
        )}
      </div>

      <Card className={cn('transition-opacity', isFetching && !isLoading && 'opacity-70')}>
        {isLoading || !data ? (
          <PageLoader />
        ) : view === 'today' ? (
          <GivenToday
            rows={data.given_today.filter((g) => matches(g.patient, [g.record.vaccine_code]))}
            doses={doses}
            onOpen={openCard}
            ageOf={(p) => ageOf(p, data.today)}
          />
        ) : (
          <DueTable
            groups={(view === 'pending' ? pending : upcoming).filter((g) =>
              matches(
                g.patient,
                g.doses.map((d) => d.vaccine),
              ),
            )}
            doses={doses}
            onOpen={openCard}
            ageOf={(p) => ageOf(p, data.today)}
            empty={t(view === 'pending' ? 'vax.empty_pending' : 'vax.empty_upcoming')}
          />
        )}
      </Card>
    </div>
  )
}

function Count({
  label,
  n,
  active,
  alert,
}: {
  label: string
  n: number
  active: boolean
  alert?: boolean
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {label}
      <span
        className={cn(
          'rounded-full px-1.5 py-0.5 text-[11px] tabular-nums',
          active
            ? 'bg-white/25 text-white'
            : alert && n > 0
              ? 'bg-[var(--danger-10)] text-danger'
              : 'bg-surface-2 text-tx-3',
        )}
      >
        {n}
      </span>
    </span>
  )
}

function PatientCell({ p, age }: { p: WorklistPatient; age: string }) {
  return (
    <div className="flex items-center gap-3">
      <Avatar name={p.name} size="sm" />
      <div className="min-w-0">
        <p className="font-medium text-tx">{p.name}</p>
        <p className="font-mono text-xs text-tx-3">
          {p.code}
          <span className="font-sans"> · {age}</span>
        </p>
      </div>
    </div>
  )
}

function PhoneCell({ phone }: { phone: string | null }) {
  return phone ? (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-tx-2">
      <Phone className="h-3.5 w-3.5 text-tx-4" />
      {phone}
    </span>
  ) : (
    <span className="text-tx-4">—</span>
  )
}

function DueTable({
  groups,
  doses,
  onOpen,
  ageOf,
  empty,
}: {
  groups: PatientGroup[]
  doses: Map<string, ScheduledDose>
  onOpen: (patientId: string) => void
  ageOf: (p: WorklistPatient) => string
  empty: string
}) {
  const t = useT()
  // A periodic dose due for years means none was ever recorded (e.g. an adult's Td).
  const longAgo = format(subYears(new Date(), 5), 'yyyy-MM-dd')
  if (groups.length === 0) return <EmptyState icon={CheckCircle2} title={empty} />
  return (
    <Table>
      <thead>
        <tr>
          <Th>{t('vax.col_patient')}</Th>
          <Th>{t('vax.col_vaccine')}</Th>
          <Th>{t('vax.col_due')}</Th>
          <Th>{t('vax.col_status')}</Th>
          <Th>{t('vax.col_contact')}</Th>
        </tr>
      </thead>
      <tbody>
        {groups.map((g) => (
          <Tr key={g.patient.id} onClick={() => onOpen(g.patient.id)}>
            <Td>
              <PatientCell p={g.patient} age={ageOf(g.patient)} />
            </Td>
            <Td>
              <div className="flex max-w-md flex-wrap gap-1">
                {g.doses.map((d) => {
                  const dose = doses.get(d.key)
                  return (
                    <span
                      key={d.key}
                      className="inline-flex items-center gap-1 rounded-md border border-line-soft bg-surface-2/60 px-2 py-0.5 text-xs text-tx-2"
                      title={d.due_on ? fmtDate(d.due_on) : undefined}
                    >
                      <Syringe
                        className={cn(
                          'h-3 w-3',
                          d.status === 'overdue' ? 'text-danger' : 'text-tx-4',
                        )}
                      />
                      {vaccineName(t, d.vaccine)}
                      {dose && <span className="text-tx-4">· {doseLabel(t, dose)}</span>}
                    </span>
                  )
                })}
              </div>
            </Td>
            <Td className="whitespace-nowrap text-[13px] text-tx-2">
              {g.lastDue && g.lastDue < longAgo ? (
                <span className="text-tx-3">{t('vax.never_recorded')}</span>
              ) : (
                <span className="font-mono">{fmtDate(g.lastDue)}</span>
              )}
            </Td>
            <Td>
              <Badge tone={STATUS_TONE[g.worst]}>{t(`vax.status.${g.worst}`)}</Badge>
            </Td>
            <Td>
              <PhoneCell phone={g.patient.phone} />
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

function GivenToday({
  rows,
  doses,
  onOpen,
  ageOf,
}: {
  rows: { patient: WorklistPatient; record: VaccinationRecord }[]
  doses: Map<string, ScheduledDose>
  onOpen: (patientId: string) => void
  ageOf: (p: WorklistPatient) => string
}) {
  const t = useT()
  if (rows.length === 0) return <EmptyState icon={Syringe} title={t('vax.empty_today')} />
  return (
    <Table>
      <thead>
        <tr>
          <Th>{t('vax.col_patient')}</Th>
          <Th>{t('vax.col_vaccine')}</Th>
          <Th>{t('vax.col_lot')}</Th>
          <Th>{t('vax.site')}</Th>
          <Th>{t('vax.col_by')}</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ patient, record: r }) => {
          const dose = r.dose_key ? doses.get(r.dose_key) : undefined
          return (
            <Tr key={r.id} onClick={() => onOpen(patient.id)}>
              <Td>
                <PatientCell p={patient} age={ageOf(patient)} />
              </Td>
              <Td>
                <p className="text-tx">{vaccineName(t, r.vaccine_code)}</p>
                {dose && <p className="text-xs text-tx-3">{doseLabel(t, dose)}</p>}
              </Td>
              <Td className="font-mono text-[13px] text-tx-2">{r.lot ?? '—'}</Td>
              <Td className="text-tx-2">{r.site ? t(`vax.site.${r.site}`) : '—'}</Td>
              <Td className="text-tx-2">{r.recorded_by_name ?? '—'}</Td>
            </Tr>
          )
        })}
      </tbody>
    </Table>
  )
}
