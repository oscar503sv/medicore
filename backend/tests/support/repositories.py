"""In-memory repository implementations backed by an :class:`InMemoryStore`.

Each repo is tenant-scoped (constructed with a ``tenant_id``) and filters accordingly, so the
fakes exercise the same multi-tenant contract the real ORM repos will honor in fase 3.
``TenantRepository`` is the exception: it is global.
"""

from __future__ import annotations

from datetime import date, datetime

from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.notification import Notification
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.prescription import Prescription
from medicore.domain.entities.tenant import Tenant
from medicore.domain.entities.user import DoctorProfile, User
from medicore.domain.enums import AppointmentStatus
from medicore.domain.repositories._support import (
    Page,
    Paging,
    PatientFilter,
    RecordFilter,
    UserFilter,
)
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    DocumentId,
    NotificationId,
    PatientId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.slug import Slug
from tests.support.store import InMemoryStore

_ACTIVE_APPOINTMENTS = {
    AppointmentStatus.SCHEDULED,
    AppointmentStatus.CONFIRMED,
    AppointmentStatus.IN_PROGRESS,
}


def _paginate(items: list, paging: Paging | None) -> Page:
    paging = paging or Paging()
    window = items[paging.offset : paging.offset + paging.limit]
    return Page(items=window, total=len(items), offset=paging.offset, limit=paging.limit)


class InMemoryTenantRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def get_by_id(self, tenant_id: TenantId) -> Tenant | None:
        return self._store.tenants.get(tenant_id.value)

    def get_by_slug(self, slug: Slug) -> Tenant | None:
        return next((t for t in self._store.tenants.values() if t.slug == slug), None)

    def save(self, tenant: Tenant) -> None:
        self._store.tenants[tenant.id.value] = tenant


class _Scoped:
    def __init__(self, store: InMemoryStore, tenant_id: TenantId) -> None:
        self._store = store
        self._tenant = tenant_id

    def _mine(self, items) -> list:
        return [e for e in items if e.tenant_id == self._tenant]


class InMemoryUserRepository(_Scoped):
    def get_by_id(self, user_id: UserId) -> User | None:
        user = self._store.users.get(user_id.value)
        return user if user and user.tenant_id == self._tenant else None

    def get_by_email(self, email: str) -> User | None:
        target = email.strip().lower()
        return next(
            (u for u in self._mine(self._store.users.values()) if u.email.lower() == target),
            None,
        )

    def list(self, filter: UserFilter | None = None, paging: Paging | None = None) -> Page[User]:
        users = self._mine(self._store.users.values())
        if filter and filter.role:
            users = [u for u in users if str(u.role) == filter.role]
        if filter and filter.status:
            users = [u for u in users if str(u.status) == filter.status]
        users.sort(key=lambda u: u.name)
        return _paginate(users, paging)

    def save(self, user: User) -> None:
        self._store.users[user.id.value] = user


class InMemoryDoctorProfileRepository(_Scoped):
    def get_by_user_id(self, user_id: UserId) -> DoctorProfile | None:
        return next(
            (
                p
                for p in self._mine(self._store.doctor_profiles.values())
                if p.user_id == user_id
            ),
            None,
        )

    def save(self, profile: DoctorProfile) -> None:
        self._store.doctor_profiles[profile.id.value] = profile


class InMemoryPatientRepository(_Scoped):
    def get_by_id(self, patient_id: PatientId) -> Patient | None:
        p = self._store.patients.get(patient_id.value)
        return p if p and p.tenant_id == self._tenant else None

    def list(
        self, filter: PatientFilter | None = None, paging: Paging | None = None
    ) -> Page[Patient]:
        patients = self._mine(self._store.patients.values())
        if filter and filter.status:
            patients = [p for p in patients if str(p.status) == filter.status]
        if filter and filter.doctor_id:
            patients = [
                p
                for p in patients
                if p.primary_doctor_id and str(p.primary_doctor_id) == filter.doctor_id
            ]
        if filter and filter.tags:
            patients = [p for p in patients if set(filter.tags).issubset(p.tags)]
        patients.sort(key=lambda p: (p.last_name, p.first_name))
        return _paginate(patients, paging)

    def search(self, query: str, paging: Paging | None = None) -> Page[Patient]:
        q = query.strip().lower()
        matches = [
            p
            for p in self._mine(self._store.patients.values())
            if q in p.full_name.lower() or q in p.code.lower()
        ]
        matches.sort(key=lambda p: (p.last_name, p.first_name))
        return _paginate(matches, paging)

    def save(self, patient: Patient) -> None:
        self._store.patients[patient.id.value] = patient


class InMemoryAppointmentRepository(_Scoped):
    def get_by_id(self, appointment_id: AppointmentId) -> Appointment | None:
        a = self._store.appointments.get(appointment_id.value)
        return a if a and a.tenant_id == self._tenant else None

    def list_by_day(self, on: date, doctor_id: UserId | None = None) -> list[Appointment]:
        result = [
            a
            for a in self._mine(self._store.appointments.values())
            if a.scheduled_start.date() == on
            and (doctor_id is None or a.doctor_id == doctor_id)
        ]
        result.sort(key=lambda a: a.scheduled_start)
        return result

    def list_by_patient(self, patient_id: PatientId) -> list[Appointment]:
        result = [
            a for a in self._mine(self._store.appointments.values()) if a.patient_id == patient_id
        ]
        result.sort(key=lambda a: a.scheduled_start)
        return result

    def find_overlapping(
        self, doctor_id: UserId, start: datetime, end: datetime
    ) -> list[Appointment]:
        return [
            a
            for a in self._mine(self._store.appointments.values())
            if a.doctor_id == doctor_id
            and a.status in _ACTIVE_APPOINTMENTS
            and a.scheduled_start < end
            and start < a.scheduled_end
        ]

    def save(self, appointment: Appointment) -> None:
        self._store.appointments[appointment.id.value] = appointment


