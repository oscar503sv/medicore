import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { appointmentsApi } from '@/api/appointments'
import { errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { clinicToday, fmtTime } from '@/lib/format'
import { useT } from '@/lib/i18n'
import type { Appointment, Slot } from '@/types'

export function RescheduleAppointmentModal({
  appointment,
  onClose,
}: {
  appointment: Appointment | null
  onClose: () => void
}) {
  const t = useT()
  const qc = useQueryClient()
  const today = clinicToday()
  const [day, setDay] = useState(today)
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null)

  // Seed the calendar with the appointment's current day whenever a new target opens.
  useEffect(() => {
    if (appointment) {
      setDay(appointment.scheduled_start.slice(0, 10))
      setSelectedSlot(null)
    }
  }, [appointment])

  const open = !!appointment
  const doctorId = appointment?.doctor_id ?? ''
  const duration = appointment?.duration_minutes ?? 30

  const { data: slots, isFetching: slotsLoading } = useQuery({
    queryKey: ['slots', doctorId, day, duration],
    queryFn: () => appointmentsApi.slots(doctorId, day, duration),
    enabled: open && !!doctorId,
  })

  const doctorOffThatDay =
    !!slots && slots.length > 0 && slots.every((s) => s.status === 'out_of_hours')

  const reschedule = useMutation({
    mutationFn: () => appointmentsApi.reschedule(appointment!.id, selectedSlot!.start, duration),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      qc.invalidateQueries({ queryKey: ['slots'] })
      qc.invalidateQueries({ queryKey: ['schedule'] })
      toast(t('appt.reschedule_ok'))
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={open} onClose={onClose} title={t('appt.reschedule_title')} width="max-w-xl">
      <div className="space-y-4 p-5">
        {appointment && (
          <div className="rounded-lg border border-line bg-surface-2/40 p-3 text-sm">
            <p className="font-medium text-tx">{appointment.patient_name ?? '—'}</p>
            <p className="text-tx-3">
              {t('appt.reschedule_current')}: {fmtTime(appointment.scheduled_start)} · {duration}m
            </p>
          </div>
        )}

        <Input
          label={t('appt.date')}
          type="date"
          min={today}
          value={day}
          onChange={(e) => {
            setDay(e.target.value)
            setSelectedSlot(null)
          }}
          className="w-44 font-mono"
        />

        {slotsLoading ? (
          <p className="py-10 text-center text-sm text-tx-3">…</p>
        ) : doctorOffThatDay ? (
          <p className="py-10 text-center text-sm text-tx-3">{t('appt.doctor_off_day')}</p>
        ) : slots && slots.length > 0 ? (
          <div className="grid max-h-[240px] grid-cols-4 gap-2 overflow-y-auto pr-1">
            {slots.map((slot) => {
              const isFree = slot.status === 'free'
              const isSelected = selectedSlot?.start === slot.start
              return (
                <button
                  key={slot.start}
                  type="button"
                  disabled={!isFree}
                  onClick={() => setSelectedSlot(slot)}
                  className={cn(
                    'rounded-lg border py-2 font-mono text-[13px] transition-colors',
                    isFree && isSelected && 'border-accent bg-accent text-white shadow-sm',
                    isFree &&
                      !isSelected &&
                      'border-accent bg-[var(--accent-10)] text-tx hover:bg-accent hover:text-white',
                    slot.status === 'taken' && 'border-line-soft text-tx-4 line-through',
                    (slot.status === 'out_of_hours' || slot.status === 'blocked_rules') &&
                      'cursor-not-allowed border-line-soft bg-surface-2 text-tx-4',
                  )}
                  title={t(
                    slot.status === 'blocked_rules' ? 'appt.slot_blocked' : `appt.slot_${slot.status}`,
                  )}
                >
                  {fmtTime(slot.start)}
                </button>
              )
            })}
          </div>
        ) : (
          <p className="py-10 text-center text-sm text-tx-3">{t('appt.no_slots')}</p>
        )}
      </div>

      <div className="flex justify-between border-t border-line px-5 py-4">
        <Button variant="outline" onClick={onClose}>
          {t('app.cancel')}
        </Button>
        <Button
          disabled={!selectedSlot}
          loading={reschedule.isPending}
          onClick={() => reschedule.mutate()}
        >
          {t('appt.reschedule')}
        </Button>
      </div>
    </Modal>
  )
}
