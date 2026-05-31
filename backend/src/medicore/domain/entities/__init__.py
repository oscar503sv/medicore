"""Domain entities and aggregates."""

from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.availability import (
    AvailabilityException,
    BookingRules,
    DoctorAvailability,
    WeeklyDay,
)
from medicore.domain.entities.consultation import Consultation, SignResult
from medicore.domain.entities.medical_document import AttachmentRef, MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord, VaccineAdministration
from medicore.domain.entities.notification import Notification
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.prescription import (
    Prescription,
    PrescriptionDraft,
    PrescriptionSnapshot,
)
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.entities.user import DoctorProfile, User, derive_initials

__all__ = [
    "Appointment",
    "AuditLog",
    "AvailabilityException",
    "BookingRules",
    "DoctorAvailability",
    "WeeklyDay",
    "Consultation",
    "SignResult",
    "AttachmentRef",
    "MedicalDocument",
    "MedicalRecord",
    "VaccineAdministration",
    "Notification",
    "Patient",
    "Prescription",
    "PrescriptionDraft",
    "PrescriptionSnapshot",
    "Location",
    "Tenant",
    "DoctorProfile",
    "User",
    "derive_initials",
]
