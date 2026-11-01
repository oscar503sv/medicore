import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Clock, Plus, Search, Syringe, Timer } from 'lucide-react'
import {
  applicationsApi,
  type ApplicationOrder,
  type ApplicationRecord,
  type WorklistPatient,
} from '@/api/applications'
import { ApplyModal, type ApplyTarget } from '@/components/applications/ApplyModal'
import { ExternalOrderModal } from '@/components/applications/ExternalOrderModal'
import { ObservationActions, ObservationTimer } from '@/components/applications/ObservationActions'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { originLabel } from '@/lib/applications'
import { cn } from '@/lib/cn'
import { fmtTime, fmtTimeTz } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'

type View = 'due' | 'observing' | 'done'

const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

/** Nursing worklist: doses to apply today, patients under observation, what was recorded. */
export function ApplicationsPage() {
  const t = useT()
  const navigate = useNavigate()
  const canAdminister = useAuthStore((s) => s.can('applications.administer'))
  const [view, setView] = useState<View>('due')
  const [q, setQ] = useState('')
  const [walkIn, setWalkIn] = useState(false)
  const [applying, setApplying] = useState<ApplyTarget | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['applications-worklist'],
    queryFn: applicationsApi.worklist,
    refetchInterval: 30_000,
  })

  const matches = (p: WorklistPatient, o: ApplicationOrder) => {
    const needle = fold(q.trim())
    if (!needle) return true
    const hay = fold([p.name, p.code, o.drug].join(' '))
    return needle.split(/\s+/).every((w) => hay.includes(w))
  }

  const late = data?.due.filter((d) => d.late).length ?? 0
  const openPatient = (id: string) => navigate(`/patients/${id}?tab=applications`)

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        eyebrow={t('apl.page_eyebrow')}
        title={t('apl.page_title')}
        action={
          canAdminister && (
            <Button variant="accent" onClick={() => setWalkIn(true)}>
              <Plus className="h-4 w-4" />
              {t('apl.walk_in')}
            </Button>
          )
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          icon={Clock}
          label={t('apl.stat_due')}
          value={data ? String(data.due.length) : '—'}
        />
        <StatCard
          icon={AlertTriangle}
          label={t('apl.stat_late')}
          value={data ? String(late) : '—'}
        />
        <StatCard
          icon={Timer}
          label={t('apl.stat_observing')}
          value={data ? String(data.observing.length) : '—'}
        />
        <StatCard
          icon={CheckCircle2}
          label={t('apl.stat_done')}
          value={data ? String(data.done_today.length) : '—'}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Segmented<View>
          value={view}
          onChange={setView}
          options={[
            {
              value: 'due',
              label: (
                <Count
                  label={t('apl.tab_due')}
                  n={data?.due.length ?? 0}
                  active={view === 'due'}
                  alert={late > 0}
                />
              ),
            },
            {
              value: 'observing',
              label: (
                <Count
                  label={t('apl.tab_observing')}
                  n={data?.observing.length ?? 0}
                  active={view === 'observing'}
                  alert
                />
              ),
            },
            {
              value: 'done',
              label: (
                <Count
                  label={t('apl.tab_done')}
                  n={data?.done_today.length ?? 0}
                  active={view === 'done'}
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
            placeholder={t('apl.search_ph')}
            className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
          />
        </div>
      </div>

      <Card>
        {isLoading || !data ? (
          <PageLoader />
        ) : view === 'due' ? (
          <DueTable
            rows={data.due.filter((d) => matches(d.patient, d.order))}
            now={data.now}
            canAdminister={canAdminister}
            onOpen={openPatient}
            onApply={(row) => setApplying({ order: row.order, patientName: row.patient.name })}
          />
        ) : view === 'observing' ? (
          <ObservingTable
            rows={data.observing.filter((d) => matches(d.patient, d.order))}
            canAdminister={canAdminister}
            onOpen={openPatient}
          />
        ) : (
          <DoneTable
            rows={data.done_today.filter((d) => matches(d.patient, d.order))}
            onOpen={openPatient}
          />
        )}
      </Card>

      <ExternalOrderModal open={walkIn} onClose={() => setWalkIn(false)} />
      <ApplyModal target={applying} onClose={() => setApplying(null)} />
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
              ? 'bg-[var(--warn-10)] text-warn'
              : 'bg-surface-2 text-tx-3',
        )}
      >
        {n}
      </span>
    </span>
  )
}

function PatientCell({ p }: { p: WorklistPatient }) {
  const t = useT()
  return (
    <div className="flex items-center gap-3">
      <Avatar name={p.name} size="sm" />
      <div className="min-w-0">
        <p className="font-medium text-tx">{p.name}</p>
        <p className="font-mono text-xs text-tx-3">
          {p.code}
          <span className="font-sans"> · {t('vax.age_short').replace('{n}', String(p.age))}</span>
        </p>
      </div>
    </div>
  )
}

function DrugCell({ order, conflicts }: { order: ApplicationOrder; conflicts?: string[] }) {
  const t = useT()
  return (
    <div>
      <p className="flex items-center gap-1.5 font-medium text-tx">
        {order.drug} {order.dose}
        <span className="text-xs font-normal text-tx-3">
          · {t(`apl.route_short.${order.route}`)}
        </span>
        {conflicts && conflicts.length > 0 && (
          <span title={t('apl.allergy_flag').replace('{list}', conflicts.join(', '))}>
            <AlertTriangle className="h-3.5 w-3.5 text-danger" />
          </span>
        )}
      </p>
      {order.instructions && (
        <p className="max-w-xs truncate text-xs text-tx-3" title={order.instructions}>
          {order.instructions}
        </p>
      )}
    </div>
  )
}

type DueRow = { patient: WorklistPatient; order: ApplicationOrder; late: boolean }

function DueTable({
  rows,
  now,
  canAdminister,
  onOpen,
  onApply,
}: {
  rows: DueRow[]
  now: string
  canAdminister: boolean
  onOpen: (patientId: string) => void
  onApply: (row: DueRow) => void
}) {
  const t = useT()
  if (rows.length === 0) return <EmptyState icon={CheckCircle2} title={t('apl.empty_due')} />
  return (
    <Table>
      <thead>
        <tr>
          <Th>{t('apl.col_patient')}</Th>
          <Th>{t('apl.col_drug')}</Th>
          <Th>{t('apl.col_dose')}</Th>
          <Th>{t('apl.col_time')}</Th>
          <Th>{t('apl.col_origin')}</Th>
          <Th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const { patient, order } = row
          const due = order.next_due_at
          return (
            <Tr key={order.id} onClick={() => onOpen(patient.id)}>
              <Td>
                <PatientCell p={patient} />
              </Td>
              <Td>
                <DrugCell order={order} conflicts={order.allergy_conflicts} />
              </Td>
              <Td className="whitespace-nowrap text-[13px] text-tx-2">
                {t('apl.dose_of')
                  .replace('{n}', String(order.next_dose ?? 1))
                  .replace('{total}', String(order.doses_total))}
              </Td>
              <Td className="whitespace-nowrap">
                <span className="font-mono text-[13px] text-tx-2">{fmtTime(due)}</span>{' '}
                {row.late ? (
                  <Badge tone="danger">{t('apl.late')}</Badge>
                ) : due && due <= now ? (
                  <Badge tone="warn">{t('apl.now')}</Badge>
                ) : (
                  <Badge tone="neutral">{t('apl.later')}</Badge>
                )}
              </Td>
              <Td className="text-[13px] text-tx-3">{originLabel(t, order)}</Td>
              <Td className="text-right">
                {canAdminister && (
                  <Button
                    size="sm"
                    variant="accent"
                    onClick={(e) => {
                      e.stopPropagation()
                      onApply(row)
                    }}
                  >
                    <Syringe className="h-3.5 w-3.5" />
                    {t('apl.apply')}
                  </Button>
                )}
              </Td>
            </Tr>
          )
        })}
      </tbody>
    </Table>
  )
}

