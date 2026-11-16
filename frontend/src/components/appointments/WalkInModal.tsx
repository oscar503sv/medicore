import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BadgeDollarSign, Info } from 'lucide-react'
import { appointmentsApi } from '@/api/appointments'
import { errorMessage } from '@/api/client'
import { feesApi } from '@/api/fees'
import { AppointmentTypeSelect } from '@/components/appointments/AppointmentTypeSelect'
import { AssigneeSelect } from '@/components/appointments/AssigneeSelect'
import { PatientPicker } from '@/components/appointments/PatientPicker'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { toast } from '@/components/ui/Toast'
import { decodeAssignee, encodeAssignee } from '@/lib/assignee'
import { fmtFee } from '@/lib/fees'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'
import type { AppointmentType, Patient } from '@/types'

export function WalkInModal({
  open,
  onClose,
  patient: fixedPatient,
}: {
  open: boolean
  onClose: () => void
  /** Already known (opened from the patient's page): no picker. */
  patient?: Patient
}) {
  const t = useT()
  const qc = useQueryClient()
  const me = useAuthStore((s) => s.session)
  const [picked, setPicked] = useState<Patient | null>(null)
  const [assignee, setAssignee] = useState('')
  const [type, setType] = useState<AppointmentType>('emergency')
  const [reason, setReason] = useState('')
  const patient = fixedPatient ?? picked

  const { data: options } = useQuery({
    queryKey: ['booking-options'],
    queryFn: () => appointmentsApi.bookingOptions(),
    enabled: open,
  })
  const { data: fees } = useQuery({ queryKey: ['fees'], queryFn: feesApi.list, enabled: open })

  // The doctor registering is the one who sees the patient; otherwise their own doctor.
  useEffect(() => {
    if (!open || assignee) return
    const isDoctor = options?.doctors.some((d) => d.id === me?.user_id)
    setAssignee(
      encodeAssignee({ doctor_id: (isDoctor ? me?.user_id : patient?.primary_doctor_id) || undefined }),
    )
  }, [open, assignee, options, me, patient])

  const { doctor_id: doctorId, agenda_id: agendaId } = decodeAssignee(assignee)
  const price = fees?.find((f) => f.doctor_id === doctorId)?.prices[type]
  const feeLine =
    type === 'procedure'
      ? t('fee.booking_procedure')
      : type === 'vaccination'
        ? t('fee.booking_vaccination')
        : price
        ? t('fee.booking').replace('{price}', fmtFee(price)!)
        : t('fee.booking_none')

  const register = useMutation({
    mutationFn: () =>
      appointmentsApi.walkIn({ patient_id: patient!.id, ...decodeAssignee(assignee), type, reason }),
    onSuccess: () => {
      for (const key of ['appointments', 'dashboard', 'slots']) {
        qc.invalidateQueries({ queryKey: [key] })
      }
      toast(t('appt.walk_in_ok'))
      setPicked(null)
      setAssignee('')
      setType('emergency')
      setReason('')
      onClose()
    },
    onError: (err) => toast(errorMessage(err), 'danger'),
  })

  return (
    <Modal open={open} onClose={onClose} title={t('appt.walk_in_title')} width="max-w-lg">
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          register.mutate()
        }}
      >
        <p className="flex items-start gap-2 rounded-lg bg-surface-2/60 px-3 py-2 text-[13px] text-tx-2">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-tx-3" />
          {t('appt.walk_in_hint')}
        </p>
        {fixedPatient ? (
          <p className="text-sm font-medium text-tx">
            {fixedPatient.first_name} {fixedPatient.last_name}
          </p>
        ) : (
          <PatientPicker selected={picked} onSelect={setPicked} />
        )}
        <AssigneeSelect
          value={assignee}
          onChange={setAssignee}
          doctors={options?.doctors ?? []}
          agendas={options?.agendas ?? []}
          withAgendas={type === 'vaccination'}
        />
        <AppointmentTypeSelect
          value={type}
          onChange={(next) => {
            setType(next)
            // An agenda only takes vaccinations.
            if (next !== 'vaccination' && agendaId) setAssignee('')
          }}
        />
        <Input
          label={t('appt.reason')}
          value={reason}
          maxLength={500}
          required
          onChange={(e) => setReason(e.target.value)}
        />
        {assignee && (
          <p className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-[13px] text-tx-3">
            <BadgeDollarSign className="h-3.5 w-3.5" />
            {feeLine}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('app.cancel')}
          </Button>
          <Button
            type="submit"
            loading={register.isPending}
            disabled={!patient || !assignee || !reason.trim()}
          >
            {t('appt.walk_in_cta')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
