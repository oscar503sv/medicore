"""Repository interfaces (ports).

Implementations live in the infrastructure layer (fase 3). Every repository is tenant-scoped
by construction — see ``_support`` for the multi-tenant contract.
"""

from medicore.domain.repositories._support import (
    Page,
    Paging,
    PatientFilter,
    RecordFilter,
    UserFilter,
)
from medicore.domain.repositories.appointment_repository import AppointmentRepository
from medicore.domain.repositories.audit_log_repository import AuditLogRepository
from medicore.domain.repositories.consultation_repository import ConsultationRepository
from medicore.domain.repositories.doctor_availability_repository import (
    DoctorAvailabilityRepository,
)
from medicore.domain.repositories.medical_document_repository import (
    MedicalDocumentRepository,
)
from medicore.domain.repositories.medical_record_repository import MedicalRecordRepository
from medicore.domain.repositories.notification_repository import NotificationRepository
from medicore.domain.repositories.patient_repository import PatientRepository
from medicore.domain.repositories.prescription_repository import PrescriptionRepository
from medicore.domain.repositories.tenant_repository import TenantRepository
from medicore.domain.repositories.user_repository import (
    DoctorProfileRepository,
    UserRepository,
)

__all__ = [
    "Page",
    "Paging",
    "PatientFilter",
    "RecordFilter",
    "UserFilter",
    "AppointmentRepository",
    "AuditLogRepository",
    "ConsultationRepository",
    "DoctorAvailabilityRepository",
    "MedicalDocumentRepository",
    "MedicalRecordRepository",
    "NotificationRepository",
    "PatientRepository",
    "PrescriptionRepository",
    "TenantRepository",
    "DoctorProfileRepository",
    "UserRepository",
]
