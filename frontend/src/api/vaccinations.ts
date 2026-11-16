import { api } from './client'
import type { Appointment } from '@/types'

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
  /** The appointment this dose was recorded from, when it came from a visit. */
  appointment_id: string | null
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

/** A vaccination appointment of today still open, as the worklist shows it. */
export interface WorklistAppointment {
  appointment: VaccinationAppointment
  patient: WorklistPatient
  attendant_name: string | null
}

export interface VisitDosePayload {
  vaccine_code: string
  dose_key?: string | null
  outcome: 'administered'
  lot: string
  route?: VaccineRoute | null
  site?: InjectionSite | null
  notes?: string | null
}

export interface VaccinationVisitPayload {
  appointment_id: string
  patient_id: string
  doses: VisitDosePayload[]
}

/** What a vaccination view needs of an appointment: no reason, fee or insurer. */
export type VaccinationAppointment = Pick<
  Appointment,
  'id' | 'code' | 'scheduled_start' | 'duration_minutes' | 'status' | 'type' | 'is_walk_in'
>

export interface VaccinationVisitResult {
  appointment: VaccinationAppointment
  records: VaccinationRecord[]
}

export interface VaccinationWorklist {
  today: string
  pending: WorklistDose[]
  upcoming: WorklistDose[]
  given_today: { patient: WorklistPatient; record: VaccinationRecord }[]
  /** Empty without appointments.view. */
  appointments_today: WorklistAppointment[]
}

export const vaccinationsApi = {
  /** National scheme (El Salvador, MINSAL): vaccines and scheduled doses. Static per release. */
  catalog: () => api.get<VaccinationCatalog>('/vaccinations/catalog').then((r) => r.data),

  card: (patientId: string) =>
    api.get<VaccinationCard>(`/vaccinations/patients/${patientId}`).then((r) => r.data),

  record: (patientId: string, payload: RecordVaccinationPayload) =>
    api.post<VaccinationRecord>(`/vaccinations/patients/${patientId}`, payload).then((r) => r.data),

  /** Records every dose of a visit and closes the appointment, atomically. */
  recordVisit: (payload: VaccinationVisitPayload) =>
    api.post<VaccinationVisitResult>('/vaccinations/visits', payload).then((r) => r.data),

  void: (recordId: string, reason: string) =>
    api.post<VaccinationRecord>(`/vaccinations/${recordId}/void`, { reason }).then((r) => r.data),

  worklist: (horizonDays = 30) =>
    api
      .get<VaccinationWorklist>('/vaccinations/worklist', { params: { horizon_days: horizonDays } })
      .then((r) => r.data),
}
