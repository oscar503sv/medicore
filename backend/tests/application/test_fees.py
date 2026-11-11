"""Fees: who sets each doctor's prices, the price copied onto bookings and procedures, and
adjusting what a visit is charged (discounts, courtesies, included procedures)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import ROLE_PERMISSIONS, Permission
from medicore.application.use_cases.appointments import (
    CancelAppointment,
    CreateAppointment,
    CreateAppointmentCommand,
)
from medicore.application.use_cases.consultations import (
    AddProcedureDraft,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.application.use_cases.fees import (
    AdjustAppointmentFee,
    ListDoctorFees,
    SetProcedureFee,
    UpdateDoctorFees,
)
from medicore.application.use_cases.procedures import (
    GetPatientProcedures,
    ProcedureTypeCommand,
    UpdateProcedureType,
)
from medicore.domain.enums import AppointmentType, Role
from medicore.domain.shared.errors import DomainError, InvalidValueObject, PermissionDenied
from medicore.domain.value_objects.fee import ZERO, fee
from tests.application.test_consultations import MONDAY_9AM, booked, fill
from tests.application.test_procedures import _create, _type, _uow
from tests.support.builders import build_user, seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator

PRICES = {AppointmentType.CONSULT: fee(30), AppointmentType.FOLLOW_UP: fee(15)}


def _set(seed, actor, doctor=None, prices=PRICES):
    return UpdateDoctorFees(_uow(seed), FixedClock()).execute(
        actor, (doctor or seed.doctor).id, prices)


def _employed(actor):
    """The doctor of a clinic whose doctors don't set their own prices."""
    return replace(actor, permissions=frozenset(
        str(p) for p in ROLE_PERMISSIONS[Role.DOCTOR] - {Permission.FEES_MANAGE_OWN}))


def _book(seed, kind=AppointmentType.CONSULT, start=MONDAY_9AM):
    return CreateAppointment(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
        seed.receptionist_actor, CreateAppointmentCommand(
            patient_id=seed.patient.id, doctor_id=seed.doctor.id,
            location_id=seed.tenant.primary_location.id, type=kind, scheduled_start=start,
            reason="Control",
        ))


def test_doctors_set_their_own_prices_and_admins_everyones():
    seed = seed_clinic()
    other = build_user(seed.tenant.id, Role.DOCTOR, name="Dr. Otro", email="otro@x.test")
    seed.factory.store.users[other.id.value] = other

    assert _set(seed, seed.doctor_actor).prices == PRICES
    with pytest.raises(PermissionDenied) as e:
        _set(seed, seed.doctor_actor, other)
    assert e.value.code == "fee.not_allowed"
    _set(seed, seed.actor(seed.admin), other, {AppointmentType.CONSULT: fee(40)})
    with pytest.raises(PermissionDenied):
        _set(seed, seed.receptionist_actor)
    with pytest.raises(PermissionDenied):  # employed doctors: the clinic sets the prices
        _set(seed, _employed(seed.doctor_actor))

    rows = {r.doctor.id: r for r in ListDoctorFees(_uow(seed)).execute(seed.receptionist_actor)}
    assert rows[seed.doctor.id].prices == PRICES and not rows[seed.doctor.id].editable
    assert rows[other.id].prices == {AppointmentType.CONSULT: fee(40)}
    mine = {r.doctor.id: r.editable for r in ListDoctorFees(_uow(seed)).execute(
        seed.doctor_actor)}
    assert mine == {seed.doctor.id: True, other.id: False}
    audited = [a for a in seed.factory.store.audit.values() if a.action == "fees.updated"]
    assert len(audited) == 2 and audited[0].metadata["prices"] == {
        "consult": "30.00", "follow_up": "15.00"}


def test_only_active_doctors_have_prices():
    seed = seed_clinic()
    with pytest.raises(EntityNotFound):
        _set(seed, seed.actor(seed.admin), seed.nurse)


def test_booking_copies_the_price_and_later_changes_dont_touch_it():
    seed = seed_clinic()
    unpriced = _book(seed)
    assert unpriced.charge.listed is None and unpriced.charge.charged is None
    _set(seed, seed.doctor_actor)
    appt = _book(seed, start=MONDAY_9AM + timedelta(hours=1))
    assert (appt.charge.listed, appt.charge.charged) == (fee(30), fee(30))
    _set(seed, seed.doctor_actor, prices={AppointmentType.CONSULT: fee(35)})
    stored = _uow(seed).appointments.get_by_id(appt.id)
    assert stored.charge.charged == fee(30)
    # procedure appointments are priced by the procedure done, not per doctor
    proc = _book(seed, AppointmentType.PROCEDURE, MONDAY_9AM + timedelta(hours=2))
    assert proc.charge.listed is None


