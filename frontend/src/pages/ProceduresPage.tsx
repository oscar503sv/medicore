import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarClock, CheckCircle2, ClipboardList, Hourglass, Plus, Search } from 'lucide-react'
import {
  proceduresApi,
  type Procedure,
  type ProcedurePatient,
  type ProcedureWorklist,
} from '@/api/procedures'
import { PageHeader } from '@/components/PageHeader'
import { ProcedureCatalog } from '@/components/procedures/ProcedureCatalog'
import { ProcedureCell } from '@/components/procedures/ProcedureCell'
import {
  NewProcedureModal,
  type PickedPatient,
  type ProcedureAppointment,
} from '@/components/procedures/NewProcedureModal'
import { StatCard } from '@/components/StatCard'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { cn } from '@/lib/cn'
import { clinicToday, fmtDate, fmtDateTimeTz, fmtDateTz, fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { STATUS_TONE } from '@/lib/procedures'
import { useAuthStore } from '@/stores/auth'

type View = 'pending' | 'today' | 'done' | 'catalog'

const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

/** Procedures worklist: pending orders, today's procedure appointments, what was signed. */
export function ProceduresPage() {
  const t = useT()
  const navigate = useNavigate()
  const canPerform = useAuthStore((s) => s.can('procedures.perform'))
  const canCatalog = useAuthStore((s) => s.can('procedures.catalog'))
  const [view, setView] = useState<View>('pending')
  const [q, setQ] = useState('')
  const [creating, setCreating] = useState<{
    patient?: PickedPatient
    appointment?: ProcedureAppointment
  } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['procedures-worklist'],
    queryFn: proceduresApi.worklist,
    refetchInterval: 30_000,
  })

  const matches = (p: ProcedurePatient, text: string) => {
    const needle = fold(q.trim())
    if (!needle) return true
    const hay = fold([p.name, p.code, text].join(' '))
    return needle.split(/\s+/).every((w) => hay.includes(w))
  }
  const open = (id: string) => navigate(`/procedures/${id}`)
  const today = clinicToday()
  const doneToday = data?.done.filter(
    (d) => fmtDateTz(d.procedure.performed_at, 'yyyy-MM-dd') === today,
  ).length

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        eyebrow={t('prc.page_eyebrow')}
        title={t('prc.page_title')}
        action={
          canPerform && (
            <Button variant="accent" onClick={() => setCreating({})}>
              <Plus className="h-4 w-4" />
              {t('prc.new')}
            </Button>
          )
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          icon={Hourglass}
          label={t('prc.stat_pending')}
          value={data ? String(data.pending.length) : '—'}
        />
        <StatCard
          icon={CalendarClock}
          label={t('prc.stat_today')}
          value={data ? String(data.today.length) : '—'}
        />
        <StatCard
          icon={CheckCircle2}
          label={t('prc.stat_done_today')}
          value={doneToday !== undefined ? String(doneToday) : '—'}
        />
        <StatCard
          icon={ClipboardList}
          label={t('prc.stat_done')}
          value={data ? String(data.done.length) : '—'}
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
                  label={t('prc.tab_pending')}
                  n={data?.pending.length ?? 0}
                  active={view === 'pending'}
                />
              ),
            },
            {
              value: 'today',
              label: (
                <Count
                  label={t('prc.tab_today')}
                  n={data?.today.length ?? 0}
                  active={view === 'today'}
                />
              ),
            },
            { value: 'done', label: t('prc.tab_done') },
            ...(canCatalog ? [{ value: 'catalog' as const, label: t('prc.tab_catalog') }] : []),
          ]}
        />
        {view !== 'catalog' && (
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t('prc.search_ph')}
              className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
            />
          </div>
        )}
      </div>

      <Card>
        {view === 'catalog' ? (
          <ProcedureCatalog />
        ) : isLoading || !data ? (
          <PageLoader />
        ) : view === 'pending' ? (
          <PendingTable
            rows={data.pending.filter((d) => matches(d.patient, d.procedure.type_name))}
            onOpen={open}
          />
        ) : view === 'today' ? (
          <TodayTable
            rows={data.today.filter((d) =>
              matches(d.patient, `${d.reason} ${d.procedure?.type_name ?? ''}`),
            )}
            canPerform={canPerform}
            onOpen={open}
            onRegister={(row) =>
              setCreating({
                patient: row.patient,
                appointment: {
                  id: row.appointment_id,
                  start: row.scheduled_start,
                  reason: row.reason,
                },
              })
            }
          />
        ) : (
          <DoneTable
            rows={data.done.filter((d) => matches(d.patient, d.procedure.type_name))}
            onOpen={open}
          />
        )}
      </Card>

      <NewProcedureModal
        open={creating !== null}
        onClose={() => setCreating(null)}
        patient={creating?.patient}
        appointment={creating?.appointment}
      />
    </div>
  )
}

