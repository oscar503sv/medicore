import { api } from './client'
import type { MedicalDocument, MedicalRecord } from '@/types'

export const recordsApi = {
  list: (params: { patient_id?: string; type?: string } = {}) =>
    api.get<MedicalRecord[]>('/records', { params }).then((r) => r.data),

  get: (id: string) => api.get<MedicalRecord>(`/records/${id}`).then((r) => r.data),

  amend: (id: string, payload: { chief_complaint?: string; soap?: Record<string, string> }) =>
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
