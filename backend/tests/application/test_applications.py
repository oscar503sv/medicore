"""In-clinic applications: external orders, recording doses (allergy alert, lot expiry),
observation and reactions, voiding, cancelling, the worklist and orders born from signing."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.use_cases.applications import (
    CancelApplicationOrder,
    CloseObservation,
    CreateExternalOrder,
    CreateExternalOrderCommand,
    GetApplicationWorklist,
    GetPatientApplications,
    RecordApplication,
    RecordApplicationCommand,
    VoidApplication,
)
from medicore.application.use_cases.consultations import (
    AddApplicationDraft,
    RemoveApplicationDraft,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.domain.entities.application import (
    ApplicationDraft,
    ApplicationOrder,
    ApplicationOrderClosed,
)
from medicore.domain.enums import (
    ApplicationOrderSource,
    ApplicationOrderStatus,
    ApplicationOutcome,
    ApplicationRoute,
    PatientStatus,
)
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import ApplicationOrderId
from tests.application.test_consultations import booked, fill
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator

NOW = datetime(2026, 5, 31, 9, 0)  # FixedClock default


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


def _external(seed, actor=None, **kw):
    cmd = CreateExternalOrderCommand(
        patient_id=kw.pop("patient_id", seed.patient.id),
        drug=kw.pop("drug", "Ceftriaxona"),
        dose=kw.pop("dose", "1 g"),
        route=kw.pop("route", ApplicationRoute.INTRAMUSCULAR),
        prescriber=kw.pop("prescriber", "Dr. Ernesto Ramos"),
        jvpm=kw.pop("jvpm", "12345"),
        **kw,
    )
    return CreateExternalOrder(_uow(seed), FixedClock()).execute(
        actor or seed.actor(seed.nurse), cmd
    )


def _apply(seed, order, clock=None, actor=None, **kw):
    return RecordApplication(_uow(seed), clock or FixedClock()).execute(
        actor or seed.actor(seed.nurse), RecordApplicationCommand(order_id=order.id, **kw)
    )


def test_nurse_registers_an_external_prescription_and_applies_its_doses():
    seed = seed_clinic()
    order = _external(seed, doses_total=2, interval_hours=24)
    assert order.source == ApplicationOrderSource.EXTERNAL and order.starts_at == NOW
    assert _uow(seed).audit.query(action="application.order_created")

    first = _apply(seed, order, lot="L-77", lot_expiry=date(2027, 1, 1))
    assert first.dose_number == 1
    assert first.observe_until == NOW + timedelta(minutes=30)  # default observation
    assert _uow(seed).applications.get_order(order.id).status == ApplicationOrderStatus.IN_PROGRESS

    second = _apply(seed, order, outcome=ApplicationOutcome.REFUSED, notes="No quiso")
    assert second.dose_number == 2 and second.observe_until is None
    assert _uow(seed).applications.get_order(order.id).status == ApplicationOrderStatus.COMPLETED
    with pytest.raises(ApplicationOrderClosed):
        _apply(seed, order)


def test_allergy_alert_blocks_until_justified():
    seed = seed_clinic()
    seed.patient.allergies = ["Penicilina"]
    order = _external(seed, drug="Penicilina benzatínica", dose="1 200 000 UI")
    with pytest.raises(ValidationError) as exc:
        _apply(seed, order)
    assert exc.value.code == "application.allergy_conflict"
    assert exc.value.params["allergies"] == "Penicilina"

    rec = _apply(seed, order, allergy_override="Prueba cutánea negativa, indicación médica")
    assert rec.allergy_override.startswith("Prueba cutánea")
    view = GetPatientApplications(_uow(seed)).execute(seed.doctor_actor, seed.patient.id)[0]
    assert view.allergy_conflicts == ["Penicilina"]


def test_override_is_dropped_when_there_is_no_clash_and_expired_lots_are_rejected():
    seed = seed_clinic()
    order = _external(seed, doses_total=2, interval_hours=12)
    with pytest.raises(ValidationError) as exc:
        _apply(seed, order, lot_expiry=date(2026, 5, 30))
    assert exc.value.code == "application.lot_expired"
    rec = _apply(seed, order, allergy_override="por si acaso")
    assert rec.allergy_override is None


def test_reaction_closes_observation_and_notifies_the_ordering_doctor():
    seed = seed_clinic()
    order = _signed_order(seed)
    rec = _apply(seed, order)
    CloseObservation(_uow(seed), FixedClock(NOW + timedelta(minutes=20))).execute(
        seed.actor(seed.nurse), rec.id, True, "Urticaria en brazo, se avisa al médico"
    )
    notes = [n for n in seed.factory.store.notifications.values()
             if n.type == "application.reaction"]
    assert [n.user_id for n in notes] == [seed.doctor.id]
    assert notes[0].data["patient_name"] == seed.patient.full_name
    assert "reaction_notes" not in notes[0].data  # no clinical content in notifications
    assert _uow(seed).audit.query(action="application.reaction")


def test_no_reaction_just_closes_it():
    seed = seed_clinic()
    rec = _apply(seed, _external(seed))
    CloseObservation(_uow(seed), FixedClock()).execute(seed.actor(seed.nurse), rec.id, False)
    assert not _uow(seed).applications.get_record(rec.id).observing
    assert not [n for n in seed.factory.store.notifications.values()
                if n.type == "application.reaction"]


def test_voiding_a_dose_makes_it_due_again():
    seed = seed_clinic()
    order = _external(seed)
    rec = _apply(seed, order)
    assert _uow(seed).applications.get_order(order.id).status == ApplicationOrderStatus.COMPLETED
    VoidApplication(_uow(seed), FixedClock()).execute(
        seed.actor(seed.nurse), rec.id, "Paciente equivocado"
    )
    assert _uow(seed).applications.get_order(order.id).status == ApplicationOrderStatus.PENDING
    assert _apply(seed, order).dose_number == 1


def test_cancelled_orders_leave_the_worklist():
    seed = seed_clinic()
    order = _external(seed)
    CancelApplicationOrder(_uow(seed), FixedClock()).execute(
        seed.actor(seed.nurse), order.id, "Ya se la aplicaron en otro lugar"
    )
    wl = GetApplicationWorklist(_uow(seed), FixedClock()).execute(seed.receptionist_actor)
    assert wl.due == []


def test_worklist_due_late_observing_and_done():
    seed = seed_clinic()
    tomorrow = _external(seed, drug="Ceftriaxona", doses_total=2, interval_hours=24)
    _apply(seed, tomorrow)  # dose 2 due tomorrow → not on today's list
    late = _external(seed, drug="Dexametasona", dose="8 mg")
    later = FixedClock(NOW + timedelta(hours=2))

    wl = GetApplicationWorklist(_uow(seed), later).execute(seed.actor(seed.nurse))
    assert [(i.view.order.drug, i.late) for i in wl.due] == [("Dexametasona", True)]
    assert [i.order.drug for i in wl.done_today] == ["Ceftriaxona"]
    assert [i.order.drug for i in wl.observing] == ["Ceftriaxona"]  # still open past its time

    _apply(seed, late, clock=later)
    wl = GetApplicationWorklist(_uow(seed), later).execute(seed.actor(seed.nurse))
    assert wl.due == [] and len(wl.done_today) == 2


def test_permissions_and_inactive_patients():
    seed = seed_clinic()
    with pytest.raises(PermissionDenied):
        _external(seed, actor=seed.receptionist_actor)
    order = _external(seed)
    with pytest.raises(PermissionDenied):
        _apply(seed, order, actor=seed.receptionist_actor)
    GetPatientApplications(_uow(seed)).execute(seed.receptionist_actor, seed.patient.id)
    # Applying a medication is a clinical act: the admin sees the list but doesn't apply.
    admin = seed.actor(seed.admin)
    with pytest.raises(PermissionDenied):
        _external(seed, actor=admin)
    with pytest.raises(PermissionDenied):
        _apply(seed, order, actor=admin)
    GetPatientApplications(_uow(seed)).execute(admin, seed.patient.id)
    seed.patient.status = PatientStatus.INACTIVE
    with pytest.raises(ValidationError) as exc:
        _apply(seed, order)
    assert exc.value.code == "application.patient_inactive"


def _signed_order(seed) -> ApplicationOrder:
    uow = _uow(seed)
    appt = booked(seed, uow)
    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)
    fill(seed, uow, consultation)
    add = AddApplicationDraft(uow, FixedClock())
    add.execute(seed.doctor_actor, consultation.id, ApplicationDraft(
        drug="Ketorolaco", dose="30 mg", route=ApplicationRoute.INTRAMUSCULAR,
        observation_minutes=15,
    ))
    add.execute(seed.doctor_actor, consultation.id, ApplicationDraft(
        drug="Salbutamol", dose="2.5 mg", route=ApplicationRoute.NEBULIZED,
    ))
    RemoveApplicationDraft(uow, FixedClock()).execute(seed.doctor_actor, consultation.id, 1)
    SignConsultation(uow, SequentialCodeGenerator(), FixedClock()).execute(
        seed.doctor_actor, SignConsultationCommand(consultation_id=consultation.id)
    )
    (order,) = uow.applications.list_orders_by_patient(seed.patient.id)
    return order


def test_signing_a_consultation_issues_its_indicated_applications():
    seed = seed_clinic()
    order = _signed_order(seed)
    assert order.source == ApplicationOrderSource.INTERNAL
    assert order.ordered_by_id == seed.doctor.id and order.consultation_id is not None
    assert (order.drug, order.observation_minutes, order.starts_at) == ("Ketorolaco", 15, NOW)
    wl = GetApplicationWorklist(_uow(seed), FixedClock()).execute(seed.actor(seed.nurse))
    assert [i.view.order.id for i in wl.due] == [order.id]


def test_unknown_order():
    seed = seed_clinic()
    with pytest.raises(EntityNotFound):
        RecordApplication(_uow(seed), FixedClock()).execute(
            seed.actor(seed.nurse), RecordApplicationCommand(order_id=ApplicationOrderId.new())
        )
