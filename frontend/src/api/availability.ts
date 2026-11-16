import { api } from './client'
import type { Availability, BookingRules, Slot, TimeRange, WeeklyDay } from '@/types'

export interface ExceptionPayload {
  date: string
  kind: string
  reason?: string
  blocks?: TimeRange[]
}

/** The schedule editor works on either the caller's own availability or a service agenda's. */
export interface AvailabilityScope {
  get: () => Promise<Availability>
  updateWeekly: (weekly: WeeklyDay[]) => Promise<Availability>
  addException: (payload: ExceptionPayload) => Promise<Availability>
  removeException: (exceptionId: string) => Promise<Availability>
  updateRules: (rules: BookingRules) => Promise<Availability>
  preview: (weekStart: string) => Promise<Record<string, Slot[]>>
}

const scopeAt = (base: string, previewParams: Record<string, string>): AvailabilityScope => ({
  get: () => api.get<Availability>(base).then((r) => r.data),
  updateWeekly: (weekly) => api.put<Availability>(`${base}/weekly`, weekly).then((r) => r.data),
  addException: (payload) =>
    api.post<Availability>(`${base}/exceptions`, payload).then((r) => r.data),
  removeException: (exceptionId) =>
    api.delete<Availability>(`${base}/exceptions/${exceptionId}`).then((r) => r.data),
  updateRules: (rules) => api.put<Availability>(`${base}/rules`, rules).then((r) => r.data),
  preview: (weekStart) =>
    api
      .get<{ preview: Record<string, Slot[]> }>('/availability/preview', {
        params: { week_start: weekStart, ...previewParams },
      })
      .then((r) => r.data.preview),
})

export const myAvailability: AvailabilityScope = scopeAt('/availability/me', {})

export const agendaAvailability = (agendaId: string): AvailabilityScope =>
  scopeAt(`/availability/agendas/${agendaId}`, { agenda_id: agendaId })
