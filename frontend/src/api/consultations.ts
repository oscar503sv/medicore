import { api } from './client'
import type { Consultation, MedicalRecord, Soap, Vitals } from '@/types'

export const consultationsApi = {
  start: (appointmentId: string) =>
    api
      .post<Consultation>(`/consultations/start/${appointmentId}`)
      .then((r) => r.data),

  autosave: (id: string, patch: { vitals?: Partial<Vitals>; soap?: Partial<Soap> }) =>
    api.patch<Consultation>(`/consultations/${id}/autosave`, patch).then((r) => r.data),

  addDiagnosis: (id: string, code: string, label: string) =>
    api
      .post<Consultation>(`/consultations/${id}/diagnoses`, { code, label })
      .then((r) => r.data),

  removeDiagnosis: (id: string, code: string) =>
    api.delete<Consultation>(`/consultations/${id}/diagnoses/${code}`).then((r) => r.data),

  addPrescription: (
    id: string,
    payload: { drug: string; dose: string; schedule: string; duration_days?: number | null },
  ) =>
    api
      .post<Consultation>(`/consultations/${id}/prescriptions`, payload)
      .then((r) => r.data),

  removePrescription: (id: string, index: number) =>
    api
      .delete<Consultation>(`/consultations/${id}/prescriptions/${index}`)
      .then((r) => r.data),

  sign: (id: string, payload: { record_type?: string; chief_complaint?: string }) =>
    api.post<MedicalRecord>(`/consultations/${id}/sign`, payload).then((r) => r.data),
}