class InMemoryInsurerRepository(_Scoped):
    def get_by_id(self, insurer_id) -> object | None:
        ins = self._store.insurers.get(insurer_id.value)
        return ins if ins and ins.tenant_id == self._tenant else None

    def list(self, active_only: bool = False) -> list:
        result = [
            i
            for i in self._mine(self._store.insurers.values())
            if not active_only or i.active
        ]
        result.sort(key=lambda i: i.name)
        return result

    def save(self, insurer) -> None:
        self._store.insurers[insurer.id.value] = insurer


class InMemoryConsultationRepository(_Scoped):
    def get_by_id(self, consultation_id: ConsultationId) -> Consultation | None:
        c = self._store.consultations.get(consultation_id.value)
        return c if c and c.tenant_id == self._tenant else None

    def get_by_appointment(self, appointment_id: AppointmentId) -> Consultation | None:
        return next(
            (
                c
                for c in self._mine(self._store.consultations.values())
                if c.appointment_id == appointment_id
            ),
            None,
        )

    def save(self, consultation: Consultation) -> None:
        self._store.consultations[consultation.id.value] = consultation


class InMemoryMedicalRecordRepository(_Scoped):
    def get_by_id(self, record_id: RecordId) -> MedicalRecord | None:
        r = self._store.medical_records.get(record_id.value)
        return r if r and r.tenant_id == self._tenant else None

    def list_by_patient(self, patient_id: PatientId) -> list[MedicalRecord]:
        result = [
            r
            for r in self._mine(self._store.medical_records.values())
            if r.patient_id == patient_id
        ]
        result.sort(key=lambda r: r.encounter_at, reverse=True)
        return result

    def list(self, filter: RecordFilter | None = None) -> list[MedicalRecord]:
        records = self._mine(self._store.medical_records.values())
        if filter and filter.patient_id:
            records = [r for r in records if str(r.patient_id) == filter.patient_id]
        if filter and filter.type:
            records = [r for r in records if str(r.type) == filter.type]
        records.sort(key=lambda r: r.encounter_at, reverse=True)
        return records

    def save(self, record: MedicalRecord) -> None:
        self._store.medical_records[record.id.value] = record


class InMemoryPrescriptionRepository(_Scoped):
    def list_by_patient(
        self, patient_id: PatientId, active_only: bool = False
    ) -> list[Prescription]:
        from medicore.domain.enums import PrescriptionStatus

        result = [
            p
            for p in self._mine(self._store.prescriptions.values())
            if p.patient_id == patient_id
            and (not active_only or p.status == PrescriptionStatus.ACTIVE)
        ]
        result.sort(key=lambda p: p.start_date, reverse=True)
        return result

    def save(self, prescription: Prescription) -> None:
        self._store.prescriptions[prescription.id.value] = prescription


class InMemoryMedicalDocumentRepository(_Scoped):
    def list_by_patient(self, patient_id: PatientId) -> list[MedicalDocument]:
        result = [
            d for d in self._mine(self._store.documents.values()) if d.patient_id == patient_id
        ]
        result.sort(key=lambda d: d.uploaded_at, reverse=True)
        return result

    def save(self, document: MedicalDocument) -> None:
        self._store.documents[document.id.value] = document

    def delete(self, document_id: DocumentId) -> None:
        self._store.documents.pop(document_id.value, None)


class InMemoryDoctorAvailabilityRepository(_Scoped):
    def get_by_doctor(self, doctor_id: UserId) -> DoctorAvailability | None:
        return next(
            (
                a
                for a in self._mine(self._store.availability.values())
                if a.doctor_id == doctor_id
            ),
            None,
        )

    def save(self, availability: DoctorAvailability) -> None:
        self._store.availability[availability.id.value] = availability


class InMemoryNotificationRepository(_Scoped):
    def list_by_user(self, user_id: UserId, unread_only: bool = False) -> list[Notification]:
        result = [
            n
            for n in self._mine(self._store.notifications.values())
            if n.user_id == user_id and (not unread_only or not n.is_read)
        ]
        result.sort(key=lambda n: n.created_at, reverse=True)
        return result

    def mark_read(self, notification_id: NotificationId) -> None:
        n = self._store.notifications.get(notification_id.value)
        if n and n.tenant_id == self._tenant:
            n.mark_read()

    def save(self, notification: Notification) -> None:
        self._store.notifications[notification.id.value] = notification


class InMemoryAuditLogRepository(_Scoped):
    def append(self, entry: AuditLog) -> None:
        self._store.audit[entry.id.value] = entry

    def query(self, **criteria: object) -> list[AuditLog]:
        entries = self._mine(self._store.audit.values())
        for key, value in criteria.items():
            entries = [e for e in entries if getattr(e, key, None) == value]
        entries.sort(key=lambda e: e.timestamp)
        return entries
