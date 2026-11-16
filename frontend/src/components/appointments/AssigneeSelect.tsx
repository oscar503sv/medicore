import type { BookingAgenda, BookingDoctor } from '@/api/appointments'
import { Select } from '@/components/ui/Input'
import { encodeAssignee } from '@/lib/assignee'
import { useT } from '@/lib/i18n'
import { useAuthStore } from '@/stores/auth'

/**
 * Who attends: doctors; the clinic's service agendas too, but only for vaccination (the one
 * type an agenda takes). A doctor books only for themselves or an agenda, never for a colleague. The value is an encoded assignee (see lib/assignee).
 */
export function AssigneeSelect({
  value,
  onChange,
  doctors,
  agendas,
  withAgendas,
}: {
  value: string
  onChange: (value: string) => void
  doctors: BookingDoctor[]
  agendas: BookingAgenda[]
  /** True when the chosen type can go to an agenda. */
  withAgendas: boolean
}) {
  const t = useT()
  const me = useAuthStore((s) => s.session)
  const offered = withAgendas ? agendas : []
  const bookable = me?.role === 'doctor' ? doctors.filter((d) => d.id === me.user_id) : doctors
  return (
    <Select label={t('appt.attends')} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">—</option>
      {offered.length > 0 && (
        <option value="__doctors" disabled>
          {t('appt.attends_doctors')}
        </option>
      )}
      {bookable.map((d) => (
        <option key={d.id} value={encodeAssignee({ doctor_id: d.id })}>
          {d.name} {d.specialty ? `· ${d.specialty}` : ''}
        </option>
      ))}
      {offered.length > 0 && (
        <option value="__agendas" disabled>
          {t('appt.attends_agendas')}
        </option>
      )}
      {offered.map((a) => (
        <option key={a.id} value={encodeAssignee({ agenda_id: a.id })}>
          {a.name}
        </option>
      ))}
    </Select>
  )
}
