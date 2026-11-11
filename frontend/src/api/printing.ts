import { api } from './client'
import type { ExamRequest, PaperSize, PrescriptionSnapshot, Soap, Vitals } from '@/types'

export interface PrintContext {
  clinic: {
    name: string
    tax_id: string
    location_name: string
    address: string | null
    phone: string | null
    paper: PaperSize
    letterhead: boolean
  }
  printed_at: string
  patient: {
    name: string
    code: string
    sex: string
    date_of_birth: string
    age: number
    allergies: string[]
  } | null
  doctor: {
    name: string
    specialty: string | null
    jvpm: string | null
    sex: string | null
  } | null
}

export type RecordDocument = 'prescription' | 'exams' | 'record'
export type ProcedureDocument = 'instructions' | 'consent' | 'pathology'

export interface RecordPrint {
  context: PrintContext
  record: {
    code: string
    encounter_at: string
    signed_at: string
    location_name: string
    insurer_name: string | null
    chief_complaint: string
    soap: Soap
    vitals: Vitals
    diagnoses: { code: string; label: string }[]
    prescriptions: PrescriptionSnapshot[]
    exams: ExamRequest[]
    vaccines: { name: string; lot: string; dose: string; site: string }[]
    status: string
  }
  indications: string | null
  amends_code: string | null
}

export interface CertificatePrint {
  context: PrintContext
  certificate: {
    code: string
    kind: 'attendance' | 'rest'
    issued_at: string
    rest_from: string | null
    rest_days: number | null
    rest_until: string | null
    diagnosis: string | null
    remarks: string | null
    addressee: string | null
  }
  encounter_at: string
  ended_at: string
}

export interface ProcedurePrint {
  context: PrintContext
  procedure: {
    type_name: string
    status: string
    indication: string
    requires_consent: boolean
    takes_specimen: boolean
    anesthesia: string | null
    technique: string | null
    findings: string | null
    complications: string | null
    instructions: string | null
    specimen_sent: boolean
    specimen_description: string | null
    performed_at: string | null
    follow_up_on: string | null
    follow_up_days: number | null
  }
}

interface AppointmentLine {
  code: string
  type: string
  status: string
  scheduled_start: string
  duration_minutes: number
}

export interface AppointmentPrint {
  context: PrintContext
  appointment: AppointmentLine
}

export interface AgendaPrint {
  context: PrintContext
  day: string
  rows: (AppointmentLine & { reason: string; patient_name: string; patient_code: string })[]
}

export const printApi = {
  record: (id: string, document: RecordDocument) =>
    api.get<RecordPrint>(`/print/records/${id}`, { params: { document } }).then((r) => r.data),

  certificate: (id: string) =>
    api.get<CertificatePrint>(`/print/certificates/${id}`).then((r) => r.data),

  procedure: (id: string, document: ProcedureDocument) =>
    api
      .get<ProcedurePrint>(`/print/procedures/${id}`, { params: { document } })
      .then((r) => r.data),

  vaccinationCard: (patientId: string) =>
    api.get<PrintContext>(`/print/vaccination-card/${patientId}`).then((r) => r.data),

  appointment: (id: string) =>
    api.get<AppointmentPrint>(`/print/appointments/${id}`).then((r) => r.data),

  agenda: (date: string, doctorId?: string) =>
    api
      .get<AgendaPrint>('/print/agenda', {
        params: { date, ...(doctorId ? { doctor_id: doctorId } : {}) },
      })
      .then((r) => r.data),
}

/** Open a printable document in a new tab (the print view; the user prints from there). */
export function openPrint(path: string) {
  window.open(`/print/${path}`, '_blank', 'noopener')
}
