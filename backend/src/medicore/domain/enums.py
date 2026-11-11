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


class ClinicalRecordType(StrEnum):
    """Kind of clinical event a signed record represents.

    Each value is produced automatically by its own flow — never chosen by hand. Today only
    ``CONSULTATION`` is emitted (when a consultation is signed); the rest are reserved for
    future modules (applications, procedures, vaccination, lab/imaging results, discharge).
    """

    CONSULTATION = "consultation"
    PROCEDURE = "procedure"
    MEDICATION_APPLICATION = "medication_application"
    VACCINATION = "vaccination"
    LAB_RESULT = "lab_result"
    IMAGING_RESULT = "imaging_result"
    DISCHARGE_SUMMARY = "discharge_summary"


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


class VaccinationOutcome(StrEnum):
    """What happened with a dose: given, declined by the patient, or medically not given."""

    ADMINISTERED = "administered"
    REFUSED = "refused"
    CONTRAINDICATED = "contraindicated"


class VaccinationSource(StrEnum):
    """Where the dose was given: here (lot/route traceable) or elsewhere (from the carnet)."""

    CLINIC = "clinic"
    EXTERNAL = "external"


class VaccineRoute(StrEnum):
    INTRAMUSCULAR = "im"
    SUBCUTANEOUS = "sc"
    INTRADERMAL = "id"
    ORAL = "oral"


class InjectionSite(StrEnum):
    LEFT_ARM = "left_arm"
    RIGHT_ARM = "right_arm"
    LEFT_THIGH = "left_thigh"
    RIGHT_THIGH = "right_thigh"
    MOUTH = "mouth"


class ApplicationRoute(StrEnum):
    """How a medication is given in the clinic (injections, IV, nebulization…)."""

    INTRAMUSCULAR = "im"
    INTRAVENOUS = "iv"
    SUBCUTANEOUS = "sc"
    INTRADERMAL = "id"
    NEBULIZED = "nebulized"
    ORAL = "oral"
    TOPICAL = "topical"


class ApplicationOrderSource(StrEnum):
    """Who ordered it: a doctor of this clinic (from a consultation) or an outside one."""

    INTERNAL = "internal"
    EXTERNAL = "external"


class ApplicationOrderStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ApplicationOutcome(StrEnum):
    APPLIED = "applied"
    REFUSED = "refused"
    CONTRAINDICATED = "contraindicated"


class ApplicationSite(StrEnum):
    LEFT_ARM = "left_arm"
    RIGHT_ARM = "right_arm"
    LEFT_GLUTEUS = "left_gluteus"
    RIGHT_GLUTEUS = "right_gluteus"
    LEFT_THIGH = "left_thigh"
    RIGHT_THIGH = "right_thigh"
    LEFT_HAND = "left_hand"
    RIGHT_HAND = "right_hand"
    LEFT_FOREARM = "left_forearm"
    RIGHT_FOREARM = "right_forearm"
    ABDOMEN = "abdomen"


class ProcedurePerformer(StrEnum):
    """Who may perform a procedure type (configured per clinic in the catalog)."""

    DOCTOR = "doctor"
    DOCTOR_OR_NURSE = "doctor_or_nurse"


class ProcedureStatus(StrEnum):
    PENDING = "pending"  # ordered, nothing recorded yet
    IN_PROGRESS = "in_progress"  # checklist / consent / note being filled
    COMPLETED = "completed"  # note signed: immutable, corrected only by amendments
    CANCELLED = "cancelled"


class ProcedureSource(StrEnum):
    """Where the order came from: a signed consultation, or registered directly (walk-in or
    a procedure appointment)."""

    CONSULTATION = "consultation"
    DIRECT = "direct"


# ── Subscriptions ─────────────────────────────────────────────────────────────


class AddonModule(StrEnum):
    """Optional modules a clinic contracts on top of its plan."""

    VACCINATION = "vaccination"
    APPLICATIONS = "applications"
    PROCEDURES = "procedures"
    # Advanced analytics: raises the clinic to the operations tier. Not a clinical module,
    # so it is not part of the clinical-modules bundle.
    ANALYTICS = "analytics"


# The clinical modules, sold together at the bundle price.
CLINICAL_MODULES = frozenset(
    {AddonModule.VACCINATION, AddonModule.APPLICATIONS, AddonModule.PROCEDURES}
)


class AnalyticsTier(StrEnum):
    """How much of the dashboard and reports a clinic gets, from least to most: its plan
    decides, and the analytics add-on raises it to operations."""

    BASIC = "basic"  # the doctor's own figures: agenda, patients, attendance
    CLINIC = "clinic"  # the whole clinic: per doctor, estimated income, trends
    OPERATIONS = "operations"  # operational metrics: occupancy, no-shows, waits, modules

    @property
    def rank(self) -> int:
        return list(AnalyticsTier).index(self)

    def includes(self, other: AnalyticsTier) -> bool:
        return self.rank >= other.rank


class PlanFeature(StrEnum):
    """Capabilities that differ between plans (beyond their quotas)."""

    USER_PERMISSIONS = "user_permissions"  # per-user permission overrides


class PaymentMethod(StrEnum):
    """How a clinic paid its subscription (recorded by hand from the console)."""

    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
    CARD = "card"
    OTHER = "other"


class SubscriptionStatus(StrEnum):
    """Derived from the paid/trial period and the grace days, never stored."""

    TRIAL = "trial"
    ACTIVE = "active"
    GRACE = "grace"  # expired, still fully usable while the grace days last
    READ_ONLY = "read_only"  # grace over: data can be read, nothing written
