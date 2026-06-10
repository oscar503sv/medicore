"""Patients router."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.use_cases.patients import (
    ArchivePatient,
    CreatePatient,
    CreatePatientCommand,
    GetPatientDetail,
    ListPatients,
    PatientsNextVisits,
    ReactivatePatient,
    SearchPatients,
    UpdatePatient,
)
from medicore.domain.enums import Sex
from medicore.domain.repositories._support import Paging, PatientFilter
from medicore.domain.shared.identifiers import PatientId, UserId
from medicore.domain.value_objects.blood_type import BloodType
from medicore.domain.value_objects.contact_info import ContactInfo
from medicore.presentation.dependencies import Actor, Clock, Codes, UoW
from medicore.presentation.schemas.patients import (
    CreatePatientRequest,
    PatientDetailResponse,
    PatientListResponse,
    PatientResponse,
    UpdatePatientRequest,
)
from medicore.presentation.serializers import ser_appointment, ser_patient

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=PatientListResponse)
def list_patients(
    actor: Actor,
    uow: UoW,
    clock: Clock,
    status: str | None = Query(None),
    doctor_id: str | None = Query(None),
    q: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    with uow:
        if q:
            page = SearchPatients(uow).execute(actor, q, Paging(offset=offset, limit=limit))
        else:
            f = PatientFilter(status=status, doctor_id=doctor_id) if (status or doctor_id) else None
            page = ListPatients(uow).execute(actor, f, Paging(offset=offset, limit=limit))
        visits = PatientsNextVisits(uow, clock).execute(actor, [p.id for p in page.items])
    return PatientListResponse(
        items=[ser_patient(p, next_visit=visits.get(p.id)) for p in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.post("", response_model=PatientResponse, status_code=201)
def create_patient(body: CreatePatientRequest, actor: Actor, uow: UoW, codes: Codes, clock: Clock):
    contact = ContactInfo(
        phone=body.contact.phone,
        email=body.contact.email,
        address=body.contact.address,
        emergency_contact_name=body.contact.emergency_contact_name,
        emergency_contact_phone=body.contact.emergency_contact_phone,
    )
    cmd = CreatePatientCommand(
        first_name=body.first_name,
        last_name=body.last_name,
        sex=Sex(body.sex),
        date_of_birth=body.date_of_birth,
        contact=contact,
        blood_type=BloodType(body.blood_type) if body.blood_type else None,
        primary_doctor_id=UserId.parse(body.primary_doctor_id) if body.primary_doctor_id else None,
        tags=tuple(body.tags),
        allergies=tuple(body.allergies),
    )
    patient = CreatePatient(uow, codes, clock).execute(actor, cmd)
    return ser_patient(patient)


@router.get("/{patient_id}", response_model=PatientDetailResponse)
def get_patient(patient_id: str, actor: Actor, uow: UoW, clock: Clock):
    with uow:
        detail = GetPatientDetail(uow, clock).execute(actor, PatientId.parse(patient_id))
        next_appointment = None
        if detail.next_appointment is not None:
            appt = detail.next_appointment
            doctor = uow.users.get_by_id(appt.doctor_id)
            insurer = uow.insurers.get_by_id(appt.insurance_id) if appt.insurance_id else None
            next_appointment = ser_appointment(
                appt,
                patient_name=detail.patient.full_name,
                doctor_name=doctor.name if doctor else None,
                insurer_name=insurer.name if insurer else None,
            )
    return PatientDetailResponse(
        patient=ser_patient(detail.patient),
        last_visit=detail.last_visit,
        next_visit=detail.next_visit,
        records_count=detail.records_count,
        active_prescriptions=detail.active_prescriptions,
        next_appointment=next_appointment,
    )


@router.patch("/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id: str, body: UpdatePatientRequest, actor: Actor, uow: UoW, clock: Clock
):
    changes = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if body.contact is not None:
        changes["contact"] = ContactInfo(
            phone=body.contact.phone,
            email=body.contact.email,
            address=body.contact.address,
            emergency_contact_name=body.contact.emergency_contact_name,
            emergency_contact_phone=body.contact.emergency_contact_phone,
        )
    if "blood_type" in changes and changes["blood_type"]:
        changes["blood_type"] = BloodType(changes["blood_type"])
    if "primary_doctor_id" in changes and changes["primary_doctor_id"]:
        changes["primary_doctor_id"] = UserId.parse(changes["primary_doctor_id"])
    patient = UpdatePatient(uow, clock).execute(actor, PatientId.parse(patient_id), **changes)
    return ser_patient(patient)


@router.post("/{patient_id}/archive", response_model=PatientResponse)
def archive_patient(patient_id: str, actor: Actor, uow: UoW, clock: Clock):
    patient = ArchivePatient(uow, clock).execute(actor, PatientId.parse(patient_id))
    return ser_patient(patient)


@router.post("/{patient_id}/reactivate", response_model=PatientResponse)
def reactivate_patient(patient_id: str, actor: Actor, uow: UoW, clock: Clock):
    patient = ReactivatePatient(uow, clock).execute(actor, PatientId.parse(patient_id))
    return ser_patient(patient)
