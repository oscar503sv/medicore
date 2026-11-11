// ── Auth ──────────────────────────────────────────────────────────────────────
// Mirror of the backend Permission catalog (application/common/permissions.py).
export type Permission =
  | 'patients.view'
  | 'patients.create'
  | 'patients.edit'
  | 'patients.archive'
  | 'appointments.view'
  | 'appointments.manage'
  | 'availability.manage'
  | 'fees.manage_own'
  | 'fees.manage_all'
  | 'consultations.start'
  | 'consultations.edit'
  | 'records.view'
  | 'records.upload'
  | 'records.sign'
  | 'records.amend'
  | 'prescriptions.manage'
  | 'diagnoses.view'
  | 'insurers.view'
  | 'insurers.manage'
  | 'users.view'
  | 'users.manage'
  | 'organization.view'
  | 'organization.manage'
  | 'locations.manage'
  | 'audit.view'
  | 'permissions.manage'
  | 'vaccinations.view'
  | 'vaccinations.record'
  | 'applications.view'
  | 'applications.administer'
  | 'procedures.view'
  | 'procedures.perform'
  | 'procedures.catalog'

export interface RolePermissionsEntry {
  defaults: Permission[]
  effective: Permission[]
  customized: boolean
}

export interface PermissionsMatrix {
  catalog: Permission[]
  roles: Record<Role, RolePermissionsEntry>
  /** Permissions of optional modules the clinic hasn't contracted: configurable, not granted. */
  locked: Permission[]
}

// The JWT itself lives in an httpOnly cookie — sessions hold only UI metadata.
export interface Session {
  user_id: string
  tenant_id: string
  tenant_name: string
  timezone: string
  role: Role
  name: string
  sex: Sex | null
  must_change_password: boolean
  permissions: Permission[]
  // Set when a superadmin entered this clinic via support impersonation.
  impersonating?: boolean
}

export interface MyProfile {
  name: string
  email: string
  role: Role
  sex: Sex | null
  specialty: string | null
  phone: string | null
  bio: string | null
  permissions: Permission[]
}

// A live server-side login session (the backing row of a JWT's sid claim).
export interface AuthSessionInfo {
  id: string
  user_id: string
  user_name: string | null
  role: Role | null
  ip_address: string | null
  user_agent: string | null
  created_at: string
  expires_at: string
  current: boolean
}

// ── Notifications ──────────────────────────────────────────────────────────────
// The backend stores what happened (type + data); the client renders the text.

export type NotificationType =
  | 'appointment.created'
  | 'appointment.rescheduled'
  | 'appointment.cancelled'
  | 'appointment.no_show'
  | 'record.amended'
  | 'document.uploaded'
  | 'user.created'
  | 'user.role_changed'

export interface AppNotification {
  id: string
  type: NotificationType | string
  /** Ids for linking plus display labels frozen at emission time (all strings). */
  data: Record<string, string>
  read_at: string | null
  created_at: string
}

// ── Platform (superadmin) ──────────────────────────────────────────────────────
export type TenantStatus = 'active' | 'suspended' | 'archived'
export type IcdVersion = 'cie10' | 'cie11'

export interface PlatformSession {
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
  status: TenantStatus
  icd_version: IcdVersion
  locations: TenantLocation[]
  subscription: TenantSubscriptionSummary
}

// ── Subscriptions ─────────────────────────────────────────────────────────────
export type AddonModule = 'vaccination' | 'applications' | 'procedures'
export const ADDON_MODULES: AddonModule[] = ['vaccination', 'applications', 'procedures']
export type PlanFeature = 'user_permissions'
export type SubscriptionStatus = 'trial' | 'active' | 'grace' | 'read_only'

/** Quotas; `null` = unlimited on a plan, "use the plan's" on a clinic override. */
export interface PlanLimits {
  doctors: number | null
  support_users: number | null
  locations: number | null
  storage_gb: number | null
}

/** Money travels as a decimal string ("79.00", USD). */
export interface Plan {
  code: string
  name: string
  monthly_price: string | null
  limits: PlanLimits
  features: PlanFeature[]
  active: boolean
  sort_order: number
}

export interface AddonPricing {
  prices: Record<AddonModule, string>
  bundle_price: string
}

export interface PlanCatalog {
  plans: Plan[]
  addons: AddonPricing
}

