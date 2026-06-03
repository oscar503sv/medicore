"""Domain enums.

String-valued enums so they serialize cleanly and read well in logs/DB. Values match the
``DOMAIN_MODEL.md`` specification verbatim.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    RECEPTIONIST = "receptionist"


class UserStatus(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"
    SUSPENDED = "suspended"


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class IcdVersion(StrEnum):
    CIE10 = "cie10"
    CIE11 = "cie11"


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class PatientStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class AppointmentType(StrEnum):
    CONSULT = "consult"
    FOLLOW_UP = "follow_up"
    CHECK_UP = "check_up"
    PROCEDURE = "procedure"
    EMERGENCY = "emergency"


class AppointmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class RecordType(StrEnum):
    """Kind of clinical document a signed record represents (document type, not specialty)."""

    EVOLUTION = "evolution"
    EMERGENCY_NOTE = "emergency_note"
    PROCEDURE_NOTE = "procedure_note"
    SURGICAL_NOTE = "surgical_note"
    LAB_REPORT = "lab_report"
    IMAGING_REPORT = "imaging_report"
    DIAGNOSIS = "diagnosis"
    PRESCRIPTION_NOTE = "prescription_note"
    VACCINATION = "vaccination"
    REFERRAL = "referral"
    DISCHARGE_SUMMARY = "discharge_summary"
    NURSING_NOTE = "nursing_note"
    GENERIC = "generic"


class RecordStatus(StrEnum):
    DRAFT = "draft"
    SIGNED = "signed"
    AMENDED = "amended"


class PrescriptionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DocumentKind(StrEnum):
    LAB = "lab"
    IMAGING = "imaging"
    RX = "rx"
    CONSENT = "consent"
    OTHER = "other"


class AvailabilityExceptionKind(StrEnum):
    OFF = "off"
    EXTRA = "extra"


class NotificationChannel(StrEnum):
    EMAIL = "email"
    PUSH = "push"
    SMS = "sms"
    NONE = "none"


class ThemePref(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class LangPref(StrEnum):
    ES = "es"
    EN = "en"


class ConsultationStatus(StrEnum):
    DRAFT = "draft"
    SIGNED = "signed"
