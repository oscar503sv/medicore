import { api } from './client'
import type { AssigneeRef } from '@/lib/assignee'
import type { ServiceAgendaKind } from './serviceAgendas'
import type { Appointment, AppointmentVitals, Location, Slot, User, Vitals } from '@/types'

export interface BookingDoctor extends User {
  /** Appointment duration imposed by the doctor's booking rules (null → not configured). */
  slot_minutes: number | null
}

/** An active service agenda that can take appointments (only with its module contracted). */
export interface BookingAgenda {
  id: string
  name: string
  kind: ServiceAgendaKind
  location_id: string | null
  slot_minutes: number | null
}

export interface BookingOptions {
  doctors: BookingDoctor[]
  agendas: BookingAgenda[]
  locations: Location[]
}

// Duration is never sent — the backend derives it from the doctor's booking rules.
export interface CreateAppointmentPayload extends AssigneeRef {
  patient_id: string
  location_id: string
  type: string
  scheduled_start: string
  reason: string
  room?: string | null
  insurance_id?: string | null
}

export interface WalkInPayload extends AssigneeRef {
  patient_id: string
  type: string
  reason: string
  location_id?: string | null
  insurance_id?: string | null
}

export const appointmentsApi = {
  bookingOptions: () =>
    api.get<BookingOptions>('/appointments/booking-options').then((r) => r.data),

  /** Next scheduled/confirmed appointments from now on, across days (doctors: their own). */
  upcoming: (limit = 6) =>
    api.get<Appointment[]>('/appointments/upcoming', { params: { limit } }).then((r) => r.data),

  listForDay: (on: string, assignee: AssigneeRef = {}) =>
    api.get<Appointment[]>('/appointments', { params: { on, ...assignee } }).then((r) => r.data),

  weeklySchedule: (weekStart: string, assignee: AssigneeRef = {}) =>
    api
      .get<{ schedule: Record<string, Appointment[]> }>('/appointments/schedule', {
        params: { week_start: weekStart, ...assignee },
      })
      .then((r) => r.data.schedule),

  /** Exactly one of doctor_id / agenda_id. */
  slots: (assignee: AssigneeRef, on: string) =>
    api.get<Slot[]>('/appointments/slots', { params: { ...assignee, on } }).then((r) => r.data),

  create: (payload: CreateAppointmentPayload) =>
    api.post<Appointment>('/appointments', payload).then((r) => r.data),

  /** A patient seen right now: starts at the clinic's current minute, no slot involved. */
  walkIn: (payload: WalkInPayload) =>
    api.post<Appointment>('/appointments/walk-in', payload).then((r) => r.data),

  /** Nursing's entry point: the waiting-room vitals, or the consultation's once it started. */
  vitals: (id: string) =>
    api.get<AppointmentVitals>(`/appointments/${id}/vitals`).then((r) => r.data),

  /** Only the fields present change; null clears one. */
  updateVitals: (id: string, changes: Partial<Vitals>) =>
    api.put<AppointmentVitals>(`/appointments/${id}/vitals`, changes).then((r) => r.data),

  adjustFee: (id: string, amount: string, note: string | null) =>
    api.put<Appointment>(`/appointments/${id}/fee`, { amount, note }).then((r) => r.data),

  reschedule: (id: string, newStart: string) =>
    api
      .put<Appointment>(`/appointments/${id}/reschedule`, { new_start: newStart })
      .then((r) => r.data),

  confirm: (id: string) =>
    api.post<Appointment>(`/appointments/${id}/confirm`).then((r) => r.data),

  cancel: (id: string) =>
    api.post<Appointment>(`/appointments/${id}/cancel`).then((r) => r.data),

  noShow: (id: string) =>
    api.post<Appointment>(`/appointments/${id}/no-show`).then((r) => r.data),
}