def test_adjusting_an_appointment_charge():
    seed = seed_clinic()
    _set(seed, seed.doctor_actor)
    appt = _book(seed)
    adjust = AdjustAppointmentFee(_uow(seed), FixedClock())
    with pytest.raises(InvalidValueObject) as e:
        adjust.execute(seed.doctor_actor, appt.id, fee(20), None)
    assert e.value.code == "fee.note_required"
    done = adjust.execute(seed.doctor_actor, appt.id, ZERO, "Cortesía")
    assert (done.charge.listed, done.charge.charged, done.charge.note) == (
        fee(30), ZERO, "Cortesía")
    with pytest.raises(PermissionDenied):  # reception sees prices, doesn't decide them
        adjust.execute(seed.receptionist_actor, appt.id, fee(10), "x")
    adjust.execute(seed.actor(seed.admin), appt.id, fee(25), "Descuento")
    CancelAppointment(_uow(seed), FixedClock()).execute(seed.receptionist_actor, appt.id)
    with pytest.raises(DomainError) as e:
        adjust.execute(seed.doctor_actor, appt.id, fee(10), "x")
    assert e.value.code == "fee.appointment_cancelled"


def _price_type(seed, name, price):
    kind = _type(seed, name)
    return UpdateProcedureType(_uow(seed), FixedClock()).execute(
        seed.actor(seed.admin), kind.id, ProcedureTypeCommand(
            name=kind.name, performer=kind.performer, requires_consent=kind.requires_consent,
            follow_up_days=kind.follow_up_days, takes_specimen=kind.takes_specimen,
            technique_template=kind.technique_template,
            instructions_template=kind.instructions_template, price=fee(price),
        ))


def test_a_procedure_can_be_included_in_the_consultation_it_was_indicated_in():
    seed = seed_clinic()
    biopsy = _price_type(seed, "Biopsia de piel", "60")
    ecg = _price_type(seed, "Electrocardiograma", "25")
    uow = _uow(seed)
    appt = booked(seed, uow)
    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)
    fill(seed, uow, consultation)
    add = AddProcedureDraft(uow, FixedClock())
    with pytest.raises(PermissionDenied):  # charging nothing is a fee decision
        add.execute(_employed(seed.doctor_actor), consultation.id, ecg.id, "Palpitaciones",
                    included=True)
    add.execute(seed.doctor_actor, consultation.id, biopsy.id, "Lesión en espalda")
    add.execute(seed.doctor_actor, consultation.id, ecg.id, "Palpitaciones", included=True)
    SignConsultation(uow, SequentialCodeGenerator(), FixedClock()).execute(
        seed.doctor_actor, SignConsultationCommand(consultation_id=consultation.id))

    procs = {p.type_name: p for p in GetPatientProcedures(_uow(seed)).execute(
        seed.doctor_actor, seed.patient.id)}
    b, e = procs["Biopsia de piel"], procs["Electrocardiograma"]
    assert (b.charge.charged, b.fee_included) == (fee(60), False)
    assert (e.charge.listed, e.charge.charged, e.fee_included) == (fee(25), ZERO, True)

    set_fee = SetProcedureFee(_uow(seed), FixedClock())
    p = set_fee.execute(seed.doctor_actor, b.id, included=True, charged=None, note=None)
    assert (p.charge.charged, p.fee_included) == (ZERO, True)
    with pytest.raises(PermissionDenied):
        set_fee.execute(seed.actor(seed.nurse), b.id, included=False, charged=fee(60), note=None)


def test_a_walk_in_procedure_is_charged_its_catalog_price_and_cannot_be_included():
    seed = seed_clinic()
    _price_type(seed, "Sutura de herida", "35")
    p = _create(seed, seed.doctor_actor)
    assert (p.charge.listed, p.charge.charged) == (fee(35), fee(35))
    with pytest.raises(DomainError) as e:
        SetProcedureFee(_uow(seed), FixedClock()).execute(
            seed.doctor_actor, p.id, included=True, charged=None, note=None)
    assert e.value.code == "fee.included_needs_consultation"
    adjusted = SetProcedureFee(_uow(seed), FixedClock()).execute(
        seed.actor(seed.admin), p.id, included=False, charged=fee(30), note="Descuento")
    assert adjusted.charge.charged == fee(30)
