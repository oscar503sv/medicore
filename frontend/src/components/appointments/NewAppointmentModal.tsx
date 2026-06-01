import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { appointmentsApi } from '@/api/appointments'
import { errorMessage } from '@/api/client'
import { patientsApi } from '@/api/patients'
import { Button } from '@/components/ui/Button'
import { Input, Select } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { Patient, Slot } from '@/types'

const STEPS = ['appt.step_patient', 'appt.step_details', 'appt.step_slot']

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
  const [step, setStep] = useState(0)
  const [patient, setPatient] = useState<Patient | null>(null)
  const [doctorId, setDoctorId] = useState('')
  const [type, setType] = useState('consult')
  const [duration, setDuration] = useState(30)
  const [reason, setReason] = useState('')
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null)
  const [search, setSearch] = useState('')

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
  const { data: slots } = useQuery({
    queryKey: ['slots', doctorId, date],
    queryFn: () => appointmentsApi.slots(doctorId, date),
    enabled: open && step === 2 && !!doctorId,
  })

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
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
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
    setReason('')
    setSelectedSlot(null)
    setSearch('')
  }

  const canNext = (step === 0 && patient) || (step === 1 && doctorId && reason)

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
                <option value="consult">Consulta</option>
                <option value="follow_up">Seguimiento</option>
                <option value="check_up">Control</option>
                <option value="procedure">Procedimiento</option>
              </Select>
              <Select
                label={t('appt.duration')}
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
              >
                <option value={15}>15 min</option>
                <option value={30}>30 min</option>
                <option value={45}>45 min</option>
                <option value={60}>60 min</option>
              </Select>
            </div>
            <Input label={t('appt.reason')} value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        )}

        {/* Step 3: slot */}
        {step === 2 && (
          <div>
            <p className="mb-3 text-[13px] text-tx-3">
              {t('appt.date')}: <span className="font-mono text-tx">{date}</span>
            </p>
            <div className="grid grid-cols-4 gap-2">
              {slots?.map((slot) => {
                const disabled = slot.status !== 'free'
                return (
                  <button
                    key={slot.start}
                    disabled={disabled}
                    onClick={() => setSelectedSlot(slot)}
                    className={cn(
                      'rounded-lg border py-2 text-[13px] font-mono transition-colors',
                      slot.status === 'free' &&
                        selectedSlot?.start === slot.start &&
                        'border-accent bg-accent text-white',
                      slot.status === 'free' &&
                        selectedSlot?.start !== slot.start &&
                        'border-line hover:border-accent text-tx',
                      slot.status === 'taken' && 'border-line-soft text-tx-4 line-through',
                      slot.status === 'out_of_hours' &&
                        'border-line-soft bg-surface-2 text-tx-4 cursor-not-allowed',
                    )}
                    title={t(`appt.slot_${slot.status === 'out_of_hours' ? 'out' : slot.status}`)}
                  >
                    {fmtTime(slot.start)}
                  </button>
                )
              })}
              {slots?.length === 0 && (
                <p className="col-span-4 py-6 text-center text-sm text-tx-3">
                  Sin disponibilidad este día
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex justify-between border-t border-line px-5 py-4">
        <Button variant="ghost" onClick={() => (step === 0 ? onClose() : setStep(step - 1))}>
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
