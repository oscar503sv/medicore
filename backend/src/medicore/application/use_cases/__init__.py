"""Use cases (interactors) for the application layer."""

from medicore.application.use_cases.appointments import (
    CancelAppointment,
    ConfirmAppointment,
    CreateAppointment,
    CreateAppointmentCommand,
    GetAvailableSlots,
    GetWeeklySchedule,
    ListAppointmentsForDay,
    MarkNoShow,
    RescheduleAppointment,
)
from medicore.application.use_cases.auth import (
    AuthenticateUser,
    AuthenticateUserCommand,
    SessionDTO,
    SwitchLocale,
    SwitchTheme,
)
from medicore.application.use_cases.availability import (
    AddAvailabilityException,
    GetMyAvailability,
    PreviewAvailability,
    RemoveAvailabilityException,
    UpdateBookingRules,
    UpdateWeeklySchedule,
)
from medicore.application.use_cases.consultations import (
    AddDiagnosis,
    AddPrescriptionDraft,
    AttachDocument,
    AutosaveConsultation,
    ConsultationPatch,
    RemoveDiagnosis,
    RemovePrescriptionDraft,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.application.use_cases.organization import (
    AddLocation,
    GetOrganization,
    UpdateLocation,
    UpdateOrganization,
)
from medicore.application.use_cases.patients import (
    ArchivePatient,
    CreatePatient,
    CreatePatientCommand,
    GetPatientDetail,
    ListPatients,
    PatientDetailDTO,
    SearchPatients,
    UpdatePatient,
)
from medicore.application.use_cases.records import (
    AmendMedicalRecord,
    GetMedicalRecord,
    ListMedicalRecords,
    ListPatientDocuments,
    UploadDocument,
    UploadDocumentCommand,
)
from medicore.application.use_cases.users import (
    InviteUser,
    InviteUserCommand,
    ListUsers,
    SuspendUser,
    UpdateUserRole,
)

__all__ = [
    # auth
    "AuthenticateUser",
    "AuthenticateUserCommand",
    "SessionDTO",
    "SwitchLocale",
    "SwitchTheme",
    # patients
    "ArchivePatient",
    "CreatePatient",
    "CreatePatientCommand",
    "GetPatientDetail",
    "ListPatients",
    "PatientDetailDTO",
    "SearchPatients",
    "UpdatePatient",
    # appointments
    "CancelAppointment",
    "ConfirmAppointment",
    "CreateAppointment",
    "CreateAppointmentCommand",
    "GetAvailableSlots",
    "GetWeeklySchedule",
    "ListAppointmentsForDay",
    "MarkNoShow",
    "RescheduleAppointment",
    # consultations
    "AddDiagnosis",
    "AddPrescriptionDraft",
    "AttachDocument",
    "AutosaveConsultation",
    "ConsultationPatch",
    "RemoveDiagnosis",
    "RemovePrescriptionDraft",
    "SignConsultation",
    "SignConsultationCommand",
    "StartConsultation",
    # records / documents
    "AmendMedicalRecord",
    "GetMedicalRecord",
    "ListMedicalRecords",
    "ListPatientDocuments",
    "UploadDocument",
    "UploadDocumentCommand",
    # availability
    "AddAvailabilityException",
    "GetMyAvailability",
    "PreviewAvailability",
    "RemoveAvailabilityException",
    "UpdateBookingRules",
    "UpdateWeeklySchedule",
    # users
    "InviteUser",
    "InviteUserCommand",
    "ListUsers",
    "SuspendUser",
    "UpdateUserRole",
    # organization
    "AddLocation",
    "GetOrganization",
    "UpdateLocation",
    "UpdateOrganization",
]
