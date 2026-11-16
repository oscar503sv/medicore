import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BadgeDollarSign,
  CalendarDays,
  Check,
  Clock,
  ShieldCheck,
  Stethoscope,
  User as UserIcon,
} from 'lucide-react'
import { appointmentsApi } from '@/api/appointments'
import { errorMessage } from '@/api/client'
import { feesApi } from '@/api/fees'
import { insurersApi } from '@/api/insurers'
import { Button } from '@/components/ui/Button'
import { AppointmentTypeSelect } from '@/components/appointments/AppointmentTypeSelect'
import { AssigneeSelect } from '@/components/appointments/AssigneeSelect'
import { PatientPicker } from '@/components/appointments/PatientPicker'
import { SlotGrid } from '@/components/appointments/SlotGrid'
import { Input, Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { typeLabelKey } from '@/lib/appointmentTypes'
import { decodeAssignee, encodeAssignee } from '@/lib/assignee'
import { cn } from '@/lib/cn'
import { fmtFee } from '@/lib/fees'
import { clinicToday, fmtDate, fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import type { AppointmentType, Patient, Slot } from '@/types'

const STEPS = ['appt.step_patient', 'appt.step_details', 'appt.step_slot']

export function NewAppointmentModal({
  open,
  onClose,
  date,
  initialPatient,
  initialType,
  initialReason,
}: {
  open: boolean
  onClose: () => void
  date: string
  /** Booking from a patient's row: skip the patient step (and suggest their doctor). */
  initialPatient?: Patient | null
  /** Prefilled type and reason, e.g. a procedure's suggested follow-up. */
  initialType?: AppointmentType
  initialReason?: string
}) {
  const t = useT()
  const qc = useQueryClient()
  const me = useAuthStore((s) => s.session)
  const today = clinicToday()
  const [step, setStep] = useState(0)
  const [patient, setPatient] = useState<Patient | null>(null)
  const [assignee, setAssignee] = useState('')
  const [type, setType] = useState<AppointmentType>('consult')
  const [reason, setReason] = useState('')
  const [withInsurance, setWithInsurance] = useState(false)
  const [insuranceId, setInsuranceId] = useState('')
  const [day, setDay] = useState(date)
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null)

  // Keep the modal's calendar in sync with the day picked on the page when (re)opening.
  useEffect(() => {
    if (open) setDay(date)
  }, [open, date])

  useEffect(() => {
    if (!open || !initialPatient) return
    setPatient(initialPatient)
    // A doctor books for themselves; reception suggests the patient's own doctor.
    const suggested = me?.role === 'doctor' ? me.user_id : initialPatient.primary_doctor_id
    setAssignee(encodeAssignee({ doctor_id: suggested ?? undefined }))
    if (initialType) setType(initialType)
    if (initialReason) setReason(initialReason)
    setSelectedSlot(null)
    setStep(1)
  }, [open, initialPatient, initialType, initialReason, me])

  // Without a suggested patient, a doctor's own agenda is the default choice.
  useEffect(() => {
    if (open && !assignee && me?.role === 'doctor') {
      setAssignee(encodeAssignee({ doctor_id: me.user_id }))
    }
  }, [open, assignee, me])

  const { data: options } = useQuery({
    queryKey: ['booking-options'],
    queryFn: () => appointmentsApi.bookingOptions(),
    enabled: open,
  })
  const { data: fees } = useQuery({
    queryKey: ['fees'],
    queryFn: feesApi.list,
    enabled: open,
  })
  const { data: insurers } = useQuery({
    queryKey: ['insurers', 'active'],
    queryFn: () => insurersApi.list(true),
    enabled: open && withInsurance,
  })
  const { data: slots, isFetching: slotsLoading } = useQuery({
    queryKey: ['slots', assignee, day],
    queryFn: () => appointmentsApi.slots(decodeAssignee(assignee), day),
    enabled: open && step === 2 && !!assignee,
  })

  const { doctor_id: doctorId, agenda_id: agendaId } = decodeAssignee(assignee)
  const selectedDoctor = options?.doctors.find((d) => d.id === doctorId)
  const selectedAgenda = options?.agendas.find((a) => a.id === agendaId)
  // What the patient will be told it costs (the backend copies the same price on booking).
  const doctorFee = fees?.find((f) => f.doctor_id === doctorId)?.prices[type as AppointmentType]
  const feeLine =
    type === 'procedure'
      ? t('fee.booking_procedure')
      : type === 'vaccination'
        ? t('fee.booking_vaccination')
        : doctorFee
          ? t('fee.booking').replace('{price}', fmtFee(doctorFee)!)
          : t('fee.booking_none')
  const assigneeName = selectedDoctor?.name ?? selectedAgenda?.name
  // Appointment duration is the assignee's rule — shown, never chosen.
  const slotMinutes = selectedDoctor?.slot_minutes ?? selectedAgenda?.slot_minutes ?? null
  const isByCatalog = type === 'procedure' || type === 'vaccination'

  // An agenda only takes vaccinations: another type can't keep it.
  const changeType = (next: AppointmentType) => {
    setType(next)
    if (next !== 'vaccination' && agendaId) {
      setAssignee('')
      setSelectedSlot(null)
    }
  }

  const create = useMutation({
    mutationFn: () =>
      appointmentsApi.create({
        patient_id: patient!.id,
        ...decodeAssignee(assignee),
        location_id: selectedAgenda?.location_id ?? options!.locations[0].id,
        type,
        scheduled_start: selectedSlot!.start,
        reason,
        insurance_id: withInsurance ? insuranceId || null : null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      qc.invalidateQueries({ queryKey: ['slots'] })
      toast(t('appt.created_ok'))
      reset()
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  function reset() {
    setStep(0)
    setPatient(null)
    setAssignee('')
    setType('consult')
    setReason('')
    setWithInsurance(false)
    setInsuranceId('')
    setDay(date)
    setSelectedSlot(null)
  }

  const canNext =
    (step === 0 && patient) ||
    (step === 1 && assignee && reason && (!withInsurance || insuranceId))

  return (
    <Modal open={open} onClose={onClose} title={t('appt.new')} width="max-w-2xl">
      {/* Step indicator */}
      <div className="flex items-center gap-2 border-b border-line px-5 py-3">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <span
              className={cn(
                'flex h-6 w-6 items-center justify-center rounded-pill text-xs font-medium',
                i < step
                  ? 'bg-ok text-white'
                  : i === step
                    ? 'bg-accent text-white'
                    : 'bg-surface-2 text-tx-3',
              )}
            >
              {i < step ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </span>
            <span className={cn('text-[13px]', i === step ? 'text-tx' : 'text-tx-3')}>
              {t(s)}
            </span>
            {i < STEPS.length - 1 && <span className="mx-1 h-px w-6 bg-line" />}
          </div>
        ))}
      </div>

      <div className="min-h-[280px] p-5">
        {/* Step 1: patient */}
        {step === 0 && <PatientPicker selected={patient} onSelect={setPatient} />}

        {/* Step 2: details */}
        {step === 1 && (
          <div className="space-y-4">
            <AssigneeSelect
              value={assignee}
              onChange={(v) => {
                setAssignee(v)
                setSelectedSlot(null) // another assignee → previous pick is stale
              }}
              doctors={options?.doctors ?? []}
              agendas={options?.agendas ?? []}
              withAgendas={type === 'vaccination'}
            />
            <div className="grid grid-cols-2 gap-4">
              <AppointmentTypeSelect value={type} onChange={changeType} />
              {/* Duration is the doctor's rule — shown for context, never chosen here. */}
              <div>
                <span className="mb-1.5 block text-[13px] font-medium text-tx-2">
                  {t('appt.duration')}
                </span>
                <div className="flex h-10 items-center gap-2 rounded-lg border border-line bg-surface-2/40 px-3 text-sm text-tx">
                  <Clock className="h-3.5 w-3.5 text-tx-3" />
                  {slotMinutes !== null ? `${slotMinutes} min` : '—'}
                </div>
                <p className="mt-1 text-[11px] text-tx-4">{t(agendaId ? 'appt.duration_by_agenda' : 'appt.duration_by_doctor')}</p>
              </div>
            </div>
            {assignee && (
              <p
                className={cn(
                  'flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-[13px]',
                  doctorFee && !isByCatalog ? 'text-tx' : 'text-tx-3',
                )}
              >
                <BadgeDollarSign className="h-3.5 w-3.5 text-tx-3" />
                {feeLine}
              </p>
            )}
            <Input label={t('appt.reason')} value={reason} onChange={(e) => setReason(e.target.value)} />
            <div className="space-y-3 rounded-lg border border-line bg-surface-2/40 p-3">
              <label className="flex items-center gap-2 text-sm text-tx">
                <input
                  type="checkbox"
                  className="rounded border-line accent-accent"
                  checked={withInsurance}
                  onChange={(e) => {
                    setWithInsurance(e.target.checked)
                    if (!e.target.checked) setInsuranceId('')
                  }}
                />
                {t('appt.with_insurance')}
              </label>
              {withInsurance && (
                <Select
                  label={t('appt.insurer')}
                  value={insuranceId}
                  onChange={(e) => setInsuranceId(e.target.value)}
                >
                  <option value="">—</option>
                  {insurers?.map((ins) => (
                    <option key={ins.id} value={ins.id}>
                      {ins.name}
                    </option>
                  ))}
                </Select>
              )}
            </div>
          </div>
        )}

        {/* Step 3: date + slots + summary */}
        {step === 2 && (
          <div className="space-y-4">
            {/* Calendar */}
            <div className="flex flex-wrap items-end justify-between gap-3">
              <Input
                label={t('appt.date')}
                type="date"
                min={today}
                value={day}
                onChange={(e) => {
                  setDay(e.target.value)
                  setSelectedSlot(null) // new day → previous pick is stale
                }}
                className="w-44 font-mono"
              />
              <div className="flex items-center gap-3 pb-2 text-[11px] text-tx-3">
                <span className="flex items-center gap-1">
                  <span className="h-2.5 w-2.5 rounded-sm border border-accent bg-[var(--accent-10)]" />
                  {t('appt.slot_free')}
                </span>
                <span className="flex items-center gap-1">
                  <span className="h-2.5 w-2.5 rounded-sm bg-surface-2" />
                  {t('appt.slot_taken')}
                </span>
                <span className="flex items-center gap-1">
                  <span className="h-2.5 w-2.5 rounded-sm border border-line-soft bg-surface-2" />
                  {t('appt.slot_out')}
                </span>
              </div>
            </div>

            <SlotGrid
              slots={slots}
              isLoading={slotsLoading}
              selected={selectedSlot}
              onSelect={setSelectedSlot}
              offDayMessage={`${assigneeName ? `${assigneeName}: ` : ''}${t(
                agendaId ? 'appt.agenda_off_day' : 'appt.doctor_off_day',
              )}`}
            />

            {/* Summary */}
            <div className="rounded-lg border border-line bg-surface-2/40 p-3">
              <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-tx-3">
                {t('appt.summary')}
              </p>
              <div className="grid grid-cols-2 gap-y-2 text-[13px]">
                <span className="flex items-center gap-2 text-tx-3">
                  <UserIcon className="h-3.5 w-3.5" /> {t('appt.patient')}
                </span>
                <span className="text-right text-tx">
                  {patient ? `${patient.first_name} ${patient.last_name}` : '—'}
                </span>
                <span className="flex items-center gap-2 text-tx-3">
                  <Stethoscope className="h-3.5 w-3.5" /> {t('appt.attends')}
                </span>
                <span className="text-right text-tx">{assigneeName ?? '—'}</span>
                <span className="flex items-center gap-2 text-tx-3">
                  <CalendarDays className="h-3.5 w-3.5" /> {t('appt.type')}
                </span>
                <span className="text-right text-tx">{t(typeLabelKey(type))}</span>
                <span className="flex items-center gap-2 text-tx-3">
                  <BadgeDollarSign className="h-3.5 w-3.5" /> {t('fee.col_fee')}
                </span>
                <span className="text-right text-tx">
                  {type === 'procedure'
                    ? t('fee.by_procedure')
                    : type === 'vaccination'
                      ? t('fee.by_vaccination')
                      : (fmtFee(doctorFee) ?? t('fee.none'))}
                </span>
                <span className="flex items-center gap-2 text-tx-3">
                  <ShieldCheck className="h-3.5 w-3.5" /> {t('appt.insurer')}
                </span>
                <span className="text-right text-tx">
                  {withInsurance
                    ? (insurers?.find((i) => i.id === insuranceId)?.name ?? '—')
                    : t('appt.private')}
                </span>
                <span className="flex items-center gap-2 text-tx-3">
                  <Clock className="h-3.5 w-3.5" /> {t('appt.date')}
                </span>
                <span className="text-right font-mono text-tx">
                  {fmtDate(day, 'd MMM')}
                  {selectedSlot ? ` · ${fmtTime(selectedSlot.start)}` : ''}
                  {slotMinutes !== null && <span className="text-tx-4"> · {slotMinutes}m</span>}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex justify-between border-t border-line px-5 py-4">
        <Button variant="outline" onClick={() => (step === 0 ? onClose() : setStep(step - 1))}>
          {step === 0 ? t('app.cancel') : t('app.back')}
        </Button>
        {step < 2 ? (
          <Button disabled={!canNext} onClick={() => setStep(step + 1)}>
            {t('app.next')}
          </Button>
        ) : (
          <Button disabled={!selectedSlot} loading={create.isPending} onClick={() => create.mutate()}>
            {t('app.confirm')}
          </Button>
        )}
      </div>
    </Modal>
  )
}
