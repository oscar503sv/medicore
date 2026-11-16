import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { appointmentsApi } from '@/api/appointments'
import { errorMessage } from '@/api/client'
import { SlotGrid } from '@/components/appointments/SlotGrid'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { assigneeOf, encodeAssignee } from '@/lib/assignee'
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
  const assignee = appointment ? assigneeOf(appointment) : {}
  const hasAssignee = !!appointment && !!(appointment.doctor_id ?? appointment.agenda_id)

  const { data: slots, isFetching: slotsLoading } = useQuery({
    queryKey: ['slots', encodeAssignee(assignee), day],
    queryFn: () => appointmentsApi.slots(assignee, day),
    enabled: open && hasAssignee,
  })

  // The new duration is decided by the backend from the doctor's current rules.
  const reschedule = useMutation({
    mutationFn: () => appointmentsApi.reschedule(appointment!.id, selectedSlot!.start),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      qc.invalidateQueries({ queryKey: ['slots'] })
      qc.invalidateQueries({ queryKey: ['schedule'] })
      toast(t('appt.reschedule_ok'))
      onClose()
    },
    onError: (err) => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      toast(errorMessage(err), 'danger')
    },
  })

  return (
    <Modal open={open} onClose={onClose} title={t('appt.reschedule_title')} width="max-w-xl">
      <div className="space-y-4 p-5">
        {appointment && (
          <div className="rounded-lg border border-line bg-surface-2/40 p-3 text-sm">
            <p className="font-medium text-tx">{appointment.patient_name ?? '—'}</p>
            <p className="text-tx-3">
              {t('appt.reschedule_current')}: {fmtTime(appointment.scheduled_start)} ·{' '}
              {appointment.duration_minutes}m
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

        <SlotGrid
          slots={slots}
          isLoading={slotsLoading}
          selected={selectedSlot}
          onSelect={setSelectedSlot}
          offDayMessage={t(appointment?.agenda_id ? 'appt.agenda_off_day' : 'appt.doctor_off_day')}
        />
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
