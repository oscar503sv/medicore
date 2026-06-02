// ── Auth ──────────────────────────────────────────────────────────────────────
export interface Session {
  token: string
  user_id: string
  tenant_id: string
  tenant_name: string
  role: Role
  name: string
  sex: Sex | null
  must_change_password: boolean
}

export interface MyProfile {
  name: string
  email: string
  role: Role
  sex: Sex | null
  specialty: string | null
  phone: string | null
  bio: string | null
}

// ── Platform (superadmin) ──────────────────────────────────────────────────────
export type TenantStatus = 'active' | 'suspended' | 'archived'
export type IcdVersion = 'cie10' | 'cie11'

export interface PlatformSession {
  token: string
  admin_id: string
  name: string
  email: string
}

export interface PlatformAdminProfile {
  id: string
  name: string
  email: string
  avatar_initials: string
  last_seen_at: string | null
}

export interface TenantLocation {
  id: string
  name: string
  address: string | null
  is_primary: boolean
}

export interface Tenant {
  id: string
  legal_name: string
  tax_id: string
  slug: string
  timezone: string
  plan: string
  seat_limit: number
  status: TenantStatus
  icd_version: IcdVersion
  locations: TenantLocation[]
}

// ── Enums ─────────────────────────────────────────────────────────────────────
export type Role = 'admin' | 'doctor' | 'nurse' | 'receptionist'
export type UserStatus = 'active' | 'pending' | 'suspended'
export type PatientStatus = 'active' | 'inactive'
export type Sex = 'male' | 'female' | 'other'
export type AppointmentStatus =
  | 'scheduled'
  | 'confirmed'
  | 'in_progress'
  | 'completed'
  | 'cancelled'
  | 'no_show'
export type AppointmentType = 'consult' | 'follow_up' | 'check_up' | 'procedure' | 'emergency'
export type ConsultationStatus = 'draft' | 'signed'
export type RecordStatus = 'draft' | 'signed' | 'amended'
export type RecordType =
  | 'evolution'
  | 'cardio_report'
  | 'obstetric'
  | 'vaccination'
  | 'diagnosis'
  | 'lab_report'
  | 'generic'
export type DocumentKind = 'lab' | 'imaging' | 'rx' | 'consent' | 'other'
export type SlotStatus = 'free' | 'taken' | 'out_of_hours' | 'blocked_rules'

// ── Users ─────────────────────────────────────────────────────────────────────
export interface User {
  id: string
  tenant_id: string
  name: string
  email: string
  role: Role
  status: UserStatus
  sex: Sex | null
  specialty: string | null
  phone: string | null
  avatar_initials: string
  last_seen_at: string | null
  joined_at: string
}

// ── Patients ──────────────────────────────────────────────────────────────────
export interface ContactInfo {
  phone: string | null
  email: string | null
  address: string | null
  emergency_contact_name: string | null
  emergency_contact_phone: string | null
}

export interface Patient {
  id: string
  tenant_id: string
  code: string
  first_name: string
  last_name: string
  sex: Sex
  date_of_birth: string
  age: number
  blood_type: string | null
  primary_doctor_id: string | null
  status: PatientStatus
  tags: string[]
  allergies: string[]
  contact: ContactInfo
  created_at: string
  updated_at: string
}

export interface Insurer {
  id: string
  tenant_id: string
  name: string
  phone: string | null
  email: string | null
  address: string | null
  contact_person: string | null
  notes: string | null
  active: boolean
  created_at: string
  updated_at: string
}

export interface PatientDetail {
  patient: Patient
  last_visit: string | null
  next_visit: string | null
  records_count: number
  active_prescriptions: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  offset: number
  limit: number
}

// ── Appointments ──────────────────────────────────────────────────────────────
export interface Appointment {
  id: string
  tenant_id: string
  code: string
  patient_id: string
  doctor_id: string
  location_id: string
  type: AppointmentType
  status: AppointmentStatus
  scheduled_start: string
  scheduled_end: string
  duration_minutes: number
  reason: string
  room: string | null
  insurance_id: string | null
  patient_name: string | null
  doctor_name: string | null
  insurer_name: string | null
  created_by_id: string
  created_at: string
  updated_at: string
}

export interface Slot {
  start: string
  end: string
  status: SlotStatus
}

// ── Consultations ─────────────────────────────────────────────────────────────
export interface Vitals {
  blood_pressure: string | null
  heart_rate: number | null
  spo2: number | null
  temperature: string | null
  weight: string | null
  glucose: number | null
  height: string | null
  fetal_heart_rate: number | null
}

export interface Soap {
  subjective: string
  objective: string
  assessment: string
  plan: string
}

export interface Diagnosis {
  code: string
  label: string
}

export interface PrescriptionDraft {
  drug: string
  dose: string
  schedule: string
  duration_days: number | null
}

export interface Consultation {
  id: string
  tenant_id: string
  appointment_id: string
  patient_id: string
  doctor_id: string
  status: ConsultationStatus
  started_at: string
  ended_at: string | null
  vitals: Vitals
  soap: Soap
  diagnoses: Diagnosis[]
  draft_prescriptions: PrescriptionDraft[]
  attachments: unknown[]
  completion_percent: number
  last_saved_at: string | null
  // Header context for the live consultation screen (immutable for its lifetime).
  patient: Patient | null
  appointment: Appointment | null
}

// ── Medical Records ───────────────────────────────────────────────────────────
export interface MedicalRecord {
  id: string
  tenant_id: string
  code: string
  patient_id: string
  author_id: string
  type: RecordType
  status: RecordStatus
  encounter_at: string
  location_name: string
  chief_complaint: string
  soap: Soap
  vitals: Vitals
  diagnoses: Diagnosis[]
  prescriptions: unknown[]
  vaccines: unknown[]
  attachments: unknown[]
  signed_at: string
  signed_by_id: string
  appointment_id: string | null
  consultation_id: string | null
  amends_record_id: string | null
}

// ── Documents ─────────────────────────────────────────────────────────────────
export interface MedicalDocument {
  id: string
  patient_id: string
  file_name: string
  kind: DocumentKind
  mime_type: string
  size_bytes: number
  storage_key: string
  uploaded_by_id: string
  uploaded_at: string
  record_id: string | null
}

// ── Availability ──────────────────────────────────────────────────────────────
export interface TimeRange {
  start: string
  end: string
}

export interface WeeklyDay {
  day_of_week: number
  enabled: boolean
  blocks: TimeRange[]
}

export interface AvailabilityException {
  id: string
  date: string
  kind: 'off' | 'extra'
  reason: string
  blocks: TimeRange[]
}

export interface BookingRules {
  slot_minutes: number
  buffer_minutes: number
  min_advance_hours: number
  max_advance_days: number
  allow_same_day: boolean
}

export interface Availability {
  id: string
  doctor_id: string
  weekly: WeeklyDay[]
  exceptions: AvailabilityException[]
  rules: BookingRules
}

// ── Organization ──────────────────────────────────────────────────────────────
export interface Location {
  id: string
  name: string
  address: string | null
  is_primary: boolean
}

export interface Organization {
  id: string
  legal_name: string
  tax_id: string
  slug: string
  timezone: string
  plan: string
  seat_limit: number
  locations: Location[]
}
