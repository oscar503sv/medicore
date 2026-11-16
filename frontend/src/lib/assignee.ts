import type { Appointment } from '@/types'

/** Who attends an appointment: a doctor or a service agenda, never both. */
export interface AssigneeRef {
  doctor_id?: string
  agenda_id?: string
}

type Assigned = Pick<Appointment, 'doctor_id' | 'agenda_id'>
type Named = Assigned & Pick<Appointment, 'doctor_name' | 'agenda_name'>

/** Select values and filters carry the assignee as one string: "d:<id>" or "a:<id>". */
export function encodeAssignee(ref: AssigneeRef): string {
  if (ref.doctor_id) return `d:${ref.doctor_id}`
  if (ref.agenda_id) return `a:${ref.agenda_id}`
  return ''
}

export function decodeAssignee(value: string): AssigneeRef {
  if (value.startsWith('d:')) return { doctor_id: value.slice(2) }
  if (value.startsWith('a:')) return { agenda_id: value.slice(2) }
  return {}
}

export const assigneeOf = (a: Assigned): AssigneeRef => ({
  ...(a.doctor_id ? { doctor_id: a.doctor_id } : {}),
  ...(a.agenda_id ? { agenda_id: a.agenda_id } : {}),
})

/** Stable id of whoever attends (doctor or agenda), e.g. a column key. */
export const assigneeKey = (a: Assigned): string => a.doctor_id ?? a.agenda_id ?? ''

/** An empty filter matches everything. */
export function matchesAssignee(a: Assigned, value: string): boolean {
  const ref = decodeAssignee(value)
  if (ref.doctor_id) return a.doctor_id === ref.doctor_id
  if (ref.agenda_id) return a.agenda_id === ref.agenda_id
  return true
}

/** Doctor's name, or the agenda's where there is no doctor. Names are only resolved in
 * listings; elsewhere a generic label keeps the cell from looking empty. */
export function assigneeName(a: Named, t: (key: string) => string): string {
  if (a.doctor_id) return a.doctor_name ?? '—'
  return a.agenda_name ?? (a.agenda_id ? t('agenda.generic') : '—')
}
