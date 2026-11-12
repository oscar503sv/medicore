import { api } from './client'
import type {
  ApplicationDraft,
  Consultation,
  ExamKind,
  MedicalRecord,
  Vitals,
} from '@/types'

export const consultationsApi = {
  get: (id: string) =>
    api.get<Consultation>(`/consultations/${id}`).then((r) => r.data),

  start: (appointmentId: string) =>
    api
      .post<Consultation>(`/consultations/start/${appointmentId}`)
      .then((r) => r.data),

  /** `note` maps section keys to their text. */
  autosave: (id: string, patch: { vitals?: Partial<Vitals>; note?: Record<string, string> }) =>
    api.patch<Consultation>(`/consultations/${id}/autosave`, patch).then((r) => r.data),

  changeTemplate: (id: string, template: string) =>
    api
      .post<Consultation>(`/consultations/${id}/note-template`, { template })
      .then((r) => r.data),

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

  addApplication: (id: string, payload: Omit<ApplicationDraft, 'instructions'> & {
    instructions?: string | null
  }) =>
    api.post<Consultation>(`/consultations/${id}/applications`, payload).then((r) => r.data),

  removeApplication: (id: string, index: number) =>
    api.delete<Consultation>(`/consultations/${id}/applications/${index}`).then((r) => r.data),

  addProcedure: (
    id: string,
    payload: { type_id: string; indication: string; included?: boolean },
  ) =>
    api.post<Consultation>(`/consultations/${id}/procedures`, payload).then((r) => r.data),

  removeProcedure: (id: string, index: number) =>
    api.delete<Consultation>(`/consultations/${id}/procedures/${index}`).then((r) => r.data),

  addExam: (id: string, payload: { name: string; kind: ExamKind; notes?: string | null }) =>
    api.post<Consultation>(`/consultations/${id}/exams`, payload).then((r) => r.data),

  removeExam: (id: string, index: number) =>
    api.delete<Consultation>(`/consultations/${id}/exams/${index}`).then((r) => r.data),

  sign: (id: string) =>
    api.post<MedicalRecord>(`/consultations/${id}/sign`, {}).then((r) => r.data),
}