function Count({ label, n, active }: { label: string; n: number; active: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {label}
      <span
        className={cn(
          'rounded-full px-1.5 py-0.5 text-[11px] tabular-nums',
          active
            ? 'bg-white/25 text-white'
            : n > 0
              ? 'bg-[var(--warn-10)] text-warn'
              : 'bg-surface-2 text-tx-3',
        )}
      >
        {n}
      </span>
    </span>
  )
}

function PatientCell({ p }: { p: ProcedurePatient }) {
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

type Row = { patient: ProcedurePatient; procedure: Procedure }

function PendingTable({ rows, onOpen }: { rows: Row[]; onOpen: (id: string) => void }) {
  const t = useT()
  if (rows.length === 0) return <EmptyState icon={CheckCircle2} title={t('prc.empty_pending')} />
  return (
    <Table>
      <thead>
        <tr>
          <Th>{t('prc.col_patient')}</Th>
          <Th>{t('prc.col_procedure')}</Th>
          <Th>{t('prc.col_origin')}</Th>
          <Th>{t('prc.col_since')}</Th>
          <Th>{t('prc.col_status')}</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ patient, procedure: p }) => (
          <Tr key={p.id} onClick={() => onOpen(p.id)}>
            <Td>
              <PatientCell p={patient} />
            </Td>
            <Td>
              <ProcedureCell p={p} />
            </Td>
            <Td className="text-[13px] text-tx-3">
              <p>{t(`prc.source.${p.source}`)}</p>
              {p.ordered_by_name && (
                <p className="text-xs">
                  {t('prc.ordered_by').replace('{name}', p.ordered_by_name)}
                </p>
              )}
            </Td>
            <Td className="whitespace-nowrap text-[13px] text-tx-2">
              {fmtDateTimeTz(p.created_at)}
            </Td>
            <Td>
              <Badge tone={STATUS_TONE[p.status]}>{t(`prc.status.${p.status}`)}</Badge>
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

type TodayRow = ProcedureWorklist['today'][number]

function TodayTable({
  rows,
  canPerform,
  onOpen,
  onRegister,
}: {
  rows: TodayRow[]
  canPerform: boolean
  onOpen: (id: string) => void
  onRegister: (row: TodayRow) => void
}) {
  const t = useT()
  if (rows.length === 0) return <EmptyState icon={CalendarClock} title={t('prc.empty_today')} />
  return (
    <Table>
      <thead>
        <tr>
          <Th>{t('prc.col_time')}</Th>
          <Th>{t('prc.col_patient')}</Th>
          <Th>{t('prc.col_reason')}</Th>
          <Th>{t('prc.col_doctor')}</Th>
          <Th>{t('prc.col_status')}</Th>
          <Th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const p = row.procedure
          return (
            <Tr key={row.appointment_id} onClick={p ? () => onOpen(p.id) : undefined}>
              <Td className="whitespace-nowrap font-mono text-[13px] text-tx-2">
                {fmtTime(row.scheduled_start)}
              </Td>
              <Td>
                <PatientCell p={row.patient} />
              </Td>
              <Td className="text-[13px] text-tx-2">{p ? <ProcedureCell p={p} /> : row.reason}</Td>
              <Td className="text-[13px] text-tx-2">{row.doctor_name ?? '—'}</Td>
              <Td>
                {p ? (
                  <Badge tone={STATUS_TONE[p.status]}>{t(`prc.status.${p.status}`)}</Badge>
                ) : (
                  <Badge tone="neutral">{t('prc.not_registered')}</Badge>
                )}
              </Td>
              <Td className="text-right">
                {!p && canPerform && (
                  <Button size="sm" variant="accent" onClick={() => onRegister(row)}>
                    {t('prc.register')}
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

function DoneTable({ rows, onOpen }: { rows: Row[]; onOpen: (id: string) => void }) {
  const t = useT()
  if (rows.length === 0) return <EmptyState icon={ClipboardList} title={t('prc.empty_done')} />
  return (
    <Table>
      <thead>
        <tr>
          <Th>{t('prc.col_performed')}</Th>
          <Th>{t('prc.col_patient')}</Th>
          <Th>{t('prc.col_procedure')}</Th>
          <Th>{t('prc.col_by')}</Th>
          <Th>{t('prc.col_specimen')}</Th>
          <Th>{t('prc.col_follow_up')}</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ patient, procedure: p }) => (
          <Tr key={p.id} onClick={() => onOpen(p.id)}>
            <Td className="whitespace-nowrap text-[13px] text-tx-2">
              {fmtDateTimeTz(p.performed_at)}
            </Td>
            <Td>
              <PatientCell p={patient} />
            </Td>
            <Td>
              <ProcedureCell p={p} />
            </Td>
            <Td className="text-[13px] text-tx-2">{p.performed_by_name ?? '—'}</Td>
            <Td className="text-[13px] text-tx-2">
              {p.specimen_sent ? <Badge tone="info">{t('prc.specimen_badge')}</Badge> : '—'}
            </Td>
            <Td className="whitespace-nowrap text-[13px] text-tx-2">
              {p.follow_up_on ? fmtDate(p.follow_up_on) : '—'}
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}