function ObservingTable({
  rows,
  canAdminister,
  onOpen,
}: {
  rows: { patient: WorklistPatient; order: ApplicationOrder; record: ApplicationRecord }[]
  canAdminister: boolean
  onOpen: (patientId: string) => void
}) {
  const t = useT()
  if (rows.length === 0) return <EmptyState icon={Timer} title={t('apl.empty_observing')} />
  return (
    <Table>
      <thead>
        <tr>
          <Th>{t('apl.col_patient')}</Th>
          <Th>{t('apl.col_drug')}</Th>
          <Th>{t('apl.col_time')}</Th>
          <Th>{t('apl.col_observation')}</Th>
          <Th />
        </tr>
      </thead>
      <tbody>
        {rows.map(({ patient, order, record }) => (
          <Tr key={record.id} onClick={() => onOpen(patient.id)}>
            <Td>
              <PatientCell p={patient} />
            </Td>
            <Td>
              <DrugCell order={order} />
            </Td>
            <Td className="whitespace-nowrap font-mono text-[13px] text-tx-2">
              {fmtTimeTz(record.recorded_at)}
            </Td>
            <Td>
              <ObservationTimer record={record} />
            </Td>
            <Td className="text-right">
              {canAdminister && <ObservationActions record={record} order={order} />}
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

function DoneTable({
  rows,
  onOpen,
}: {
  rows: { patient: WorklistPatient; order: ApplicationOrder; record: ApplicationRecord }[]
  onOpen: (patientId: string) => void
}) {
  const t = useT()
  if (rows.length === 0) return <EmptyState icon={Syringe} title={t('apl.empty_done')} />
  return (
    <Table>
      <thead>
        <tr>
          <Th>{t('apl.col_patient')}</Th>
          <Th>{t('apl.col_drug')}</Th>
          <Th>{t('apl.col_time')}</Th>
          <Th>{t('apl.col_status')}</Th>
          <Th>{t('apl.col_by')}</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ patient, order, record }) => (
          <Tr key={record.id} onClick={() => onOpen(patient.id)}>
            <Td>
              <PatientCell p={patient} />
            </Td>
            <Td>
              <DrugCell order={order} />
              <p className="text-xs text-tx-3">
                {t('apl.dose_of')
                  .replace('{n}', String(record.dose_number))
                  .replace('{total}', String(order.doses_total))}
              </p>
            </Td>
            <Td className="whitespace-nowrap font-mono text-[13px] text-tx-2">
              {fmtTimeTz(record.recorded_at)}
            </Td>
            <Td>
              <div className="flex flex-wrap gap-1">
                <Badge tone={record.outcome === 'applied' ? 'ok' : 'warn'}>
                  {t(`apl.outcome.${record.outcome}`)}
                </Badge>
                {record.reaction && <Badge tone="danger">{t('apl.reaction')}</Badge>}
                {record.allergy_override && (
                  <span title={record.allergy_override}>
                    <AlertTriangle className="h-4 w-4 text-warn" />
                  </span>
                )}
              </div>
            </Td>
            <Td className="text-[13px] text-tx-2">{record.recorded_by_name ?? '—'}</Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}
