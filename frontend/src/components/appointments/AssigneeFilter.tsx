import type { BookingAgenda, BookingDoctor } from '@/api/appointments'
import { Select } from '@/components/ui/Input'
import { encodeAssignee } from '@/lib/assignee'
import { useT } from '@/lib/i18n'

/** List/agenda filter: all, one doctor or one service agenda (encoded assignee value). */
export function AssigneeFilter({
  value,
  onChange,
  doctors,
  agendas,
  className,
}: {
  value: string
  onChange: (value: string) => void
  doctors: BookingDoctor[]
  agendas: BookingAgenda[]
  className?: string
}) {
  const t = useT()
  return (
    <Select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={className}
      aria-label={t('sched.doctor')}
    >
      <option value="">
        {t(agendas.length > 0 ? 'sched.all_assignees' : 'sched.all_doctors')}
      </option>
      {doctors.map((d) => (
        <option key={d.id} value={encodeAssignee({ doctor_id: d.id })}>
          {d.name}
        </option>
      ))}
      {agendas.map((a) => (
        <option key={a.id} value={encodeAssignee({ agenda_id: a.id })}>
          {a.name}
        </option>
      ))}
    </Select>
  )
}
