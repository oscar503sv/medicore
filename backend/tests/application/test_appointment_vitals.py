"""Vitals taken from a confirmed appointment, before the consultation exists."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import ConsultationNotStarted
from medicore.application.use_cases.appointments import (
    CancelAppointment,
    ConfirmAppointment,
    CreateAppointment,
    CreateAppointmentCommand,
    RegisterWalkIn,
    RescheduleAppointment,
    WalkInCommand,
)
from medicore.application.use_cases.consultations import (
    AutosaveConsultation,
    ConsultationPatch,
    GetAppointmentVitals,
    GetConsultationVitals,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
    UpdateAppointmentVitals,
)
from medicore.domain.enums import AppointmentType, Role
from medicore.domain.shared.errors import ConsultationAlreadySigned, DomainError, PermissionDenied
from medicore.domain.shared.identifiers import PlatformAdminId
from tests.support.builders import build_user, seed_clinic, soap_note
from tests.support.fakes import FixedClock, SequentialCodeGenerator

START = datetime(2026, 6, 1, 9, 0)


class Setup:
    def __init__(self) -> None:
        self.seed = seed_clinic()
        self.uow = self.seed.factory.for_tenant(self.seed.tenant.id)
        self.clock = FixedClock()
        self.nurse = self.seed.actor(self.seed.nurse)
        self.doctor = self.seed.doctor_actor
        self.receptionist = self.seed.receptionist_actor
        other_doctor = build_user(
            self.seed.tenant.id, Role.DOCTOR, name="Dr. Otro", email="otro@clinica-norte.test"
        )
        self.seed.factory.store.users[other_doctor.id.value] = other_doctor
        self.other = self.seed.actor(other_doctor)
        self.support = ActorContext(
            user_id=self.seed.admin.id, tenant_id=self.seed.tenant.id, role=Role.ADMIN,
            impersonated_by=PlatformAdminId.new(),
        )
        self.appointment = self.book(START)
        ConfirmAppointment(self.uow, self.clock).execute(self.receptionist, self.appointment.id)

    def book(self, start: datetime):
        return CreateAppointment(self.uow, SequentialCodeGenerator(), self.clock).execute(
            self.doctor,
            CreateAppointmentCommand(
                patient_id=self.seed.patient.id, doctor_id=self.seed.doctor.id,
                location_id=self.seed.tenant.primary_location.id, type=AppointmentType.CONSULT,
                scheduled_start=start, reason="Control",
            ),
        )

    def record(self, actor, appointment=None, **changes):
        return UpdateAppointmentVitals(self.uow, self.clock).execute(
            actor, (appointment or self.appointment).id, changes or {"heart_rate": 70}
        )

    def view(self, actor, appointment=None):
        return GetAppointmentVitals(self.uow, self.clock).execute(
            actor, (appointment or self.appointment).id
        )

    def start(self, appointment=None):
        return StartConsultation(self.uow, self.clock).execute(
            self.doctor, (appointment or self.appointment).id
        )

    def audit(self, action: str):
        return [e for e in self.uow.audit.query() if e.action == action]


@pytest.fixture
def ctx() -> Setup:
    return Setup()


def test_nursing_records_vitals_on_a_confirmed_appointment(ctx):
    view = ctx.record(ctx.nurse, blood_pressure="120/80", heart_rate=70)

    assert view.phase == "triage" and view.consultation is None
    assert view.vitals.blood_pressure == "120/80"
    assert view.last_saved_at == ctx.clock.now()
    assert ctx.view(ctx.nurse).vitals.heart_rate == 70


def test_nursing_records_vitals_on_a_walk_in(ctx):
    walk_in = RegisterWalkIn(ctx.uow, SequentialCodeGenerator(), ctx.clock).execute(
        ctx.receptionist,
        WalkInCommand(
            patient_id=ctx.seed.patient.id, doctor_id=ctx.seed.doctor.id, reason="Dolor"
        ),
    )
    assert ctx.record(ctx.nurse, walk_in, spo2=97).vitals.spo2 == 97


def test_start_copies_the_vitals_into_the_consultation_and_clears_the_appointment(ctx):
    ctx.record(ctx.nurse, heart_rate=70, spo2=98)

    consultation = ctx.start()

    assert consultation.vitals.heart_rate == 70 and consultation.vitals.spo2 == 98
    assert consultation.last_saved_at == ctx.clock.now()
    stored = ctx.uow.appointments.get_by_id(ctx.appointment.id)
    assert stored.pre_vitals.is_empty() and stored.pre_vitals_saved_at is None
    (started,) = ctx.audit("consultation.started")
    assert started.metadata["pre_vitals"] == ["heart_rate", "spo2"]


def test_start_without_vitals_leaves_the_consultation_as_before(ctx):
    consultation = ctx.start()
    assert consultation.vitals.is_empty() and consultation.last_saved_at is None
    (started,) = ctx.audit("consultation.started")
    assert "pre_vitals" not in started.metadata


def test_once_started_the_view_and_the_writes_go_to_the_consultation(ctx):
    ctx.record(ctx.nurse, heart_rate=70)
    consultation = ctx.start()

    assert ctx.view(ctx.nurse).phase == "consultation"
    view = ctx.record(ctx.nurse, weight=Decimal("70"))

    assert view.consultation.id == consultation.id
    stored = ctx.uow.consultations.get_by_id(consultation.id).vitals
    assert (stored.heart_rate, stored.weight) == (70, Decimal("70"))
    assert ctx.uow.appointments.get_by_id(ctx.appointment.id).pre_vitals.is_empty()


def test_a_signed_consultation_refuses_vitals(ctx):
    consultation = ctx.start()
    AutosaveConsultation(ctx.uow, ctx.clock).execute(
        ctx.doctor, consultation.id,
        ConsultationPatch(note=soap_note("s", "o", "a", "p").texts(), vitals={"heart_rate": 70}),
    )
    SignConsultation(ctx.uow, SequentialCodeGenerator(), ctx.clock).execute(
        ctx.doctor, SignConsultationCommand(consultation.id)
    )
    with pytest.raises(ConsultationAlreadySigned):
        ctx.record(ctx.nurse)
    assert ctx.view(ctx.nurse).phase == "consultation"


@pytest.mark.parametrize("operation", ["record", "view"])
def test_a_scheduled_appointment_does_not_take_vitals_yet(ctx, operation):
    scheduled = ctx.book(START + timedelta(days=1))
    with pytest.raises(DomainError) as exc:
        getattr(ctx, operation)(ctx.nurse, scheduled)
    assert exc.value.code == "appointment.vitals_closed"


def test_a_cancelled_appointment_is_closed_to_vitals(ctx):
    CancelAppointment(ctx.uow, ctx.clock).execute(ctx.receptionist, ctx.appointment.id)
    with pytest.raises(DomainError) as exc:
        ctx.record(ctx.nurse)
    assert exc.value.code == "appointment.vitals_closed"


def test_the_legacy_consultation_view_still_needs_a_started_consultation(ctx):
    with pytest.raises(ConsultationNotStarted):
        GetConsultationVitals(ctx.uow, ctx.clock).execute(ctx.nurse, ctx.appointment.id)


def test_the_owner_doctor_may_but_another_doctor_may_not(ctx):
    ctx.record(ctx.doctor)
    ctx.view(ctx.doctor)
    for operation in (ctx.record, ctx.view):
        with pytest.raises(PermissionDenied) as exc:
            operation(ctx.other)
        assert exc.value.code == "consultation.not_own"


def test_receptionist_and_support_are_refused(ctx):
    for actor, code in (
        (ctx.receptionist, "permission.missing"), (ctx.support, "support.clinical_forbidden"),
    ):
        for operation in (ctx.record, ctx.view):
            with pytest.raises(PermissionDenied) as exc:
                operation(actor)
            assert exc.value.code == code
    assert ctx.uow.appointments.get_by_id(ctx.appointment.id).pre_vitals.is_empty()


def test_the_audit_names_the_fields_and_never_the_values(ctx):
    ctx.record(ctx.nurse, blood_pressure="187/99", heart_rate=70)
    ctx.record(ctx.nurse, heart_rate=70)  # nothing new: not logged again
    ctx.view(ctx.nurse)
    ctx.view(ctx.nurse)  # coalesced

    (updated,) = ctx.audit("consultation.vitals_updated")
    assert (updated.entity_type, updated.entity_id) == ("Appointment", str(ctx.appointment.id))
    assert updated.actor_id == ctx.seed.nurse.id
    assert updated.metadata["keys"] == ["blood_pressure", "heart_rate"]
    assert "187/99" not in str(updated.metadata)
    (viewed,) = ctx.audit("consultation.viewed")
    assert (viewed.entity_type, viewed.metadata["scope"]) == ("Appointment", "vitals")


def test_the_pre_consultation_write_never_locks_the_consultation(ctx):
    ctx.seed.factory.store.lock_log.clear()

    ctx.record(ctx.nurse)

    assert ctx.seed.factory.store.lock_log == [("appointment", ctx.appointment.id.value)]


def test_the_consultation_write_never_locks_the_appointment(ctx):
    consultation = ctx.start()
    ctx.seed.factory.store.lock_log.clear()

    ctx.record(ctx.nurse)

    assert ctx.seed.factory.store.lock_log == [("consultation", consultation.id.value)]


def test_cancelling_or_rescheduling_leaves_no_vitals_behind(ctx):
    ctx.record(ctx.nurse)
    RescheduleAppointment(ctx.uow, ctx.clock).execute(
        ctx.receptionist, ctx.appointment.id, START + timedelta(days=1, hours=1)
    )
    assert ctx.uow.appointments.get_by_id(ctx.appointment.id).pre_vitals.is_empty()

    other = ctx.book(START + timedelta(days=2))
    ConfirmAppointment(ctx.uow, ctx.clock).execute(ctx.receptionist, other.id)
    ctx.record(ctx.nurse, other)
    CancelAppointment(ctx.uow, ctx.clock).execute(ctx.receptionist, other.id)
    assert ctx.uow.appointments.get_by_id(other.id).pre_vitals.is_empty()
