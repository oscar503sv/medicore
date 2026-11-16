import { useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { addDays, format, parseISO } from 'date-fns'
import {
  BadgeDollarSign,
  Calendar as CalendarIcon,
  CalendarCheck,
  CalendarClock,
  CalendarDays,
  CalendarX,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Clock,
  HeartPulse,
  Plus,
  Printer,
  Search,
  Stethoscope,
  Syringe,
  UserX,
  X,
} from 'lucide-react'
import { appointmentsApi } from '@/api/appointments'
import { openPrint } from '@/api/printing'
import { consultationsApi } from '@/api/consultations'
import { errorMessage } from '@/api/client'
import { ConsultationVitalsModal } from '@/components/consultation/ConsultationVitalsModal'
import { AssigneeFilter } from '@/components/appointments/AssigneeFilter'
import { NewAppointmentModal } from '@/components/appointments/NewAppointmentModal'
import { WalkInBadge } from '@/components/appointments/WalkInBadge'
import { WalkInButton } from '@/components/appointments/WalkInButton'
import { RescheduleAppointmentModal } from '@/components/appointments/RescheduleAppointmentModal'
import { VaccinationVisitModal, type VisitTarget } from '@/components/vaccination/VaccinationVisitModal'
import { AdjustFeeModal } from '@/components/fees/AdjustFeeModal'
import { FeeCell } from '@/components/fees/FeeCell'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { Badge } from '@/components/ui/Badge'
import { statusTone } from '@/components/ui/badgeTone'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Menu, type MenuItem } from '@/components/ui/Menu'
import { Modal } from '@/components/ui/Modal'
import { Pager, PAGE_SIZE } from '@/components/ui/Pager'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { assigneeName, matchesAssignee } from '@/lib/assignee'
import { cn } from '@/lib/cn'
import { useCanPrice } from '@/lib/fees'
import { clinicNowTime, clinicToday, fmtDate, fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import type { Appointment, AppointmentStatus } from '@/types'

const STATUSES: AppointmentStatus[] = [
  'scheduled',
  'confirmed',
  'in_progress',
  'completed',
  'cancelled',
  'no_show',
]
/** Still ahead of the patient: can be confirmed, rescheduled, cancelled or marked no-show. */
const PENDING = new Set<AppointmentStatus>(['scheduled', 'confirmed'])
const ACTIVE = new Set<AppointmentStatus>(['scheduled', 'confirmed', 'in_progress'])

export function AppointmentsPage() {
  const t = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const canConsult = useAuthStore((s) => s.can('consultations.start'))
  const canEditConsult = useAuthStore((s) => s.can('consultations.edit'))
  const canVitals = useAuthStore((s) => s.can('consultations.vitals'))
  const myId = useAuthStore((s) => s.session?.user_id)
  const canManage = useAuthStore((s) => s.can('appointments.manage'))
  const isDoctor = useAuthStore((s) => s.hasRole('doctor'))
  const canRecordVaccines = useAuthStore((s) => s.can('vaccinations.record'))
  const today = clinicToday()
  // The date lives in the URL: deep links (notifications, dashboard, agenda) and the back
  // button land on the right day.
  const [searchParams, setSearchParams] = useSearchParams()
  const dateParam = searchParams.get('date')
  const date = dateParam && /^\d{4}-\d{2}-\d{2}$/.test(dateParam) ? dateParam : today
  const [modalOpen, setModalOpen] = useState(false)
  const [cancelTarget, setCancelTarget] = useState<Appointment | null>(null)
  const [noShowTarget, setNoShowTarget] = useState<Appointment | null>(null)
  const [rescheduleTarget, setRescheduleTarget] = useState<Appointment | null>(null)
  const [feeTarget, setFeeTarget] = useState<Appointment | null>(null)
  const [vitalsTarget, setVitalsTarget] = useState<Appointment | null>(null)
  const [visitTarget, setVisitTarget] = useState<VisitTarget | null>(null)
  const canPrice = useCanPrice()
  const [statusFilter, setStatusFilter] = useState<'all' | AppointmentStatus>('all')
  const [assignee, setAssignee] = useState('')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const dateInput = useRef<HTMLInputElement>(null)

  const setDate = (d: string) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return
    setSearchParams({ date: d }, { replace: true })
    setOffset(0)
  }
  const shiftDate = (n: number) => setDate(format(addDays(parseISO(date), n), 'yyyy-MM-dd'))

  const { data, isLoading } = useQuery({
    queryKey: ['appointments', 'day', date],
    queryFn: () => appointmentsApi.listForDay(date),
  })

  // A doctor manages only their own appointments (the backend refuses the rest).
  const canManageAppt = (a: Appointment) => canManage && (!isDoctor || a.doctor_id === myId)

  // Doctors only see their own appointments; the doctor/agenda filter is for the front desk.
  const { data: options } = useQuery({
    queryKey: ['booking-options'],
    queryFn: () => appointmentsApi.bookingOptions(),
    enabled: canManage && !isDoctor,
  })
  const doctors = options?.doctors ?? []
  const agendas = options?.agendas ?? []

  const ofDoctor = (data ?? []).filter((a) => matchesAssignee(a, assignee))
  const countBy = (s: AppointmentStatus) => ofDoctor.filter((a) => a.status === s).length
  const term = q.trim().toLowerCase()
  const visible = ofDoctor.filter(
    (a) =>
      (statusFilter === 'all' || a.status === statusFilter) &&
      (!term ||
        (a.patient_name ?? '').toLowerCase().includes(term) ||
        a.reason.toLowerCase().includes(term) ||
        a.code.toLowerCase().includes(term)),
  )
  const paged = visible.slice(offset, offset + PAGE_SIZE)
  const showDoctorCol = !isDoctor && !assignee

  // On today's list, flag the appointment happening now and the next one due.
  const now = date === today ? clinicNowTime() : null
  const isNow = (a: Appointment) =>
    !!now &&
    ACTIVE.has(a.status) &&
    fmtTime(a.scheduled_start) <= now &&
    now < fmtTime(a.scheduled_end)
  const nextId =
    now != null
      ? ofDoctor.find((a) => PENDING.has(a.status) && fmtTime(a.scheduled_start) > now)?.id
      : undefined

  const startConsult = useMutation({
    mutationFn: (appointmentId: string) => consultationsApi.start(appointmentId),
    onSuccess: (consultation) => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      // Starting is operational (the admin may open it for the doctor); only the doctor
      // it belongs to goes on into the note.
      if (canEditConsult && consultation.doctor_id === myId) {
        navigate(`/consultation/${consultation.id}`)
      } else {
        toast(t('consult.started_ok'))
      }
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const adjustFee = useMutation({
    mutationFn: (v: { id: string; amount: string; note: string | null }) =>
      appointmentsApi.adjustFee(v.id, v.amount, v.note),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      toast(t('fee.adjusted_ok'))
      setFeeTarget(null)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const confirmAppt = useMutation({
    mutationFn: (appointmentId: string) => appointmentsApi.confirm(appointmentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      toast(t('appt.confirmed_ok'))
    },
    onError: (err) => {
      // Someone else may have moved it first: show its real state.
      qc.invalidateQueries({ queryKey: ['appointments'] })
      toast(errorMessage(err), 'danger')
    },
  })

  const cancelAppt = useMutation({
    mutationFn: (appointmentId: string) => appointmentsApi.cancel(appointmentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      qc.invalidateQueries({ queryKey: ['slots'] })
      setCancelTarget(null)
      toast(t('appt.cancelled_ok'))
    },
    onError: (err) => {
      // Someone else may have moved it first: show its real state.
      qc.invalidateQueries({ queryKey: ['appointments'] })
      toast(errorMessage(err), 'danger')
    },
  })

  const noShowAppt = useMutation({
    mutationFn: (appointmentId: string) => appointmentsApi.noShow(appointmentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      setNoShowTarget(null)
      toast(t('appt.no_show_ok'))
    },
    onError: (err) => {
      // Someone else may have moved it first: show its real state.
      qc.invalidateQueries({ queryKey: ['appointments'] })
      toast(errorMessage(err), 'danger')
    },
  })

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        title={t('appt.title')}
        action={
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => navigate(`/schedule?view=day&date=${date}`)}>
              <CalendarDays className="h-4 w-4" />
              {t('appt.view_in_schedule')}
            </Button>
            <WalkInButton />
            {canManage && (
              <Button onClick={() => setModalOpen(true)}>
                <Plus className="h-4 w-4" />
                {t('appt.new')}
              </Button>
            )}
          </div>
        }
      />

      {/* Day navigation: a readable date instead of the browser's mm/dd/yyyy field. */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center rounded-lg border border-line bg-bg">
          <button
            onClick={() => shiftDate(-1)}
            className="rounded-l-lg p-2.5 text-tx-2 hover:bg-surface-2"
            aria-label={t('sched.prev_day')}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            onClick={() => dateInput.current?.showPicker?.()}
            className="relative flex items-center gap-2 border-x border-line px-3 py-2 text-sm font-medium text-tx hover:bg-surface-2"
            title={t('appt.pick_date')}
          >
            <CalendarIcon className="h-4 w-4 text-tx-3" />
            <span className="first-letter:uppercase">{fmtDate(date, t('sched.day_pattern'))}</span>
            <input
              ref={dateInput}
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              tabIndex={-1}
              aria-hidden
              className="pointer-events-none absolute inset-0 opacity-0"
            />
          </button>
          <button
            onClick={() => shiftDate(1)}
            className="rounded-r-lg p-2.5 text-tx-2 hover:bg-surface-2"
            aria-label={t('sched.next_day')}
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        {date !== today && (
          <Button variant="ghost" size="sm" onClick={() => setDate(today)}>
            {t('sched.today')}
          </Button>
        )}
        <div className="relative ml-auto w-72">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tx-4" />
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setOffset(0)
            }}
            placeholder={t('appt.search_ph')}
            className="h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm text-tx placeholder:text-tx-4 focus:border-accent focus:outline-none"
          />
        </div>
        {doctors.length + agendas.length > 0 && (
          <AssigneeFilter
            value={assignee}
            onChange={(v) => {
              setAssignee(v)
              setOffset(0)
            }}
            doctors={doctors}
            agendas={agendas}
            className="w-56"
          />
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <StatCard
          icon={CalendarCheck}
          label={t('appt.stat_total')}
          value={String(ofDoctor.length)}
        />
        <StatCard
          icon={Clock}
          label={t('appt.stat_scheduled')}
          value={String(countBy('scheduled'))}
        />
        <StatCard
          icon={Check}
          label={t('appt.stat_confirmed')}
          value={String(countBy('confirmed'))}
        />
        <StatCard
          icon={CheckCheck}
          label={t('appt.stat_completed')}
          value={String(countBy('completed'))}
        />
        <StatCard icon={UserX} label={t('appt.stat_no_show')} value={String(countBy('no_show'))} />
      </div>

      <Segmented
        value={statusFilter}
        onChange={(v) => {
          setStatusFilter(v)
          setOffset(0)
        }}
        options={(['all', ...STATUSES] as const).map((s) => {
          const n = s === 'all' ? ofDoctor.length : countBy(s)
          return {
            value: s,
            label: (
              <>
                {s === 'all' ? t('app.all') : t(`status.${s}`)}
                <span className="ml-1.5 tabular-nums opacity-60">{n}</span>
              </>
            ),
          }
        })}
      />

      <Card>
        {isLoading ? (
          <PageLoader />
        ) : visible.length > 0 ? (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>{t('appt.col_time')}</Th>
                  <Th>{t('appt.col_patient')}</Th>
                  {showDoctorCol && <Th>{t('appt.attends')}</Th>}
                  <Th>{t('appt.col_reason')}</Th>
                  <Th>{t('appt.col_status')}</Th>
                  <Th className="text-right">{t('fee.col_fee')}</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {paged.map((a) => {
                  const inactive = a.status === 'cancelled' || a.status === 'no_show'
                  const manageable = canManageAppt(a) && PENDING.has(a.status)
                  const menu: MenuItem[] = [
                    ...(PENDING.has(a.status)
                      ? [
                          {
                            label: t('pr.btn.appointment'),
                            icon: Printer,
                            onSelect: () => openPrint(`appointment/${a.id}`),
                          },
                        ]
                      : []),
                    ...(a.status !== 'cancelled' &&
                    (a.type !== 'vaccination' || a.listed_fee !== null) &&
                    canManageAppt(a) &&
                    canPrice(a.doctor_id)
                      ? [
                          {
                            label: t('fee.adjust'),
                            icon: BadgeDollarSign,
                            onSelect: () => setFeeTarget(a),
                          },
                        ]
                      : []),
                    ...(manageable
                    ? [
                        // A walk-in is already in the clinic: nothing to move or to miss.
                        ...(a.is_walk_in
                          ? []
                          : [
                              {
                                label: t('appt.reschedule'),
                                icon: CalendarClock,
                                onSelect: () => setRescheduleTarget(a),
                              },
                              {
                                label: t('appt.no_show'),
                                icon: UserX,
                                onSelect: () => setNoShowTarget(a),
                              },
                            ]),
                        {
                          label: t('appt.cancel_appt'),
                          icon: X,
                          tone: 'danger' as const,
                          onSelect: () => setCancelTarget(a),
                        },
                      ]
                    : []),
                  ]
                  return (
                    <Tr
                      key={a.id}
                      className={cn(
                        isNow(a) && 'bg-[var(--warn-10)]',
                        a.id === nextId && 'bg-[var(--accent-10)]',
                      )}
                    >
                      <Td className="whitespace-nowrap">
                        <span
                          className={cn(
                            'font-mono',
                            inactive ? 'text-tx-3 line-through' : 'text-tx',
                          )}
                        >
                          {fmtTime(a.scheduled_start)}
                        </span>
                        <span className="font-mono text-tx-4">–{fmtTime(a.scheduled_end)}</span>
                        {isNow(a) && (
                          <span className="ml-2 align-middle">
                            <Badge tone="warn">{t('appt.now')}</Badge>
                          </span>
                        )}
                        {a.id === nextId && (
                          <span className="ml-2 align-middle">
                            <Badge tone="accent">{t('appt.next')}</Badge>
                          </span>
                        )}
                        {a.is_walk_in && (
                          <span className="ml-2 align-middle">
                            <WalkInBadge />
                          </span>
                        )}
                      </Td>
                      <Td>
                        <Link
                          to={`/patients/${a.patient_id}`}
                          className={cn(
                            'font-medium text-tx hover:text-accent hover:underline',
                            inactive && 'text-tx-3',
                          )}
                        >
                          {a.patient_name ?? '—'}
                        </Link>
                        <p className="font-mono text-xs text-tx-3">{a.code}</p>
                      </Td>
                      {showDoctorCol && <Td>{assigneeName(a, t)}</Td>}
                      <Td>
                        <p className="text-tx-2">{a.reason}</p>
                        <p className="text-xs text-tx-3">{t(`apptype.${a.type}`)}</p>
                      </Td>
                      <Td>
                        <Badge tone={statusTone(a.status)}>{t(`status.${a.status}`)}</Badge>
                      </Td>
                      <Td className="whitespace-nowrap text-right">
                        <FeeCell appointment={a} />
                      </Td>
                      <Td className="text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {/* One clear next step per status; the rest lives in the ⋯ menu. */}
                          {canManageAppt(a) && a.status === 'scheduled' && (
                            <Button
                              size="sm"
                              variant="outline"
                              loading={confirmAppt.isPending && confirmAppt.variables === a.id}
                              onClick={() => confirmAppt.mutate(a.id)}
                            >
                              <Check className="h-3.5 w-3.5" />
                              {t('appt.confirm_appt')}
                            </Button>
                          )}
                          {canConsult && !a.agenda_id && a.status === 'confirmed' && (
                            <Button
                              size="sm"
                              loading={startConsult.isPending && startConsult.variables === a.id}
                              onClick={() => startConsult.mutate(a.id)}
                            >
                              <Stethoscope className="h-3.5 w-3.5" />
                              {t('appt.start_consult')}
                            </Button>
                          )}
                          {canEditConsult && a.doctor_id === myId && a.status === 'in_progress' && (
                            <Button
                              size="sm"
                              variant="subtle"
                              onClick={() => startConsult.mutate(a.id)}
                            >
                              {t('appt.continue')}
                            </Button>
                          )}
                          {canRecordVaccines && a.type === 'vaccination' && date === today && ACTIVE.has(a.status) && (
                            <Button
                              size="sm"
                              onClick={() =>
                                setVisitTarget({
                                  appointmentId: a.id,
                                  patientId: a.patient_id,
                                  patientName: a.patient_name,
                                })
                              }
                            >
                              <Syringe className="h-3.5 w-3.5" />
                              {t('vax.visit_cta')}
                            </Button>
                          )}
                          {canVitals &&
                            !a.agenda_id &&
                            (a.status === 'confirmed' || a.status === 'in_progress') && (
                            <Button size="sm" variant="outline" onClick={() => setVitalsTarget(a)}>
                              <HeartPulse className="h-3.5 w-3.5" />
                              {t('appt.vitals')}
                            </Button>
                          )}
                          <span className="w-8">
                            <Menu items={menu} label={t('appt.more_actions')} />
                          </span>
                        </div>
                      </Td>
                    </Tr>
                  )
                })}
              </tbody>
            </Table>
            {visible.length > PAGE_SIZE && (
              <Pager
                offset={offset}
                limit={PAGE_SIZE}
                count={paged.length}
                total={visible.length}
                onChange={setOffset}
              />
            )}
          </>
        ) : (
          <EmptyState
            icon={CalendarX}
            title={ofDoctor.length > 0 ? t('appt.empty_filtered') : t('appt.empty_title')}
            description={ofDoctor.length > 0 ? undefined : t('appt.empty_desc')}
            action={
              canManage && ofDoctor.length === 0 ? (
                <Button size="sm" onClick={() => setModalOpen(true)}>
                  <Plus className="h-4 w-4" />
                  {t('appt.new')}
                </Button>
              ) : undefined
            }
          />
        )}
      </Card>

      <NewAppointmentModal open={modalOpen} onClose={() => setModalOpen(false)} date={date} />

      <AdjustFeeModal
        open={!!feeTarget}
        subtitle={feeTarget ? `${feeTarget.code} · ${feeTarget.patient_name ?? '—'}` : ''}
        listed={feeTarget?.listed_fee ?? null}
        charged={feeTarget?.fee ?? null}
        note={feeTarget?.fee_note ?? null}
        max={feeTarget?.type === 'vaccination' ? feeTarget.listed_fee : null}
        loading={adjustFee.isPending}
        onClose={() => setFeeTarget(null)}
        onSave={(amount, note) => adjustFee.mutate({ id: feeTarget!.id, amount, note })}
      />

      <RescheduleAppointmentModal
        appointment={rescheduleTarget}
        onClose={() => setRescheduleTarget(null)}
      />

      <Modal
        open={!!noShowTarget}
        onClose={() => setNoShowTarget(null)}
        title={t('appt.no_show_title')}
        width="max-w-md"
      >
        <div className="space-y-4 p-5">
          <p className="text-sm text-tx-2">{t('appt.no_show_confirm')}</p>
          {noShowTarget && (
            <div className="rounded-lg border border-line bg-surface-2/40 p-3 text-sm">
              <p className="font-medium text-tx">{noShowTarget.patient_name ?? '—'}</p>
              <p className="text-tx-3">
                {fmtTime(noShowTarget.scheduled_start)} · {noShowTarget.reason}
              </p>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setNoShowTarget(null)}>
              {t('app.back')}
            </Button>
            <Button
              variant="danger"
              loading={noShowAppt.isPending}
              onClick={() => noShowAppt.mutate(noShowTarget!.id)}
            >
              {t('appt.no_show')}
            </Button>
          </div>
        </div>
      </Modal>

      <VaccinationVisitModal target={visitTarget} onClose={() => setVisitTarget(null)} />

      <ConsultationVitalsModal appointment={vitalsTarget} onClose={() => setVitalsTarget(null)} />

      <Modal
        open={!!cancelTarget}
        onClose={() => setCancelTarget(null)}
        title={t('appt.cancel_title')}
        width="max-w-md"
      >
        <div className="space-y-4 p-5">
          <p className="text-sm text-tx-2">{t('appt.cancel_confirm')}</p>
          {cancelTarget && (
            <div className="rounded-lg border border-line bg-surface-2/40 p-3 text-sm">
              <p className="font-medium text-tx">{cancelTarget.patient_name ?? '—'}</p>
              <p className="text-tx-3">
                {fmtTime(cancelTarget.scheduled_start)} · {cancelTarget.reason}
              </p>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setCancelTarget(null)}>
              {t('app.back')}
            </Button>
            <Button
              variant="danger"
              loading={cancelAppt.isPending}
              onClick={() => cancelAppt.mutate(cancelTarget!.id)}
            >
              {t('appt.cancel_appt')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
