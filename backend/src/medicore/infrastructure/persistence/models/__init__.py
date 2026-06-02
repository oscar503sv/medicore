"""ORM models — import all so Alembic autogenerate picks them up."""

from medicore.infrastructure.persistence.models.appointment import AppointmentModel
from medicore.infrastructure.persistence.models.audit_log import AuditLogModel
from medicore.infrastructure.persistence.models.availability import (
    AvailabilityExceptionModel,
    DoctorAvailabilityModel,
)
from medicore.infrastructure.persistence.models.consultation import ConsultationModel
from medicore.infrastructure.persistence.models.counters import TenantCounterModel
from medicore.infrastructure.persistence.models.insurer import InsurerModel
from medicore.infrastructure.persistence.models.medical_document import MedicalDocumentModel
from medicore.infrastructure.persistence.models.medical_record import MedicalRecordModel
from medicore.infrastructure.persistence.models.notification import NotificationModel
from medicore.infrastructure.persistence.models.patient import PatientModel
from medicore.infrastructure.persistence.models.platform import (
    PlatformAdminModel,
    PlatformAuditLogModel,
)
from medicore.infrastructure.persistence.models.prescription import PrescriptionModel
from medicore.infrastructure.persistence.models.tenant import LocationModel, TenantModel
from medicore.infrastructure.persistence.models.user import DoctorProfileModel, UserModel

__all__ = [
    "AppointmentModel",
    "AuditLogModel",
    "AvailabilityExceptionModel",
    "ConsultationModel",
    "DoctorAvailabilityModel",
    "DoctorProfileModel",
    "InsurerModel",
    "LocationModel",
    "MedicalDocumentModel",
    "MedicalRecordModel",
    "NotificationModel",
    "PatientModel",
    "PlatformAdminModel",
    "PlatformAuditLogModel",
    "PrescriptionModel",
    "TenantCounterModel",
    "TenantModel",
    "UserModel",
]
