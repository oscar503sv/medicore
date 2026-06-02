import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { CalendarDays, Check, Clock, ShieldCheck, Stethoscope, User as UserIcon } from 'lucide-react'
import { appointmentsApi } from '@/api/appointments'
import { errorMessage } from '@/api/client'
import { insurersApi } from '@/api/insurers'
import { patientsApi } from '@/api/patients'
import { Button } from '@/components/ui/Button'
import { Input, Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { fmtDate, fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { Patient, Slot } from '@/types'

const STEPS = ['appt.step_patient', 'appt.step_details', 'appt.step_slot']

const TYPE_LABELS: Record<string, string> = {
  consult: 'Consulta',
  follow_up: 'Seguimiento',
  check_up: 'Control',
  procedure: 'Procedimiento',
}

export function NewAppointmentModal({
  open,
  onClose,
  date,
}: {
  open: boolean
  onClose: () => void
  date: string
}) {
  const t = useT()
  const qc = useQueryClient()
  const today = format(new Date(), 'yyyy-MM-dd')
  const [step, setStep] = useState(0)
  const [patient, setPatient] = useState<Patient | null>(null)
  const [doctorId, setDoctorId] = useState('')
  const [type, setType] = useState('consult')
  const [duration, setDuration] = useState(30)
  const [reason, setReason] = useState('')
  const [withInsurance, setWithInsurance] = useState(false)
  const [insuranceId, setInsuranceId] = useState('')
  const [day, setDay] = useState(date)
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null)
  const [search, setSearch] = useState('')

  // Keep the modal's calendar in sync with the day picked on the page when (re)opening.
  useEffect(() => {
    if (open) setDay(date)
  }, [open, date])

  const { data: patients } = useQuery({
    queryKey: ['patients', { q: search }],
    queryFn: () => patientsApi.list({ q: search || undefined, limit: 8 }),
    enabled: open && step === 0,
  })
  const { data: options } = useQuery({
    queryKey: ['booking-options'],
    queryFn: () => appointmentsApi.bookingOptions(),
    enabled: open,
  })
  const { data: insurers } = useQuery({
    queryKey: ['insurers', 'active'],
    queryFn: () => insurersApi.list(true),
    enabled: open && withInsurance,
  })
  const { data: slots, isFetching: slotsLoading } = useQuery({
    queryKey: ['slots', doctorId, day, duration],
    queryFn: () => appointmentsApi.slots(doctorId, day, duration),
    enabled: open && step === 2 && !!doctorId,
  })

  // The doctor isn't available at all that day (off exception or non-working weekday):
  // every candidate in the fixed grid came back out_of_hours.
  const doctorOffThatDay =
    !!slots && slots.length > 0 && slots.every((s) => s.status === 'out_of_hours')
  const doctorName = options?.doctors.find((d) => d.id === doctorId)?.name

  const create = useMutation({
    mutationFn: () =>
      appointmentsApi.create({
        patient_id: patient!.id,
        doctor_id: doctorId,
        location_id: options!.locations[0].id,
        type,
        scheduled_start: selectedSlot!.start,
        duration_minutes: duration,
        reason,
        insurance_id: withInsurance ? insuranceId || null : null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      qc.invalidateQueries({ queryKey: ['slots'] })
      toast('Cita agendada')
      reset()
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  function reset() {
    setStep(0)
    setPatient(null)
    setDoctorId('')
    setType('consult')
    setDuration(30)
    setReason('')
    setWithInsurance(false)
    setInsuranceId('')
    setDay(date)
    setSelectedSlot(null)
    setSearch('')
  }

  const canNext =
    (step === 0 && patient) ||
    (step === 1 && doctorId && reason && (!withInsurance || insuranceId))

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
        {step === 0 && (
          <div className="space-y-3">
            <Input
              placeholder={t('appt.select_patient')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoFocus
            />
            <div className="max-h-60 space-y-1 overflow-y-auto">
              {patients?.items.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setPatient(p)}
                  className={cn(
                    'flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-left transition-colors',
                    patient?.id === p.id
                      ? 'border-accent bg-[var(--accent-10)]'
                      : 'border-line hover:bg-surface-2',
                  )}
                >
                  <div>
                    <p className="text-sm font-medium text-tx">
                      {p.first_name} {p.last_name}
                    </p>
                    <p className="font-mono text-xs text-tx-3">{p.code}</p>
                  </div>
                  {patient?.id === p.id && <Check className="h-4 w-4 text-accent" />}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 2: details */}
        {step === 1 && (
          <div className="space-y-4">
            <Select label={t('appt.col_doctor')} value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
              <option value="">—</option>
              {options?.doctors.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} {d.specialty ? `· ${d.specialty}` : ''}
                </option>
              ))}
            </Select>
            <div className="grid grid-cols-2 gap-4">
              <Select label={t('appt.type')} value={type} onChange={(e) => setType(e.target.value)}>
                {Object.entries(TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
              <Select
                label={t('appt.duration')}
                value={duration}
                onChange={(e) => {
                  setDuration(Number(e.target.value))
                  setSelectedSlot(null) // slot length changed → previous pick is stale
                }}
              >
                <option value={15}>15 min</option>
                <option value={30}>30 min</option>
                <option value={45}>45 min</option>
                <option value={60}>60 min</option>
              </Select>
            </div>
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

            {/* Slots */}
            {slotsLoading ? (
              <p className="py-10 text-center text-sm text-tx-3">…</p>
            ) : doctorOffThatDay ? (
              <p className="py-10 text-center text-sm text-tx-3">
                {doctorName ? `${doctorName}: ` : ''}
                {t('appt.doctor_off_day')}
              </p>
            ) : slots && slots.length > 0 ? (
              <div className="grid max-h-[240px] grid-cols-4 gap-2 overflow-y-auto pr-1">
                {slots.map((slot) => {
                  const isFree = slot.status === 'free'
                  const isSelected = selectedSlot?.start === slot.start
                  const titleKey =
                    slot.status === 'out_of_hours'
                      ? 'appt.slot_out'
                      : slot.status === 'blocked_rules'
                        ? 'appt.slot_blocked'
                        : `appt.slot_${slot.status}`
                  return (
                    <button
                      key={slot.start}
                      type="button"
                      disabled={!isFree}
                      onClick={() => setSelectedSlot(slot)}
                      className={cn(
                        'rounded-lg border py-2 text-[13px] font-mono transition-colors',
                        isFree &&
                          isSelected &&
                          'border-accent bg-accent text-white shadow-sm',
                        isFree &&
                          !isSelected &&
                          'border-accent bg-[var(--accent-10)] text-tx hover:bg-accent hover:text-white',
                        slot.status === 'taken' && 'border-line-soft text-tx-4 line-through',
                        (slot.status === 'out_of_hours' || slot.status === 'blocked_rules') &&
                          'cursor-not-allowed border-line-soft bg-surface-2 text-tx-4',
                      )}
                      title={t(titleKey)}
                    >
                      {fmtTime(slot.start)}
                    </button>
                  )
                })}
              </div>
            ) : (
              <p className="py-10 text-center text-sm text-tx-3">{t('appt.no_slots')}</p>
            )}

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
                  <Stethoscope className="h-3.5 w-3.5" /> {t('appt.col_doctor')}
                </span>
                <span className="text-right text-tx">{doctorName ?? '—'}</span>
                <span className="flex items-center gap-2 text-tx-3">
                  <CalendarDays className="h-3.5 w-3.5" /> {t('appt.type')}
                </span>
                <span className="text-right text-tx">{TYPE_LABELS[type] ?? type}</span>
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
                  <span className="text-tx-4"> · {duration}m</span>
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
