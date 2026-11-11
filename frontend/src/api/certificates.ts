import { api } from './client'
import type { CertificateKind, MedicalCertificate } from '@/types'

export interface IssueCertificatePayload {
  kind: CertificateKind
  rest_from?: string | null
  rest_days?: number | null
  include_diagnosis?: boolean
  remarks?: string | null
  addressee?: string | null
}

export const certificatesApi = {
  forRecord: (recordId: string) =>
    api.get<MedicalCertificate[]>(`/records/${recordId}/certificates`).then((r) => r.data),

  forPatient: (patientId: string) =>
    api.get<MedicalCertificate[]>(`/patients/${patientId}/certificates`).then((r) => r.data),

  issue: (recordId: string, payload: IssueCertificatePayload) =>
    api.post<MedicalCertificate>(`/records/${recordId}/certificates`, payload).then((r) => r.data),

  void: (id: string, reason: string) =>
    api.post<MedicalCertificate>(`/certificates/${id}/void`, { reason }).then((r) => r.data),
}