export interface Subscription {
  plan: Plan
  modules: AddonModule[]
  period_end: string | null
  is_trial: boolean
  grace_days: number
  status: SubscriptionStatus
  today: string
  days_left: number | null
  limits: PlanLimits
  limit_overrides: PlanLimits | null
  price_override: string | null
  monthly_price: string | null
  usage: { doctors: number; support_users: number; locations: number }
  addon_prices: AddonPricing
}

export type PaymentMethod = 'bank_transfer' | 'cash' | 'card' | 'other'
export const PAYMENT_METHODS: PaymentMethod[] = ['bank_transfer', 'cash', 'card', 'other']

export interface SubscriptionPayment {
  id: string
  amount: string
  paid_on: string
  months: number
  plan_code: string
  period_end: string // paid-until date this payment left the clinic with
  method: PaymentMethod
  reference: string | null
  notes: string | null
  recorded_at: string
}

/** Any user's view of the subscription, for the app banner. */
export interface SubscriptionNotice {
  status: SubscriptionStatus
  is_trial: boolean
  period_end: string | null
  grace_until: string | null
  days_left: number | null
}

export interface TenantSubscriptionSummary {
  plan_code: string
  modules: AddonModule[]
  period_end: string | null
  is_trial: boolean
  status: SubscriptionStatus
  days_left: number | null
}

export interface TenantStats {
  tenant_id: string
  legal_name: string
  status: TenantStatus
  patients: number
  users: number
  appointments: number
  consultations: number
  records: number
}

/** Where a clinic stands for the business overview. */
export type ClinicStanding = SubscriptionStatus | 'complimentary' | 'suspended'

export interface ClinicBusiness {
  tenant_id: string
  legal_name: string
  slug: string
  standing: ClinicStanding
  plan_code: string
  plan_name: string
  modules: AddonModule[]
  period_end: string | null
  days_left: number | null
  monthly: string | null
  paying: boolean
  usage: { doctors: number; support_users: number; locations: number }
  limits: PlanLimits
  at_capacity: ('doctors' | 'support_users' | 'locations')[]
  last_activity: string | null
  active_users: number
  signed_records: number
}

export interface BusinessOverview {
  today: string
  mrr: string
  unpriced: number
  collected_this_month: string
  collected_last_month: string
  by_standing: Partial<Record<ClinicStanding, number>>
  by_plan: { code: string; name: string; clinics: number; mrr: string }[]
  by_module: Partial<Record<AddonModule, number>>
  active_clinics: number
  inactive_clinics: number
  at_capacity_clinics: number
  weekly_signed: { week: string; count: number }[]
  expiring: ClinicBusiness[]
  clinics: ClinicBusiness[]
}

export interface AuditEntry {
  id: string
  tenant_id: string
  actor_id: string
  action: string
  entity_type: string
  entity_id: string
  metadata: Record<string, unknown>
  timestamp: string
  ip_address?: string | null
  user_agent?: string | null
  actor_name?: string | null
}

/** A consolidated row in the platform global audit (tenant + platform trails merged). */
export interface GlobalAuditEntry {
  id: string
  timestamp: string
  source_kind: 'tenant' | 'platform'
  actor_name?: string | null
  action: string
  clinic_name?: string | null
  metadata: Record<string, unknown>
  ip_address?: string | null
  user_agent?: string | null
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
export type ClinicalRecordType =
  | 'consultation'
  | 'procedure'
  | 'medication_application'
  | 'vaccination'
  | 'lab_result'
  | 'imaging_result'
  | 'discharge_summary'
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
  /** Has per-user exceptions to their role's permissions. */
  permissions_customized: boolean
}

/** One person's permissions: their role's set plus exceptions (plans with per-user permissions). */
export interface UserPermissions {
  user: User
  /** The clinic's plan includes per-user permissions. */
  available: boolean
  catalog: Permission[]
  role_permissions: Permission[]
  granted: Permission[]
  revoked: Permission[]
  effective: Permission[]
  locked: Permission[]
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
  next_visit: string | null
  /** Latest completed appointment (clinic wall-clock); only filled in list responses. */
  last_visit?: string | null
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
  next_appointment: Appointment | null
}

export type PrescriptionStatus = 'active' | 'completed' | 'cancelled'

