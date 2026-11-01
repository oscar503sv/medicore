import { api } from './client'
import type { PaginatedResponse, Patient, PatientDetail } from '@/types'

export interface PatientStats {
  active: number
  inactive: number
  /** Registered in the last 30 days. */
  new_recent: number
  /** With an active appointment ahead; null without permission to see appointments. */
  with_upcoming: number | null
}

export interface PatientListParams {
  status?: string
  doctor_id?: string
  q?: string
  offset?: number
  limit?: number
}

export interface CreatePatientPayload {
  first_name: string
  last_name: string
  sex: string
  date_of_birth: string
  contact?: Partial<Patient['contact']>
  blood_type?: string | null
  primary_doctor_id?: string | null
  tags?: string[]
  allergies?: string[]
}

export const patientsApi = {
  list: (params: PatientListParams = {}) =>
    api.get<PaginatedResponse<Patient>>('/patients', { params }).then((r) => r.data),

  /** Headline numbers for the patients page (independent of the list's filters). */
  stats: () => api.get<PatientStats>('/patients/stats').then((r) => r.data),

  get: (id: string) => api.get<PatientDetail>(`/patients/${id}`).then((r) => r.data),

  create: (payload: CreatePatientPayload) =>
    api.post<Patient>('/patients', payload).then((r) => r.data),

  update: (id: string, payload: Partial<CreatePatientPayload>) =>
    api.patch<Patient>(`/patients/${id}`, payload).then((r) => r.data),

  archive: (id: string) =>
    api.post<Patient>(`/patients/${id}/archive`).then((r) => r.data),

  reactivate: (id: string) =>
    api.post<Patient>(`/patients/${id}/reactivate`).then((r) => r.data),
}
