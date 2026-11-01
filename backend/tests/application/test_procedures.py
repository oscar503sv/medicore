"""Procedures: catalog (preloaded, editable), who may perform, the full lifecycle (consent,
note, sign, amend, cancel), procedure appointments, consultation orders and the worklist."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from medicore.application.common.errors import ValidationError
from medicore.application.use_cases.appointments import (
    CreateAppointment,
    CreateAppointmentCommand,
)
from medicore.application.use_cases.consultations import (
    AddProcedureDraft,
    RemoveProcedureDraft,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.application.use_cases.procedures import (
    AmendProcedure,
    CancelProcedure,
    CreateProcedure,
    CreateProcedureCommand,
    CreateProcedureType,
    GetPatientProcedures,
    GetProcedure,
    GetProcedureCatalog,
    GetProcedureWorklist,
    ProcedureTypeCommand,
    RecordProcedureConsent,
    SaveProcedureProgress,
    SetProcedureTypeActive,
    SignProcedure,
    UpdateProcedureType,
)
from medicore.domain.entities.procedure import ProcedureProgress
from medicore.domain.enums import (
    AppointmentStatus,
    AppointmentType,
    ProcedurePerformer,
    ProcedureSource,
    ProcedureStatus,
)
from medicore.domain.services.procedure_catalog import DEFAULT_PROCEDURES
from medicore.domain.shared.errors import PermissionDenied
from tests.application.test_consultations import MONDAY_9AM, booked, fill
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


def _type(seed, name):
    types = GetProcedureCatalog(_uow(seed), FixedClock()).execute(seed.doctor_actor)
    return next(t for t in types if t.name == name)


def _create(seed, actor, name="Sutura de herida", **kw):
    return CreateProcedure(_uow(seed), FixedClock()).execute(actor, CreateProcedureCommand(
        patient_id=seed.patient.id, type_id=_type(seed, name).id,
        indication=kw.pop("indication", "Herida cortante en antebrazo"), **kw,
    ))


def _progress(**kw) -> ProcedureProgress:
    return ProcedureProgress(allergies_reviewed=True, technique="Puntos simples", **kw)


def test_catalog_starts_with_the_common_procedures_and_is_editable():
    seed = seed_clinic()
    admin = seed.actor(seed.admin)
    types = GetProcedureCatalog(_uow(seed), FixedClock()).execute(seed.receptionist_actor)
    assert len(types) == len(DEFAULT_PROCEDURES)
    assert len(GetProcedureCatalog(_uow(seed), FixedClock()).execute(admin)) == len(types)

    cmd = ProcedureTypeCommand(name="Taponamiento nasal", performer=ProcedurePerformer.DOCTOR,
                               follow_up_days=2)
    with pytest.raises(PermissionDenied):
        CreateProcedureType(_uow(seed), FixedClock()).execute(seed.doctor_actor, cmd)
    kind = CreateProcedureType(_uow(seed), FixedClock()).execute(admin, cmd)
    with pytest.raises(ValidationError) as exc:
        CreateProcedureType(_uow(seed), FixedClock()).execute(admin, ProcedureTypeCommand(
            name="  taponamiento NASAL", performer=ProcedurePerformer.DOCTOR))
    assert exc.value.code == "procedure.name_taken"
    renamed = ProcedureTypeCommand(name="Taponamiento nasal anterior",
                                   performer=ProcedurePerformer.DOCTOR_OR_NURSE)
    kind = UpdateProcedureType(_uow(seed), FixedClock()).execute(admin, kind.id, renamed)
    assert kind.performer == ProcedurePerformer.DOCTOR_OR_NURSE
    SetProcedureTypeActive(_uow(seed), FixedClock()).execute(admin, kind.id, False)
    with pytest.raises(ValidationError) as exc:
        CreateProcedure(_uow(seed), FixedClock()).execute(seed.doctor_actor, CreateProcedureCommand(
            patient_id=seed.patient.id, type_id=kind.id, indication="Epistaxis"))
    assert exc.value.code == "procedure.type_inactive"
    actions = {e.action for e in seed.factory.store.audit.values()}
    assert {"procedure.type_created", "procedure.type_updated",
            "procedure.type_archived"} <= actions


def test_who_may_perform():
    seed = seed_clinic()
    nurse = seed.actor(seed.nurse)
    with pytest.raises(PermissionDenied) as exc:
        _create(seed, nurse)  # suture: doctors only
    assert exc.value.code == "procedure.doctor_only"
    p = _create(seed, nurse, "Retiro de puntos", indication="Sutura de hace 8 días")
    assert p.performer == ProcedurePerformer.DOCTOR_OR_NURSE
    for actor in (seed.receptionist_actor, seed.actor(seed.admin)):
        with pytest.raises(PermissionDenied):
            _create(seed, actor, "Retiro de puntos")
    # A doctor-only procedure ordered by a doctor can't be signed by the nurse.
    suture = _create(seed, seed.doctor_actor)
    with pytest.raises(PermissionDenied):
        SaveProcedureProgress(_uow(seed), FixedClock()).execute(nurse, suture.id, _progress())


def test_full_lifecycle_with_consent_sign_and_amendment():
    seed = seed_clinic()
    doc = seed.doctor_actor
    seed.patient.allergies = ["Lidocaína"]
    p = _create(seed, doc)
    uow = _uow(seed)
    SaveProcedureProgress(uow, FixedClock()).execute(
        doc, p.id, _progress(anesthesia="Lidocaína 2 %", bp_before="120/80"))
    view = GetProcedure(_uow(seed)).execute(seed.receptionist_actor, p.id)
    assert view.allergy_conflicts == ["Lidocaína"]
    assert view.kind.technique_template  # the catalog's template for the note
    with pytest.raises(Exception) as exc:
        SignProcedure(_uow(seed), FixedClock()).execute(doc, p.id)
    assert exc.value.code == "procedure.consent_required"
    RecordProcedureConsent(_uow(seed), FixedClock()).execute(
        doc, p.id, "María López", "Madre", "Lucía Méndez")
    with pytest.raises(Exception) as exc:
        SignProcedure(_uow(seed), FixedClock()).execute(doc, p.id)
    assert exc.value.code == "procedure.allergy_conflict"
    SaveProcedureProgress(_uow(seed), FixedClock()).execute(doc, p.id, _progress(
        anesthesia="Lidocaína 2 %", allergy_override="Alergia referida a otro anestésico"))
    p = SignProcedure(_uow(seed), FixedClock()).execute(doc, p.id)
    assert p.status == ProcedureStatus.COMPLETED and p.follow_up_on.isoformat() == "2026-06-08"

    nurse = seed.actor(seed.nurse)
    with pytest.raises(PermissionDenied) as exc:
        AmendProcedure(_uow(seed), FixedClock()).execute(nurse, p.id, "x", "y")
    assert exc.value.code == "procedure.not_performer"
    p = AmendProcedure(_uow(seed), FixedClock()).execute(doc, p.id, "4 puntos", "Conteo")
    assert len(p.amendments) == 1
    actions = {e.action for e in seed.factory.store.audit.values()}
    assert {"procedure.created", "procedure.consent_recorded", "procedure.signed",
            "procedure.amended"} <= actions


def test_nurse_signing_a_doctors_order_notifies_the_doctor():
    seed = seed_clinic()
    p = _create(seed, seed.doctor_actor, "Retiro de puntos", indication="Retiro a los 8 días")
    nurse = seed.actor(seed.nurse)
    SaveProcedureProgress(_uow(seed), FixedClock()).execute(nurse, p.id, _progress())
    SignProcedure(_uow(seed), FixedClock()).execute(nurse, p.id)
    sent = [(n.user_id, n.type) for n in seed.factory.store.notifications.values()]
    assert sent == [(seed.doctor.id, "procedure.performed")]


def test_cancel_needs_a_reason_and_closes_it():
    seed = seed_clinic()
    p = _create(seed, seed.doctor_actor)
    with pytest.raises(Exception) as exc:
        CancelProcedure(_uow(seed), FixedClock()).execute(seed.doctor_actor, p.id, " ")
    assert exc.value.code == "procedure.reason_required"
    p = CancelProcedure(_uow(seed), FixedClock()).execute(seed.doctor_actor, p.id, "No vino")
    assert p.status == ProcedureStatus.CANCELLED
    wl = GetProcedureWorklist(_uow(seed), FixedClock()).execute(seed.receptionist_actor)
    assert wl.pending == []


def _procedure_appointment(seed):
    return CreateAppointment(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
        seed.doctor_actor, CreateAppointmentCommand(
            patient_id=seed.patient.id, doctor_id=seed.doctor.id,
            location_id=seed.tenant.primary_location.id, type=AppointmentType.PROCEDURE,
            scheduled_start=MONDAY_9AM + timedelta(minutes=30), reason="Retiro de puntos",
        ))


def test_procedure_appointment_is_linked_and_completed_on_signing():
    seed = seed_clinic()
    appt = _procedure_appointment(seed)
    monday = FixedClock(datetime(2026, 6, 1, 9, 10))
    wl = GetProcedureWorklist(_uow(seed), monday).execute(seed.receptionist_actor)
    assert [(i.appointment.id, i.procedure) for i in wl.today] == [(appt.id, None)]

    nurse = seed.actor(seed.nurse)
    p = _create(seed, nurse, "Retiro de puntos", appointment_id=appt.id)
    with pytest.raises(ValidationError) as exc:
        _create(seed, nurse, "Retiro de puntos", appointment_id=appt.id)
    assert exc.value.code == "procedure.appointment_taken"
    consult = booked(seed, _uow(seed))
    with pytest.raises(ValidationError) as exc:
        _create(seed, nurse, "Retiro de puntos", appointment_id=consult.id)
    assert exc.value.code == "procedure.appointment_mismatch"

    SaveProcedureProgress(_uow(seed), monday).execute(nurse, p.id, _progress())
    SignProcedure(_uow(seed), monday).execute(nurse, p.id)
    assert _uow(seed).appointments.get_by_id(appt.id).status == AppointmentStatus.COMPLETED
    wl = GetProcedureWorklist(_uow(seed), monday).execute(seed.receptionist_actor)
    assert wl.today[0].procedure.id == p.id and [i.procedure.id for i in wl.done] == [p.id]


def test_consultation_orders_become_pending_procedures():
    seed = seed_clinic()
    uow = _uow(seed)
    appt = booked(seed, uow)
    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)
    fill(seed, uow, consultation)
    biopsy = _type(seed, "Biopsia de piel")
    ecg = _type(seed, "Electrocardiograma")
    add = AddProcedureDraft(uow, FixedClock())
    add.execute(seed.doctor_actor, consultation.id, biopsy.id, "Lesión pigmentada en espalda")
    add.execute(seed.doctor_actor, consultation.id, ecg.id, "Palpitaciones")
    RemoveProcedureDraft(uow, FixedClock()).execute(seed.doctor_actor, consultation.id, 1)
    SignConsultation(uow, SequentialCodeGenerator(), FixedClock()).execute(
        seed.doctor_actor, SignConsultationCommand(consultation_id=consultation.id))
    (p,) = GetPatientProcedures(_uow(seed)).execute(seed.receptionist_actor, seed.patient.id)
    assert (p.source, p.type_name, p.requires_consent, p.takes_specimen) == (
        ProcedureSource.CONSULTATION, "Biopsia de piel", True, True)
    assert p.consultation_id == consultation.id and p.ordered_by_id == seed.doctor.id
    wl = GetProcedureWorklist(_uow(seed), FixedClock()).execute(seed.actor(seed.nurse))
    assert [i.procedure.id for i in wl.pending] == [p.id]
