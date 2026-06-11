import { api } from './client'
import type { Prescription } from '@/types'

export const prescriptionsApi = {
  list: (patientId: string) =>
    api
      .get<{ items: Prescription[] }>('/prescriptions', { params: { patient_id: patientId } })
      .then((r) => r.data.items),

  complete: (id: string) =>
    api.post<Prescription>(`/prescriptions/${id}/complete`).then((r) => r.data),

  cancel: (id: string) =>
    api.post<Prescription>(`/prescriptions/${id}/cancel`).then((r) => r.data),
}
