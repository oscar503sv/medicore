import { api } from './client'
import type { MedicalDocument, MedicalRecord, RecordPage, VitalsReading } from '@/types'

export const recordsApi = {
  list: (params: {
    patient_id?: string
    type?: string
    date_from?: string
    date_to?: string
    q?: string
    offset: number
    limit: number
  }) => api.get<RecordPage>('/records', { params }).then((r) => r.data),

  /** The full clinical history of a patient: doctors only. */
  history: (patientId: string) =>
    api.get<MedicalRecord[]>(`/patients/${patientId}/records`).then((r) => r.data),

  vitals: (patientId: string) =>
    api.get<VitalsReading[]>(`/patients/${patientId}/vitals`).then((r) => r.data),

  get: (id: string) => api.get<MedicalRecord>(`/records/${id}`).then((r) => r.data),

  amend: (id: string, payload: { chief_complaint?: string; note?: Record<string, string> }) =>
    api.post<MedicalRecord>(`/records/${id}/amend`, payload).then((r) => r.data),

  listDocuments: (patientId: string) =>
    api.get<MedicalDocument[]>(`/patients/${patientId}/documents`).then((r) => r.data),

  uploadDocument: (payload: {
    patient_id: string
    file_name: string
    kind: string
    mime_type: string
    size_bytes: number
    storage_key: string
    record_id?: string | null
  }) => api.post<MedicalDocument>('/documents', payload).then((r) => r.data),
}
