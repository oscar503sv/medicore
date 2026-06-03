"""Patient use cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.timezone import clinic_now, to_naive
from medicore.application.ports.clock import Clock
from medicore.application.ports.code_generator import CodeGenerator
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.patient import Patient
from medicore.domain.enums import AppointmentStatus, PrescriptionStatus, Sex
from medicore.domain.repositories._support import Page, Paging, PatientFilter
from medicore.domain.shared.identifiers import PatientId, UserId
from medicore.domain.value_objects.blood_type import BloodType
from medicore.domain.value_objects.contact_info import ContactInfo


@dataclass(frozen=True, slots=True)
class CreatePatientCommand:
    first_name: str
    last_name: str
    sex: Sex
    date_of_birth: date
    contact: ContactInfo = field(default_factory=ContactInfo)
    blood_type: BloodType | None = None
    primary_doctor_id: UserId | None = None
    tags: tuple[str, ...] = ()
    allergies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PatientDetailDTO:
    patient: Patient
    last_visit: datetime | None
    next_visit: datetime | None
    records_count: int
    active_prescriptions: int


class CreatePatient:
    def __init__(self, uow: UnitOfWork, codes: CodeGenerator, clock: Clock) -> None:
        self._uow = uow
        self._codes = codes
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: CreatePatientCommand) -> Patient:
        patient = Patient(
            id=PatientId.new(),
            tenant_id=actor.tenant_id,
            code=self._codes.next_patient_code(),
            first_name=cmd.first_name,
            last_name=cmd.last_name,
            sex=cmd.sex,
            date_of_birth=cmd.date_of_birth,
            contact=cmd.contact,
            blood_type=cmd.blood_type,
            primary_doctor_id=cmd.primary_doctor_id,
            tags=list(cmd.tags),
            allergies=list(cmd.allergies),
            created_at=self._clock.now(),
            updated_at=self._clock.now(),
        )
        with self._uow:
            self._uow.patients.save(patient)
            self._uow.audit.append(
                audit_entry(actor, self._clock.now(), "patient.created", "Patient", str(patient.id))
            )
            self._uow.commit()
        return patient


class UpdatePatient:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, patient_id: PatientId, **changes: object) -> Patient:
        patient = self._uow.patients.get_by_id(patient_id)
        if patient is None:
            raise EntityNotFound("Patient", patient_id)
        allowed = {
            "first_name",
            "last_name",
            "contact",
            "blood_type",
            "primary_doctor_id",
            "tags",
            "allergies",
        }
        with self._uow:
            for key, value in changes.items():
                if key in allowed:
                    setattr(patient, key, value)
            patient.updated_at = self._clock.now()
            self._uow.patients.save(patient)
            self._uow.audit.append(
                audit_entry(actor, self._clock.now(), "patient.updated", "Patient", str(patient.id))
            )
            self._uow.commit()
        return patient


class ArchivePatient:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, patient_id: PatientId) -> Patient:
        patient = self._uow.patients.get_by_id(patient_id)
        if patient is None:
            raise EntityNotFound("Patient", patient_id)
        with self._uow:
            patient.archive()
            self._uow.patients.save(patient)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "patient.archived", "Patient", str(patient.id)
                )
            )
            self._uow.commit()
        return patient


class ListPatients:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self,
        actor: ActorContext,
        filter: PatientFilter | None = None,
        paging: Paging | None = None,
    ) -> Page[Patient]:
        return self._uow.patients.list(filter, paging)


class SearchPatients:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self, actor: ActorContext, query: str, paging: Paging | None = None
    ) -> Page[Patient]:
        return self._uow.patients.search(query, paging)


class PatientsNextVisits:
    """Earliest upcoming appointment per patient — enriches the patients list."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, patient_ids: list[PatientId]
    ) -> dict[PatientId, datetime]:
        now = clinic_now(self._uow, actor.tenant_id, self._clock)
        return self._uow.appointments.next_visits(patient_ids, now)


class GetPatientDetail:
    """Patient profile plus derived facts (last/next visit, counts)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, patient_id: PatientId) -> PatientDetailDTO:
        patient = self._uow.patients.get_by_id(patient_id)
        if patient is None:
            raise EntityNotFound("Patient", patient_id)

        # Appointments are stored as the clinic's local wall-clock; compare against "now" in
        # that same reference (see clinic_now), not raw UTC.
        now = clinic_now(self._uow, actor.tenant_id, self._clock)
        appointments = self._uow.appointments.list_by_patient(patient_id)
        # A completed appointment is a visit that happened; an active future one is the next.
        past = [a for a in appointments if a.status == AppointmentStatus.COMPLETED]
        upcoming = [a for a in appointments if a.is_active and to_naive(a.scheduled_start) > now]
        records = self._uow.medical_records.list_by_patient(patient_id)
        prescriptions = self._uow.prescriptions.list_by_patient(patient_id, active_only=True)

        return PatientDetailDTO(
            patient=patient,
            last_visit=max((a.scheduled_start for a in past), default=None),
            next_visit=min((a.scheduled_start for a in upcoming), default=None),
            records_count=len(records),
            active_prescriptions=sum(
                1 for p in prescriptions if p.status == PrescriptionStatus.ACTIVE
            ),
        )