export interface Prescription {
  id: string
  patient_id: string
  prescriber_id: string
  prescriber_name: string | null
  drug: string
  dose: string
  schedule: string
  start_date: string
  end_date: string | null
  duration_days: number | null
  status: PrescriptionStatus
  record_id: string | null
  created_at: string
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
  /** The doctor's price when booked and what is charged ("25.00", USD); null: no price. */
  listed_fee: string | null
  fee: string | null
  fee_note: string | null
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

export interface DiagnosisSuggestion {
  version: string
  code: string
  label: string
  billable: boolean
  chapter: string | null
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
  draft_applications: ApplicationDraft[]
  draft_procedures: ProcedureDraft[]
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
  patient_name: string | null
  signed_by_name: string | null
  author_id: string
  type: ClinicalRecordType
  status: RecordStatus
  encounter_at: string
  location_name: string
  insurer_name: string | null
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
  min_advance_hours: number
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
  locations: Location[]
}

/** An in-clinic application indicated during a consultation (issued as an order on signing). */
export interface ApplicationDraft {
  drug: string
  dose: string
  route: string
  doses_total: number
  interval_hours: number | null
  observation_minutes: number
  instructions: string | null
}

/** A procedure indicated during a consultation (a pending procedure once it is signed). */
export interface ProcedureDraft {
  type_id: string
  type_name: string
  performer: 'doctor' | 'doctor_or_nurse'
  requires_consent: boolean
  indication: string
  follow_up_days: number | null
  /** Catalog price when indicated ("25.00"); null: no price. */
  price: string | null
  /** Included in the consultation fee (charged nothing). */
  included: boolean
}

// ── Platform monitoring ──────────────────────────────────────────────────────

export interface LockedLogin {
  scope: 'tenant' | 'platform'
  clinic_slug: string | null
  email: string
  failed_count: number
  locked_until: string
}

export interface ActiveImpersonation {
  session_id: string
  admin_name: string | null
  tenant_id: string | null
  clinic_name: string | null
  started_at: string
  expires_at: string
  ip_address: string | null
}

export interface ErrorGroup {
  method: string
  route: string
  error_type: string
  location: string
  count: number
  last_at: string
  first_at: string | null
  first_commit: string | null
  last_commit: string | null
}

export interface ConsoleLogin {
  admin_name: string | null
  action: 'auth.platform_login' | 'auth.platform_login_failed' | 'auth.platform_login_locked'
  at: string
  ip_address: string | null
  user_agent: string | null
}

export type JobState = 'ok' | 'failed' | 'overdue' | 'never'

export interface ScheduledJob {
  job: string
  state: JobState
  expected_every_hours: number | null
  last_started_at: string | null
  last_finished_at: string | null
  last_ok: boolean | null
  last_detail: string | null
  last_success_at: string | null
}

export interface SystemStatus {
  now: string
  runtime: {
    version: string
    commit: string | null
    environment: string
    python: string
    started_at: string
    uptime_seconds: number
  }
  database: {
    version: string
    size_bytes: number
    revision: string | null
    latency_ms: number
    connections: {
      total: number
      active: number
      idle: number
      idle_in_transaction: number
      max_connections: number
    }
  }
  largest_tables: { name: string; size_bytes: number; rows: number }[]
  logins: {
    failing_accounts: number
    failed_attempts: number
    lockouts_24h: number
    locked: LockedLogin[]
    console: ConsoleLogin[]
  }
  sessions: { tenant: number; support: number; platform: number }
  impersonations: ActiveImpersonation[]
  errors: {
    last_24h: number
    last_7d: number
    retention_days: number
    groups: ErrorGroup[]
    daily: { day: string; count: number }[]
  }
  jobs: ScheduledJob[]
  performance: Performance
}

export interface RoutePerformance {
  method: string
  route: string
  count: number
  client_errors: number
  server_errors: number
  avg_ms: number
  p95_ms: number | null
  max_ms: number
}

export interface Performance {
  window_hours: number
  requests: number
  client_errors: number
  server_errors: number
  p50_ms: number | null
  p95_ms: number | null
  slowest: RoutePerformance[]
  hourly: { hour: string; count: number; server_errors: number }[]
}

export interface ErrorEvent {
  id: string
  occurred_at: string
  method: string
  route: string
  status: number
  error_type: string
  location: string
  commit: string | null
}

