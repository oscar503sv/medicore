import { api } from './client'
import type { Appointment, Location, Slot, User } from '@/types'

export interface BookingDoctor extends User {
  /** Appointment duration imposed by the doctor's booking rules (null → not configured). */
  slot_minutes: number | null
}

export interface BookingOptions {
  doctors: BookingDoctor[]
  locations: Location[]
}

// Duration is never sent — the backend derives it from the doctor's booking rules.
export interface CreateAppointmentPayload {
  patient_id: string
  doctor_id: string
  location_id: string
  type: string
  scheduled_start: string
  reason: string
  room?: string | null
  insurance_id?: string | null
}

export const appointmentsApi = {
  bookingOptions: () =>
    api.get<BookingOptions>('/appointments/booking-options').then((r) => r.data),

  listForDay: (on: string, doctorId?: string) =>
    api
      .get<Appointment[]>('/appointments', { params: { on, doctor_id: doctorId } })
      .then((r) => r.data),

  weeklySchedule: (weekStart: string, doctorId?: string) =>
    api
      .get<{ schedule: Record<string, Appointment[]> }>('/appointments/schedule', {
        params: { week_start: weekStart, doctor_id: doctorId },
      })
      .then((r) => r.data.schedule),

  slots: (doctorId: string, on: string) =>
    api
      .get<Slot[]>('/appointments/slots', {
        params: { doctor_id: doctorId, on },
      })
      .then((r) => r.data),

  create: (payload: CreateAppointmentPayload) =>
    api.post<Appointment>('/appointments', payload).then((r) => r.data),

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
