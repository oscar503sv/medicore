import { api } from './client'

export type ProcedurePerformer = 'doctor' | 'doctor_or_nurse'
export type ProcedureStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'

export interface ProcedureType {
  id: string
  name: string
  performer: ProcedurePerformer
  requires_consent: boolean
  follow_up_days: number | null
  takes_specimen: boolean
  technique_template: string | null
  instructions_template: string | null
  active: boolean
  /** USD "25.00"; null: no price set. */
  price: string | null
}

export type ProcedureTypePayload = Omit<ProcedureType, 'id' | 'active'>

/** What the performer fills in before signing; every field replaces the stored one. */
export interface ProcedureProgress {
  allergies_reviewed: boolean
  anticoagulants: boolean | null
  fasting: boolean | null
  allergy_override: string | null
  bp_before: string | null
  hr_before: number | null
  spo2_before: number | null
  temp_before: number | null
  bp_after: string | null
  hr_after: number | null
  spo2_after: number | null
  temp_after: number | null
  anesthesia: string | null
  technique: string | null
  findings: string | null
  materials: string | null
  complications: string | null
  instructions: string | null
  specimen_sent: boolean
  specimen_description: string | null
}

export const PROGRESS_FIELDS: (keyof ProcedureProgress)[] = [
  'allergies_reviewed',
  'anticoagulants',
  'fasting',
  'allergy_override',
  'bp_before',
  'hr_before',
  'spo2_before',
  'temp_before',
  'bp_after',
  'hr_after',
  'spo2_after',
  'temp_after',
  'anesthesia',
  'technique',
  'findings',
  'materials',
  'complications',
  'instructions',
  'specimen_sent',
  'specimen_description',
]

export interface Amendment {
  at: string
  by_name: string | null
  text: string
  reason: string
}

export interface Procedure extends ProcedureProgress {
  id: string
  patient_id: string
  type_id: string
  type_name: string
  performer: ProcedurePerformer
  requires_consent: boolean
  source: 'consultation' | 'direct'
  indication: string
  ordered_by_name: string | null
  created_by_name: string | null
  follow_up_days: number | null
  takes_specimen: boolean
  consultation_id: string | null
  appointment_id: string | null
  created_at: string
  status: ProcedureStatus
  consent_signer: string | null
  consent_relationship: string | null
  consent_witness: string | null
  consent_at: string | null
  consent_by_name: string | null
  started_at: string | null
  performed_at: string | null
  performed_by_name: string | null
  /** Suggested follow-up day (YYYY-MM-DD). */
  follow_up_on: string | null
  cancelled_at: string | null
  cancelled_by_name: string | null
  cancel_reason: string | null
  amendments: Amendment[]
  /** Catalog price when ordered and what is charged ("25.00"); null: no price. */
  listed_fee: string | null
  fee: string | null
  fee_note: string | null
  /** Included in the consultation fee it was indicated in. */
  fee_included: boolean
}

export interface ProcedurePatient {
  id: string
  code: string
  name: string
  age: number
  allergies: string[]
}

export interface ProcedureDetail {
  procedure: Procedure
  patient: ProcedurePatient
  technique_template: string | null
  instructions_template: string | null
  /** The anesthesia against the patient's allergies. */
  allergy_conflicts: string[]
  /** The current user may change what it is charged. */
  fee_editable: boolean
}

export interface ProcedureWorklist {
  now: string
  pending: { patient: ProcedurePatient; procedure: Procedure }[]
  today: {
    appointment_id: string
    /** Naive clinic wall-clock. */
    scheduled_start: string
    status: string
    reason: string
    doctor_name: string | null
    patient: ProcedurePatient
    procedure: Procedure | null
  }[]
  done: { patient: ProcedurePatient; procedure: Procedure }[]
}

export const proceduresApi = {
  catalog: () => api.get<ProcedureType[]>('/procedures/catalog').then((r) => r.data),

  createType: (payload: ProcedureTypePayload) =>
    api.post<ProcedureType>('/procedures/catalog', payload).then((r) => r.data),

  updateType: (id: string, payload: ProcedureTypePayload) =>
    api.put<ProcedureType>(`/procedures/catalog/${id}`, payload).then((r) => r.data),

  setTypeActive: (id: string, active: boolean) =>
    api.post<ProcedureType>(`/procedures/catalog/${id}/active`, { active }).then((r) => r.data),

  worklist: () => api.get<ProcedureWorklist>('/procedures/worklist').then((r) => r.data),

  patient: (patientId: string) =>
    api.get<Procedure[]>(`/procedures/patients/${patientId}`).then((r) => r.data),

  get: (id: string) => api.get<ProcedureDetail>(`/procedures/${id}`).then((r) => r.data),

  create: (payload: {
    patient_id: string
    type_id: string
    indication: string
    appointment_id?: string | null
  }) => api.post<ProcedureDetail>('/procedures', payload).then((r) => r.data),

  saveProgress: (id: string, payload: ProcedureProgress) =>
    api.put<ProcedureDetail>(`/procedures/${id}`, payload).then((r) => r.data),

  consent: (
    id: string,
    payload: { signer: string; relationship: string | null; witness: string },
  ) => api.post<ProcedureDetail>(`/procedures/${id}/consent`, payload).then((r) => r.data),

  sign: (id: string) => api.post<ProcedureDetail>(`/procedures/${id}/sign`).then((r) => r.data),

  cancel: (id: string, reason: string) =>
    api.post<ProcedureDetail>(`/procedures/${id}/cancel`, { reason }).then((r) => r.data),

  amend: (id: string, text: string, reason: string) =>
    api.post<ProcedureDetail>(`/procedures/${id}/amendments`, { text, reason }).then((r) => r.data),

  setFee: (id: string, payload: { included: boolean; amount: string | null; note: string | null }) =>
    api.put<ProcedureDetail>(`/procedures/${id}/fee`, payload).then((r) => r.data),
}
