"""In-memory data store shared by the fake repositories and unit of work."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from uuid import UUID

from medicore.domain.entities.application import ApplicationOrder, ApplicationRecord
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.diagnosis_catalog import CatalogDiagnosis
from medicore.domain.entities.error_event import ErrorEvent
from medicore.domain.entities.fee_schedule import FeeSchedule
from medicore.domain.entities.insurer import Insurer
from medicore.domain.entities.job_run import JobRun
from medicore.domain.entities.medical_certificate import MedicalCertificate
from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.note_template import CustomNoteTemplate
from medicore.domain.entities.notification import Notification
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.plan import AddonPricing, Plan
from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.entities.platform_audit_log import PlatformAuditLog
from medicore.domain.entities.prescription import Prescription
from medicore.domain.entities.procedure import Procedure, ProcedureType
from medicore.domain.entities.role_permission_override import RolePermissionOverride
from medicore.domain.entities.subscription_payment import SubscriptionPayment
from medicore.domain.entities.tenant import Tenant
from medicore.domain.entities.user import DoctorProfile, User
from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.repositories._support import RequestStatsRow
from medicore.domain.services.plan_catalog import default_addon_pricing, default_plans


@dataclass
class InMemoryStore:
    """Holds every aggregate keyed by the UUID inside its identifier.

    ``snapshot``/``restore`` give the unit of work real transactional rollback so tests can
    assert that a failed multi-aggregate operation leaves nothing behind.
    """

    tenants: dict[UUID, Tenant] = field(default_factory=dict)
    users: dict[UUID, User] = field(default_factory=dict)
    doctor_profiles: dict[UUID, DoctorProfile] = field(default_factory=dict)
    patients: dict[UUID, Patient] = field(default_factory=dict)
    insurers: dict[UUID, Insurer] = field(default_factory=dict)
    note_templates: dict[UUID, CustomNoteTemplate] = field(default_factory=dict)
    appointments: dict[UUID, Appointment] = field(default_factory=dict)
    consultations: dict[UUID, Consultation] = field(default_factory=dict)
    medical_records: dict[UUID, MedicalRecord] = field(default_factory=dict)
    prescriptions: dict[UUID, Prescription] = field(default_factory=dict)
    documents: dict[UUID, MedicalDocument] = field(default_factory=dict)
    availability: dict[UUID, DoctorAvailability] = field(default_factory=dict)
    fees: dict[UUID, FeeSchedule] = field(default_factory=dict)
    certificates: dict[UUID, MedicalCertificate] = field(default_factory=dict)
    notifications: dict[UUID, Notification] = field(default_factory=dict)
    audit: dict[UUID, AuditLog] = field(default_factory=dict)
    role_permission_overrides: dict[UUID, RolePermissionOverride] = field(default_factory=dict)
    vaccinations: dict[UUID, VaccinationRecord] = field(default_factory=dict)
    application_orders: dict[UUID, ApplicationOrder] = field(default_factory=dict)
    application_records: dict[UUID, ApplicationRecord] = field(default_factory=dict)
    procedure_types: dict[UUID, ProcedureType] = field(default_factory=dict)
    procedures: dict[UUID, Procedure] = field(default_factory=dict)
    platform_admins: dict[UUID, PlatformAdmin] = field(default_factory=dict)
    platform_audit: dict[UUID, PlatformAuditLog] = field(default_factory=dict)
    # Global catalog keyed by "version:code" (reference data, not tenant-scoped).
    diagnosis_codes: dict[str, CatalogDiagnosis] = field(default_factory=dict)
    # Global login throttle keyed by identifier: (failed_count, last_failed_at, locked_until).
    login_attempts: dict[str, tuple] = field(default_factory=dict)
    # Global revocable sessions (tenant and platform scopes share the store).
    sessions: dict[UUID, AuthSession] = field(default_factory=dict)
    # Recorded server errors (platform monitoring).
    error_events: dict[UUID, ErrorEvent] = field(default_factory=dict)
    job_runs: dict[UUID, JobRun] = field(default_factory=dict)
    # Hourly request metrics keyed by (hour, method, route).
    request_stats: dict[tuple, RequestStatsRow] = field(default_factory=dict)
    # Global subscription catalog, starting from the published price list.
    subscription_payments: dict[UUID, SubscriptionPayment] = field(default_factory=dict)
    plans: dict[str, Plan] = field(default_factory=lambda: {p.code: p for p in default_plans()})
    addon_pricing: dict[str, AddonPricing] = field(
        default_factory=lambda: {"current": default_addon_pricing()}
    )

    # Simulated outage for readiness tests (not transactional state).
    database_down = False

    def snapshot(self) -> dict[str, dict]:
        return {f.name: copy.deepcopy(getattr(self, f.name)) for f in fields(self)}

    def restore(self, snap: dict[str, dict]) -> None:
        for name, data in snap.items():
            store: dict = getattr(self, name)
            store.clear()
            store.update(data)
