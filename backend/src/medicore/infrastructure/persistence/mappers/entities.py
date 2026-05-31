"""ORM → domain entity mappers for all aggregates."""

from __future__ import annotations

from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.notification import Notification
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.prescription import Prescription
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.entities.user import DoctorProfile, User
from medicore.domain.enums import (
    AppointmentStatus,
    AppointmentType,
    ConsultationStatus,
    DocumentKind,
    LangPref,
    NotificationChannel,
    PatientStatus,
    PrescriptionStatus,
    RecordStatus,
    RecordType,
    Role,
    Sex,
    ThemePref,
    UserStatus,
)
from medicore.domain.shared.identifiers import (
    AppointmentId,
    AuditLogId,
    ConsultationId,
    DoctorProfileId,
    DocumentId,
    LocationId,
    NotificationId,
    PatientId,
    PrescriptionId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.blood_type import BloodType
from medicore.domain.value_objects.contact_info import ContactInfo
from medicore.domain.value_objects.slug import Slug
from medicore.domain.value_objects.user_preferences import (
    NotificationPreferences,
    UserPreferences,
)
from medicore.infrastructure.persistence.mappers._json import (
    dict_to_attachment,
    dict_to_diagnoses,
    dict_to_draft,
    dict_to_snapshot,
    dict_to_soap,
    dict_to_vaccine,
    dict_to_vitals,
)
from medicore.infrastructure.persistence.models.appointment import AppointmentModel
from medicore.infrastructure.persistence.models.audit_log import AuditLogModel
from medicore.infrastructure.persistence.models.consultation import ConsultationModel
from medicore.infrastructure.persistence.models.medical_document import MedicalDocumentModel
from medicore.infrastructure.persistence.models.medical_record import MedicalRecordModel
from medicore.infrastructure.persistence.models.notification import NotificationModel
from medicore.infrastructure.persistence.models.patient import PatientModel
from medicore.infrastructure.persistence.models.prescription import PrescriptionModel
from medicore.infrastructure.persistence.models.tenant import LocationModel, TenantModel
from medicore.infrastructure.persistence.models.user import DoctorProfileModel, UserModel


def to_location(row: LocationModel) -> Location:
    return Location(
        id=LocationId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        name=row.name,
        address=row.address,
        is_primary=row.is_primary,
    )


def to_tenant(row: TenantModel) -> Tenant:
    locations = [to_location(loc) for loc in (row.locations or [])]
    return Tenant(
        id=TenantId.parse(row.id),
        legal_name=row.legal_name,
        tax_id=row.tax_id,
        slug=Slug(row.slug),
        timezone=row.timezone,
        plan=row.plan,
        seat_limit=row.seat_limit,
        locations=locations,
        created_at=row.created_at,
    )


def _prefs_from_json(d: dict) -> UserPreferences:
    n = d.get("notifications", {})
    return UserPreferences(
        theme=ThemePref(d.get("theme", "system")),
        language=LangPref(d.get("language", "es")),
        notifications=NotificationPreferences(
            appointments=NotificationChannel(n.get("appointments", "email")),
            reminders=NotificationChannel(n.get("reminders", "email")),
            lab_results=NotificationChannel(n.get("lab_results", "email")),
            internal_messages=NotificationChannel(n.get("internal_messages", "push")),
            weekly_reports=NotificationChannel(n.get("weekly_reports", "none")),
        ),
    )


def to_user(row: UserModel) -> User:
    return User(
        id=UserId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        name=row.name,
        email=row.email,
        password_hash=row.password_hash,
        role=Role(row.role),
        status=UserStatus(row.status),
        specialty=row.specialty,
        phone=row.phone,
        preferences=_prefs_from_json(row.preferences or {}),
        last_seen_at=row.last_seen_at,
        joined_at=row.joined_at,
    )


def to_doctor_profile(row: DoctorProfileModel) -> DoctorProfile:
    return DoctorProfile(
        id=DoctorProfileId.parse(row.id),
        user_id=UserId.parse(row.user_id),
        tenant_id=TenantId.parse(row.tenant_id),
        bio=row.bio,
        default_location_id=LocationId.parse(row.default_location_id)
        if row.default_location_id
        else None,
    )


def to_patient(row: PatientModel) -> Patient:
    return Patient(
        id=PatientId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        code=row.code,
        first_name=row.first_name,
        last_name=row.last_name,
        sex=Sex(row.sex),
        date_of_birth=row.date_of_birth,
        blood_type=BloodType(row.blood_type) if row.blood_type else None,
        insurance=row.insurance,
        primary_doctor_id=UserId.parse(row.primary_doctor_id) if row.primary_doctor_id else None,
        status=PatientStatus(row.status),
        tags=list(row.tags or []),
        allergies=list(row.allergies or []),
        contact=_contact_from_json(row.contact or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _contact_from_json(d: dict) -> ContactInfo:
    return ContactInfo(
        phone=d.get("phone"),
        email=d.get("email"),
        address=d.get("address"),
        emergency_contact_name=d.get("emergency_contact_name"),
        emergency_contact_phone=d.get("emergency_contact_phone"),
    )


def to_appointment(row: AppointmentModel) -> Appointment:
    return Appointment(
        id=AppointmentId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        code=row.code,
        patient_id=PatientId.parse(row.patient_id),
        doctor_id=UserId.parse(row.doctor_id),
        location_id=LocationId.parse(row.location_id),
        type=AppointmentType(row.type),
        status=AppointmentStatus(row.status),
        scheduled_start=row.scheduled_start,
        duration_minutes=row.duration_minutes,
        reason=row.reason,
        room=row.room,
        created_by_id=UserId.parse(row.created_by_id),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def to_consultation(row: ConsultationModel) -> Consultation:
    return Consultation(
        id=ConsultationId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        appointment_id=AppointmentId.parse(row.appointment_id),
        patient_id=PatientId.parse(row.patient_id),
        doctor_id=UserId.parse(row.doctor_id),
        status=ConsultationStatus(row.status),
        started_at=row.started_at,
        ended_at=row.ended_at,
        vitals=dict_to_vitals(row.vitals or {}),
        soap=dict_to_soap(row.soap or {}),
        diagnoses=[d for d in dict_to_diagnoses(row.diagnoses or [])],  # list for mutability
        draft_prescriptions=[dict_to_draft(d) for d in (row.draft_prescriptions or [])],
        attachments=[dict_to_attachment(a) for a in (row.attachments or [])],
        last_saved_at=row.last_saved_at,
    )


def to_medical_record(row: MedicalRecordModel) -> MedicalRecord:
    return MedicalRecord(
        id=RecordId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        code=row.code,
        patient_id=PatientId.parse(row.patient_id),
        author_id=UserId.parse(row.author_id),
        type=RecordType(row.type),
        status=RecordStatus(row.status),
        encounter_at=row.encounter_at,
        location_name=row.location_name,
        chief_complaint=row.chief_complaint,
        soap=dict_to_soap(row.soap or {}),
        vitals=dict_to_vitals(row.vitals or {}),
        diagnoses=dict_to_diagnoses(row.diagnoses or []),
        prescriptions=tuple(dict_to_snapshot(p) for p in (row.prescriptions or [])),
        vaccines=tuple(dict_to_vaccine(v) for v in (row.vaccines or [])),
        attachments=tuple(dict_to_attachment(a) for a in (row.attachments or [])),
        signed_at=row.signed_at,
        signed_by_id=UserId.parse(row.signed_by_id),
        appointment_id=AppointmentId.parse(row.appointment_id) if row.appointment_id else None,
        consultation_id=ConsultationId.parse(row.consultation_id) if row.consultation_id else None,
        amends_record_id=RecordId.parse(row.amends_record_id) if row.amends_record_id else None,
    )


def to_prescription(row: PrescriptionModel) -> Prescription:
    return Prescription(
        id=PrescriptionId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        patient_id=PatientId.parse(row.patient_id),
        prescriber_id=UserId.parse(row.prescriber_id),
        drug=row.drug,
        dose=row.dose,
        schedule=row.schedule,
        start_date=row.start_date,
        end_date=row.end_date,
        duration_days=row.duration_days,
        status=PrescriptionStatus(row.status),
        record_id=RecordId.parse(row.record_id) if row.record_id else None,
        created_at=row.created_at,
    )


def to_medical_document(row: MedicalDocumentModel) -> MedicalDocument:
    return MedicalDocument(
        id=DocumentId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        patient_id=PatientId.parse(row.patient_id),
        file_name=row.file_name,
        kind=DocumentKind(row.kind),
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        storage_key=row.storage_key,
        uploaded_by_id=UserId.parse(row.uploaded_by_id),
        uploaded_at=row.uploaded_at,
        record_id=RecordId.parse(row.record_id) if row.record_id else None,
    )


def to_notification(row: NotificationModel) -> Notification:
    return Notification(
        id=NotificationId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        user_id=UserId.parse(row.user_id),
        type=row.type,
        title=row.title,
        body=row.body,
        read_at=row.read_at,
        created_at=row.created_at,
    )


def to_audit_log(row: AuditLogModel) -> AuditLog:
    return AuditLog(
        id=AuditLogId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        actor_id=UserId.parse(row.actor_id),
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        metadata=dict(row.metadata_ or {}),
        timestamp=row.timestamp,
    )
