import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarCheck, CalendarClock, Check, CheckCheck, Clock, Plus, Search, Stethoscope, X } from 'lucide-react'
import { appointmentsApi } from '@/api/appointments'
import { consultationsApi } from '@/api/consultations'
import { errorMessage } from '@/api/client'
import { NewAppointmentModal } from '@/components/appointments/NewAppointmentModal'
import { RescheduleAppointmentModal } from '@/components/appointments/RescheduleAppointmentModal'
import { PageHeader } from '@/components/PageHeader'
import { StatCard } from '@/components/StatCard'
import { Badge } from '@/components/ui/Badge'
import { statusTone, typeTone } from '@/components/ui/badgeTone'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Modal } from '@/components/ui/Modal'
import { Pager, PAGE_SIZE } from '@/components/ui/Pager'
import { Segmented } from '@/components/ui/Segmented'
import { PageLoader } from '@/components/ui/Spinner'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { toast } from '@/components/ui/Toast'
import { clinicToday, fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import type { Appointment, AppointmentStatus } from '@/types'

export function AppointmentsPage() {
  const t = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const canConsult = useAuthStore((s) => s.can('consultations.start'))
  const canManage = useAuthStore((s) => s.can('appointments.manage'))
  const [date, setDate] = useState(clinicToday())
  const [modalOpen, setModalOpen] = useState(false)
  const [cancelTarget, setCancelTarget] = useState<Appointment | null>(null)
  const [rescheduleTarget, setRescheduleTarget] = useState<Appointment | null>(null)
  const [statusFilter, setStatusFilter] = useState<'all' | AppointmentStatus>('all')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)

  const { data, isLoading } = useQuery({
    queryKey: ['appointments', 'day', date],
    queryFn: () => appointmentsApi.listForDay(date),
  })

  const all = data ?? []
  const countBy = (s: AppointmentStatus) => all.filter((a) => a.status === s).length
  const term = q.trim().toLowerCase()
  const visible = all.filter(
    (a) =>
      (statusFilter === 'all' || a.status === statusFilter) &&
      (!term ||
        (a.patient_name ?? '').toLowerCase().includes(term) ||
        a.reason.toLowerCase().includes(term)),
  )
  const paged = visible.slice(offset, offset + PAGE_SIZE)

  const startConsult = useMutation({
    mutationFn: (appointmentId: string) => consultationsApi.start(appointmentId),
    onSuccess: (consultation) => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      navigate(`/consultation/${consultation.id}`)
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const confirmAppt = useMutation({
    mutationFn: (appointmentId: string) => appointmentsApi.confirm(appointmentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      toast(t('appt.confirmed_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  const cancelAppt = useMutation({
    mutationFn: (appointmentId: string) => appointmentsApi.cancel(appointmentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      qc.invalidateQueries({ queryKey: ['slots'] })
      setCancelTarget(null)
      toast(t('appt.cancelled_ok'))
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <div className="space-y-5 p-8">
      <PageHeader
        title={t('appt.title')}
        action={
          canManage ? (
            <Button onClick={() => setModalOpen(true)}>
              <Plus className="h-4 w-4" />
              {t('appt.new')}
            </Button>
          ) : undefined
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard icon={CalendarCheck} label={t('appt.stat_total')} value={String(all.length)} />
        <StatCard icon={Clock} label={t('appt.stat_scheduled')} value={String(countBy('scheduled'))} />
        <StatCard icon={Check} label={t('appt.stat_confirmed')} value={String(countBy('confirmed'))} />
        <StatCard icon={CheckCheck} label={t('appt.stat_completed')} value={String(countBy('completed'))} />
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <input
            type="date"
            value={date}
            onChange={(e) => {
              setDate(e.target.value)
              setOffset(0)
            }}
            className="h-10 rounded-lg border border-line bg-bg px-3 text-sm text-tx focus:border-accent focus:outline-none"
          />
          <div className="relative w-72">
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
        </div>
        <Segmented
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v)
            setOffset(0)
          }}
          options={[
            { value: 'all', label: t('app.all') },
            { value: 'scheduled', label: t('status.scheduled') },
            { value: 'confirmed', label: t('status.confirmed') },
            { value: 'in_progress', label: t('status.in_progress') },
            { value: 'completed', label: t('status.completed') },
            { value: 'cancelled', label: t('status.cancelled') },
          ]}
        />
      </div>

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
                <Th>{t('appt.col_doctor')}</Th>
                <Th>{t('appt.col_reason')}</Th>
                <Th>{t('appt.col_type')}</Th>
                <Th>{t('appt.col_status')}</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {paged.map((a) => (
                <Tr key={a.id}>
                  <Td>
                    <span className="font-mono text-tx">{fmtTime(a.scheduled_start)}</span>
                    <span className="text-tx-4"> · {a.duration_minutes}m</span>
                  </Td>
                  <Td>
                    <p className="font-medium text-tx">{a.patient_name ?? '—'}</p>
                    <p className="font-mono text-xs text-tx-3">{a.code}</p>
                  </Td>
                  <Td>{a.doctor_name ?? '—'}</Td>
                  <Td>{a.reason}</Td>
                  <Td>
                    <Badge tone={typeTone(a.type)}>{t(`apptype.${a.type}`)}</Badge>
                  </Td>
                  <Td>
                    <Badge tone={statusTone(a.status)}>{t(`status.${a.status}`)}</Badge>
                  </Td>
                  <Td className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      {canManage && a.status === 'scheduled' && (
                        <Button
                          size="sm"
                          variant="outline"
                          loading={confirmAppt.isPending}
                          onClick={() => confirmAppt.mutate(a.id)}
                        >
                          <Check className="h-3.5 w-3.5" />
                          {t('appt.confirm_appt')}
                        </Button>
                      )}
                      {/* Start consultation only once the appointment is confirmed. */}
                      {canConsult && a.status === 'confirmed' && (
                        <Button
                          size="sm"
                          variant="outline"
                          loading={startConsult.isPending}
                          onClick={() => startConsult.mutate(a.id)}
                        >
                          <Stethoscope className="h-3.5 w-3.5" />
                          {t('appt.start_consult')}
                        </Button>
                      )}
                      {a.status === 'in_progress' && canConsult && (
                        <Button size="sm" variant="subtle" onClick={() => startConsult.mutate(a.id)}>
                          {t('appt.continue')}
                        </Button>
                      )}
                      {canManage && (a.status === 'scheduled' || a.status === 'confirmed') && (
                        <>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setRescheduleTarget(a)}
                            title={t('appt.reschedule')}
                          >
                            <CalendarClock className="h-3.5 w-3.5" />
                            {t('appt.reschedule')}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setCancelTarget(a)}
                            title={t('appt.cancel_appt')}
                          >
                            <X className="h-3.5 w-3.5" />
                            {t('app.cancel')}
                          </Button>
                        </>
                      )}
                    </div>
                  </Td>
                </Tr>
              ))}
            </tbody>
            </Table>
            {visible.length > PAGE_SIZE && (
              <Pager offset={offset} limit={PAGE_SIZE} count={paged.length} total={visible.length} onChange={setOffset} />
            )}
          </>
        ) : (
          <EmptyState title="Sin citas" description="No hay citas para esta fecha." />
        )}
      </Card>

      <NewAppointmentModal open={modalOpen} onClose={() => setModalOpen(false)} date={date} />

      <RescheduleAppointmentModal
        appointment={rescheduleTarget}
        onClose={() => setRescheduleTarget(null)}
      />

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
