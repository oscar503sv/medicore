import { api } from './client'

export type ApplicationRoute = 'im' | 'iv' | 'sc' | 'id' | 'nebulized' | 'oral' | 'topical'
export type ApplicationOrderStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'
export type ApplicationOutcome = 'applied' | 'refused' | 'contraindicated'
export type ApplicationSite =
  | 'left_arm'
  | 'right_arm'
  | 'left_gluteus'
  | 'right_gluteus'
  | 'left_thigh'
  | 'right_thigh'
  | 'left_hand'
  | 'right_hand'
  | 'left_forearm'
  | 'right_forearm'
  | 'abdomen'

export const ROUTES: ApplicationRoute[] = ['im', 'iv', 'sc', 'id', 'nebulized', 'oral', 'topical']
export const SITES: ApplicationSite[] = [
  'left_gluteus',
  'right_gluteus',
  'left_arm',
  'right_arm',
  'left_thigh',
  'right_thigh',
  'left_hand',
  'right_hand',
  'left_forearm',
  'right_forearm',
  'abdomen',
]
export const DEFAULT_OBSERVATION_MINUTES = 30

export interface ApplicationRecord {
  id: string
  order_id: string
  dose_number: number
  outcome: ApplicationOutcome
  recorded_at: string
  recorded_by_name: string | null
  lot: string | null
  lot_expiry: string | null
  site: ApplicationSite | null
  blood_pressure: string | null
  temperature: number | null
  allergy_override: string | null
  notes: string | null
  observe_until: string | null
  observation_closed_at: string | null
  observation_closed_by_name: string | null
  reaction: boolean | null
  reaction_notes: string | null
  voided_at: string | null
  voided_by_name: string | null
  void_reason: string | null
}

export interface ApplicationOrder {
  id: string
  patient_id: string
  drug: string
  dose: string
  route: ApplicationRoute
  source: 'internal' | 'external'
  status: ApplicationOrderStatus
  /** Naive clinic wall-clock. */
  starts_at: string
  doses_total: number
  interval_hours: number | null
  observation_minutes: number
  instructions: string | null
  ordered_by_name: string | null
  external_prescriber: string | null
  external_jvpm: string | null
  created_by_name: string | null
  created_at: string
  cancelled_at: string | null
  cancelled_by_name: string | null
  cancel_reason: string | null
  next_dose: number | null
  /** Naive clinic wall-clock. */
  next_due_at: string | null
  allergy_conflicts: string[]
  records: ApplicationRecord[]
}

export interface WorklistPatient {
  id: string
  code: string
  name: string
  age: number
  allergies: string[]
}

export interface ApplicationWorklist {
  now: string
  due: { patient: WorklistPatient; order: ApplicationOrder; late: boolean }[]
  observing: { patient: WorklistPatient; order: ApplicationOrder; record: ApplicationRecord }[]
  done_today: { patient: WorklistPatient; order: ApplicationOrder; record: ApplicationRecord }[]
}

export interface ExternalOrderPayload {
  patient_id: string
  drug: string
  dose: string
  route: ApplicationRoute
  prescriber: string
  jvpm: string
  doses_total: number
  interval_hours: number | null
  observation_minutes: number
  instructions?: string | null
}

export interface RecordApplicationPayload {
  outcome: ApplicationOutcome
  lot?: string | null
  lot_expiry?: string | null
  site?: ApplicationSite | null
  blood_pressure?: string | null
  temperature?: number | null
  allergy_override?: string | null
  notes?: string | null
}

export const applicationsApi = {
  worklist: () => api.get<ApplicationWorklist>('/applications/worklist').then((r) => r.data),

  patient: (patientId: string) =>
    api.get<ApplicationOrder[]>(`/applications/patients/${patientId}`).then((r) => r.data),

  createExternal: (payload: ExternalOrderPayload) =>
    api.post<ApplicationOrder>('/applications/orders', payload).then((r) => r.data),

  cancel: (orderId: string, reason: string) =>
    api
      .post<ApplicationOrder>(`/applications/orders/${orderId}/cancel`, { reason })
      .then((r) => r.data),

  record: (orderId: string, payload: RecordApplicationPayload) =>
    api
      .post<ApplicationRecord>(`/applications/orders/${orderId}/records`, payload)
      .then((r) => r.data),

  closeObservation: (recordId: string, reaction: boolean, notes?: string | null) =>
    api
      .post<ApplicationRecord>(`/applications/records/${recordId}/observation`, {
        reaction,
        notes,
      })
      .then((r) => r.data),

  void: (recordId: string, reason: string) =>
    api
      .post<ApplicationRecord>(`/applications/records/${recordId}/void`, { reason })
      .then((r) => r.data),
}
