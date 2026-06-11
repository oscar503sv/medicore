"""In-memory data store shared by the fake repositories and unit of work."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from uuid import UUID

from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.diagnosis_catalog import CatalogDiagnosis
from medicore.domain.entities.insurer import Insurer
from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.notification import Notification
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.entities.platform_audit_log import PlatformAuditLog
from medicore.domain.entities.prescription import Prescription
from medicore.domain.entities.role_permission_override import RolePermissionOverride
from medicore.domain.entities.tenant import Tenant
from medicore.domain.entities.user import DoctorProfile, User


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
    appointments: dict[UUID, Appointment] = field(default_factory=dict)
    consultations: dict[UUID, Consultation] = field(default_factory=dict)
    medical_records: dict[UUID, MedicalRecord] = field(default_factory=dict)
    prescriptions: dict[UUID, Prescription] = field(default_factory=dict)
    documents: dict[UUID, MedicalDocument] = field(default_factory=dict)
    availability: dict[UUID, DoctorAvailability] = field(default_factory=dict)
    notifications: dict[UUID, Notification] = field(default_factory=dict)
    audit: dict[UUID, AuditLog] = field(default_factory=dict)
    role_permission_overrides: dict[UUID, RolePermissionOverride] = field(default_factory=dict)
    platform_admins: dict[UUID, PlatformAdmin] = field(default_factory=dict)
    platform_audit: dict[UUID, PlatformAuditLog] = field(default_factory=dict)
    # Global catalog keyed by "version:code" (reference data, not tenant-scoped).
    diagnosis_codes: dict[str, CatalogDiagnosis] = field(default_factory=dict)
    # Global login throttle keyed by identifier: (failed_count, last_failed_at, locked_until).
    login_attempts: dict[str, tuple] = field(default_factory=dict)

    def snapshot(self) -> dict[str, dict]:
        return {f.name: copy.deepcopy(getattr(self, f.name)) for f in fields(self)}

    def restore(self, snap: dict[str, dict]) -> None:
        for name, data in snap.items():
            store: dict = getattr(self, name)
            store.clear()
            store.update(data)
