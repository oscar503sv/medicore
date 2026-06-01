import { api } from './client'
import type { Availability, BookingRules, Slot, TimeRange, WeeklyDay } from '@/types'

export const availabilityApi = {
  getMine: () => api.get<Availability>('/availability/me').then((r) => r.data),

  updateWeekly: (weekly: WeeklyDay[]) =>
    api.put<Availability>('/availability/me/weekly', weekly).then((r) => r.data),

  addException: (payload: {
    date: string
    kind: string
    reason?: string
    blocks?: TimeRange[]
  }) => api.post<Availability>('/availability/me/exceptions', payload).then((r) => r.data),

  removeException: (exceptionId: string) =>
    api
      .delete<Availability>(`/availability/me/exceptions/${exceptionId}`)
      .then((r) => r.data),

  updateRules: (rules: BookingRules) =>
    api.put<Availability>('/availability/me/rules', rules).then((r) => r.data),

  preview: (weekStart: string, doctorId?: string) =>
    api
      .get<{ preview: Record<string, Slot[]> }>('/availability/preview', {
        params: { week_start: weekStart, doctor_id: doctorId },
      })
      .then((r) => r.data.preview),
}
