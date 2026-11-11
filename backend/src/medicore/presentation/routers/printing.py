"""Printable documents router. Each endpoint returns what one sheet needs and logs the print;
the browser lays it out. Prices never appear here."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from medicore.application.use_cases.printing import (
    PrintAgenda,
    PrintAppointmentSlip,
    PrintCertificate,
    PrintContext,
    PrintProcedureDocument,
    PrintRecordDocument,
    PrintVaccinationCard,
)
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.procedure import Procedure
from medicore.domain.shared.identifiers import (
    AppointmentId,
    CertificateId,
    PatientId,
    ProcedureId,
    RecordId,
    UserId,
)
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.printing import (
    AgendaPrintResponse,
    AppointmentPrintResponse,
    CertificatePrintResponse,
    PrintContextSchema,
    ProcedurePrintResponse,
    RecordPrintResponse,
)
from medicore.presentation.serializers import ser_record

router = APIRouter(prefix="/print", tags=["printing"])


def _context(c: PrintContext) -> dict:
    clinic = c.clinic
    return {
        "clinic": {
            "name": clinic.name, "tax_id": clinic.tax_id, "location_name": clinic.location_name,
            "address": clinic.address, "phone": clinic.phone, "paper": clinic.paper,
            "letterhead": clinic.letterhead,
        },
        "printed_at": c.printed_at,
        "patient": {
            "name": c.patient.name, "code": c.patient.code, "sex": c.patient.sex,
            "date_of_birth": c.patient.date_of_birth, "age": c.patient.age,
            "allergies": list(c.patient.allergies),
        } if c.patient else None,
        "doctor": {
            "name": c.doctor.name, "specialty": c.doctor.specialty, "jvpm": c.doctor.jvpm,
            "sex": c.doctor.sex,
        } if c.doctor else None,
    }


def _procedure(p: Procedure) -> dict:
    return {
        "type_name": p.type_name, "status": str(p.status), "indication": p.indication,
        "requires_consent": p.requires_consent, "takes_specimen": p.takes_specimen,
        "anesthesia": p.anesthesia, "technique": p.technique, "findings": p.findings,
        "complications": p.complications, "instructions": p.instructions,
        "specimen_sent": p.specimen_sent, "specimen_description": p.specimen_description,
        "performed_at": p.performed_at, "follow_up_on": p.follow_up_on,
        "follow_up_days": p.follow_up_days,
    }


def _appointment(a: Appointment) -> dict:
    return {
        "code": a.code, "type": str(a.type), "status": str(a.status),
        "scheduled_start": a.scheduled_start, "duration_minutes": a.duration_minutes,
    }


@router.get("/records/{record_id}", response_model=RecordPrintResponse)
def print_record(
    record_id: str, actor: Actor, uow: UoW, clock: Clock,
    document: Literal["prescription", "exams", "record"] = Query("prescription"),
):
    doc = PrintRecordDocument(uow, clock).execute(actor, RecordId.parse(record_id), document)
    return {
        "context": _context(doc.context), "record": ser_record(doc.record),
        "indications": doc.indications, "amends_code": doc.amends_code,
    }


@router.get("/certificates/{certificate_id}", response_model=CertificatePrintResponse)
def print_certificate(certificate_id: str, actor: Actor, uow: UoW, clock: Clock):
    doc = PrintCertificate(uow, clock).execute(actor, CertificateId.parse(certificate_id))
    c = doc.certificate
    return {
        "context": _context(doc.context),
        "certificate": {
            "code": c.code, "kind": str(c.kind), "issued_at": c.issued_at,
            "rest_from": c.rest_from, "rest_days": c.rest_days, "rest_until": c.rest_until,
            "diagnosis": c.diagnosis, "remarks": c.remarks, "addressee": c.addressee,
        },
        "encounter_at": doc.encounter_at, "ended_at": doc.ended_at,
    }


@router.get("/procedures/{procedure_id}", response_model=ProcedurePrintResponse)
def print_procedure(
    procedure_id: str, actor: Actor, uow: UoW, clock: Clock,
    document: Literal["instructions", "consent", "pathology"] = Query("instructions"),
):
    doc = PrintProcedureDocument(uow, clock).execute(
        actor, ProcedureId.parse(procedure_id), document
    )
    return {"context": _context(doc.context), "procedure": _procedure(doc.procedure)}


@router.get("/vaccination-card/{patient_id}", response_model=PrintContextSchema)
def print_vaccination_card(patient_id: str, actor: Actor, uow: UoW, clock: Clock):
    return _context(PrintVaccinationCard(uow, clock).execute(actor, PatientId.parse(patient_id)))


@router.get("/appointments/{appointment_id}", response_model=AppointmentPrintResponse)
def print_appointment(appointment_id: str, actor: Actor, uow: UoW, clock: Clock):
    doc = PrintAppointmentSlip(uow, clock).execute(actor, AppointmentId.parse(appointment_id))
    return {"context": _context(doc.context), "appointment": _appointment(doc.appointment)}


@router.get("/agenda", response_model=AgendaPrintResponse)
def print_agenda(
    actor: Actor, uow: UoW, clock: Clock, day: date = Query(..., alias="date"),
    doctor_id: str | None = Query(None),
):
    doc = PrintAgenda(uow, clock).execute(
        actor, day, UserId.parse(doctor_id) if doctor_id else None
    )
    return {
        "context": _context(doc.context), "day": doc.day,
        "rows": [
            {**_appointment(r.appointment), "reason": r.appointment.reason,
             "patient_name": r.patient_name, "patient_code": r.patient_code}
            for r in doc.rows
        ],
    }
