import { api } from './client'

export type VaccineStage = 'childhood' | 'adolescence' | 'adulthood' | 'indicated'
export type DoseKind = 'dose' | 'booster' | 'single' | 'yearly' | 'periodic'
export type DoseStatus =
  | 'administered'
  | 'refused'
  | 'contraindicated'
  | 'overdue'
  | 'due'
  | 'due_soon'
  | 'upcoming'
  | 'not_applicable'
  | 'indicated'
export type VaccinationOutcome = 'administered' | 'refused' | 'contraindicated'
export type VaccinationSource = 'clinic' | 'external'
export type VaccineRoute = 'im' | 'sc' | 'id' | 'oral'
export type InjectionSite = 'left_arm' | 'right_arm' | 'left_thigh' | 'right_thigh' | 'mouth'

export interface Vaccine {
  code: string
  route: VaccineRoute
  /** False for vaccines offered privately, outside the national scheme. */
  in_schedule: boolean
}

export interface ScheduledDose {
  key: string
  vaccine: string
  kind: DoseKind
  number: number
  age_months: number
  stage: VaccineStage
  max_age_months: number | null
  repeat_months: number | null
  routine: boolean
  sex: string | null
}

export interface VaccinationCatalog {
  schedule: string
  vaccines: Vaccine[]
  doses: ScheduledDose[]
}

export interface DoseState {
  key: string
  status: DoseStatus
  due_on: string | null
  last_on: string | null
}

export interface VaccinationRecord {
  id: string
  patient_id: string
  vaccine_code: string
  dose_key: string | null
  outcome: VaccinationOutcome
  occurred_on: string
  source: VaccinationSource
  lot: string | null
  route: VaccineRoute | null
  site: InjectionSite | null
  notes: string | null
  recorded_by_id: string
  recorded_by_name: string | null
  created_at: string
  voided_at: string | null
  voided_by_name: string | null
  void_reason: string | null
}

export interface VaccinationCard {
  today: string
  states: DoseState[]
  records: VaccinationRecord[]
}

export interface RecordVaccinationPayload {
  vaccine_code: string
  dose_key?: string | null
  outcome: VaccinationOutcome
  occurred_on: string
  source: VaccinationSource
  lot?: string | null
  route?: VaccineRoute | null
  site?: InjectionSite | null
  notes?: string | null
}

export interface WorklistPatient {
  id: string
  code: string
  name: string
  age: number
  date_of_birth: string
  sex: string
  phone: string | null
}

export interface WorklistDose {
  patient: WorklistPatient
  key: string
  vaccine: string
  status: DoseStatus
  due_on: string | null
}

export interface VaccinationWorklist {
  today: string
  pending: WorklistDose[]
  upcoming: WorklistDose[]
  given_today: { patient: WorklistPatient; record: VaccinationRecord }[]
}

export const vaccinationsApi = {
  /** National scheme (El Salvador, MINSAL): vaccines and scheduled doses. Static per release. */
  catalog: () => api.get<VaccinationCatalog>('/vaccinations/catalog').then((r) => r.data),

  card: (patientId: string) =>
    api.get<VaccinationCard>(`/vaccinations/patients/${patientId}`).then((r) => r.data),

  record: (patientId: string, payload: RecordVaccinationPayload) =>
    api.post<VaccinationRecord>(`/vaccinations/patients/${patientId}`, payload).then((r) => r.data),

  void: (recordId: string, reason: string) =>
    api.post<VaccinationRecord>(`/vaccinations/${recordId}/void`, { reason }).then((r) => r.data),

  worklist: (horizonDays = 30) =>
    api
      .get<VaccinationWorklist>('/vaccinations/worklist', { params: { horizon_days: horizonDays } })
      .then((r) => r.data),
}
