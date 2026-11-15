"""Who may do what in a consultation: the doctor owns the content, nursing records vitals,
the admin may open it, support never touches it. Plus the audit of reads and edits."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import ConsultationNotStarted
from medicore.application.use_cases.appointments import (
    CreateAppointment,
    CreateAppointmentCommand,
)
from medicore.application.use_cases.consultations import (
    AddDiagnosis,
    AddExam,
    AddPrescriptionDraft,
    AutosaveConsultation,
    ChangeNoteTemplate,
    ConsultationPatch,
    GetConsultation,
    GetConsultationVitals,
    RemoveDiagnosis,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
    UpdateConsultationVitals,
)
from medicore.domain.entities.prescription import PrescriptionDraft
from medicore.domain.enums import AppointmentType, Role
from medicore.domain.shared.errors import ConsultationAlreadySigned, PermissionDenied
from medicore.domain.shared.identifiers import PlatformAdminId
from medicore.domain.value_objects.exam_request import ExamRequest
from medicore.domain.value_objects.icd_code import IcdCode
from tests.support.builders import build_user, seed_clinic, soap_note
from tests.support.fakes import FixedClock, SequentialCodeGenerator

START = datetime(2026, 6, 1, 9, 0)
SECRET_NOTE = "dolor torácico irradiado al brazo izquierdo"


class Setup:
    def __init__(self) -> None:
        self.seed = seed_clinic()
        self.uow = self.seed.factory.for_tenant(self.seed.tenant.id)
        self.clock = FixedClock()
        self.other_doctor = build_user(
            self.seed.tenant.id, Role.DOCTOR, name="Dr. Otro", email="otro@clinica-norte.test"
        )
        self.seed.factory.store.users[self.other_doctor.id.value] = self.other_doctor
        self.admin = self.seed.actor(self.seed.admin)
        self.nurse = self.seed.actor(self.seed.nurse)
        self.doctor = self.seed.doctor_actor
        self.other = self.seed.actor(self.other_doctor)
        self.receptionist = self.seed.receptionist_actor
        self.support = ActorContext(
            user_id=self.seed.admin.id, tenant_id=self.seed.tenant.id, role=Role.ADMIN,
            impersonated_by=PlatformAdminId.new(),
        )
        self.delegated = ActorContext(
            user_id=self.seed.receptionist.id, tenant_id=self.seed.tenant.id,
            role=Role.RECEPTIONIST,
            permissions=frozenset({"consultations.vitals", "appointments.view"}),
        )
        create = CreateAppointment(self.uow, SequentialCodeGenerator(), self.clock)
        self.appointment = create.execute(
            self.doctor,
            CreateAppointmentCommand(
                patient_id=self.seed.patient.id, doctor_id=self.seed.doctor.id,
                location_id=self.seed.tenant.primary_location.id, type=AppointmentType.CONSULT,
                scheduled_start=START, reason="Control",
            ),
        )
        self.consultation = StartConsultation(self.uow, self.clock).execute(
            self.doctor, self.appointment.id
        )

    def audit(self, action: str):
        return [e for e in self.uow.audit.query() if e.action == action]


@pytest.fixture
def ctx() -> Setup:
    return Setup()


def _get(ctx, actor):
    return GetConsultation(ctx.uow, ctx.clock).execute(actor, ctx.consultation.id)


def _autosave(ctx, actor):
    return AutosaveConsultation(ctx.uow, ctx.clock).execute(
        actor, ctx.consultation.id, ConsultationPatch(note={"plan": "x"})
    )


def _template(ctx, actor):
    return ChangeNoteTemplate(ctx.uow, ctx.clock).execute(actor, ctx.consultation.id, "soap")


def _diagnosis(ctx, actor):
    return AddDiagnosis(ctx.uow, ctx.clock).execute(
        actor, ctx.consultation.id, IcdCode("I10", "HTA")
    )


def _prescription(ctx, actor):
    return AddPrescriptionDraft(ctx.uow, ctx.clock).execute(
        actor, ctx.consultation.id,
        PrescriptionDraft(drug="Enalapril", dose="20 mg", schedule="1x", duration_days=30),
    )


def _exam(ctx, actor):
    return AddExam(ctx.uow, ctx.clock).execute(
        actor, ctx.consultation.id, ExamRequest(name="Hemograma")
    )


def _sign(ctx, actor):
    return SignConsultation(ctx.uow, SequentialCodeGenerator(), ctx.clock).execute(
        actor, SignConsultationCommand(consultation_id=ctx.consultation.id)
    )


CONTENT_OPERATIONS = [_get, _autosave, _template, _diagnosis, _prescription, _exam, _sign]


@pytest.mark.parametrize("operation", CONTENT_OPERATIONS)
class TestContentIsTheOwnerDoctors:
    def test_admin_nurse_and_receptionist_lack_the_permission(self, ctx, operation):
        for actor in (ctx.admin, ctx.nurse, ctx.receptionist):
            with pytest.raises(PermissionDenied) as exc:
                operation(ctx, actor)
            assert exc.value.code == "permission.missing"

    def test_another_doctor_is_refused_by_ownership(self, ctx, operation):
        with pytest.raises(PermissionDenied) as exc:
            operation(ctx, ctx.other)
        assert exc.value.code == "consultation.not_own"

    def test_support_is_refused(self, ctx, operation):
        with pytest.raises(PermissionDenied):
            operation(ctx, ctx.support)


def test_the_owner_does_everything(ctx):
    for operation in (_get, _autosave, _template, _diagnosis, _prescription, _exam):
        operation(ctx, ctx.doctor)


def test_support_session_on_a_doctor_account_is_refused_by_the_guard(ctx):
    impersonating_the_doctor = ActorContext(
        user_id=ctx.seed.doctor.id, tenant_id=ctx.seed.tenant.id, role=Role.DOCTOR,
        impersonated_by=PlatformAdminId.new(),
    )
    for operation in (_get, _autosave, _diagnosis, _sign):
        with pytest.raises(PermissionDenied) as exc:
            operation(ctx, impersonating_the_doctor)
        assert exc.value.code == "support.clinical_forbidden"


class TestStart:
    def _fresh(self, ctx):
        appointment = CreateAppointment(ctx.uow, SequentialCodeGenerator(), ctx.clock).execute(
            ctx.doctor,
            CreateAppointmentCommand(
                patient_id=ctx.seed.patient.id, doctor_id=ctx.seed.doctor.id,
                location_id=ctx.seed.tenant.primary_location.id,
                type=AppointmentType.CONSULT, scheduled_start=START + timedelta(days=1),
                reason="Otra",
            ),
        )
        return appointment.id

    def test_admin_may_start_any_doctors_consultation(self, ctx):
        consultation = StartConsultation(ctx.uow, ctx.clock).execute(ctx.admin, self._fresh(ctx))
        assert consultation.doctor_id == ctx.seed.doctor.id

    def test_another_doctor_may_not_start_it(self, ctx):
        with pytest.raises(PermissionDenied) as exc:
            StartConsultation(ctx.uow, ctx.clock).execute(ctx.other, self._fresh(ctx))
        assert exc.value.code == "consultation.not_own"

    def test_nurse_may_not_start(self, ctx):
        with pytest.raises(PermissionDenied):
            StartConsultation(ctx.uow, ctx.clock).execute(ctx.nurse, self._fresh(ctx))

    def test_support_may_not_start(self, ctx):
        with pytest.raises(PermissionDenied) as exc:
            StartConsultation(ctx.uow, ctx.clock).execute(ctx.support, self._fresh(ctx))
        assert exc.value.code == "support.clinical_forbidden"


def _record_vitals(ctx, actor, **changes):
    return UpdateConsultationVitals(ctx.uow, ctx.clock).execute(
        actor, ctx.consultation.id, changes or {"heart_rate": 70}
    )


def _view_vitals(ctx, actor):
    return GetConsultationVitals(ctx.uow, ctx.clock).execute(actor, ctx.appointment.id)


@pytest.mark.parametrize("operation", [_record_vitals, _view_vitals])
class TestVitals:
    def test_nurse_and_the_owner_doctor_may(self, ctx, operation):
        operation(ctx, ctx.nurse)
        operation(ctx, ctx.doctor)

    def test_a_delegated_receptionist_may(self, ctx, operation):
        operation(ctx, ctx.delegated)

    def test_admin_and_plain_receptionist_may_not(self, ctx, operation):
        for actor in (ctx.admin, ctx.receptionist):
            with pytest.raises(PermissionDenied) as exc:
                operation(ctx, actor)
            assert exc.value.code == "permission.missing"

    def test_another_doctor_may_not(self, ctx, operation):
        with pytest.raises(PermissionDenied) as exc:
            operation(ctx, ctx.other)
        assert exc.value.code == "consultation.not_own"

    def test_support_may_not(self, ctx, operation):
        with pytest.raises(PermissionDenied) as exc:
            operation(ctx, ctx.support)
        assert exc.value.code == "support.clinical_forbidden"


def test_vitals_view_before_the_consultation_started_is_a_coded_not_found(ctx):
    other_appointment = CreateAppointment(ctx.uow, SequentialCodeGenerator(), ctx.clock).execute(
        ctx.doctor,
        CreateAppointmentCommand(
            patient_id=ctx.seed.patient.id, doctor_id=ctx.seed.doctor.id,
            location_id=ctx.seed.tenant.primary_location.id, type=AppointmentType.CONSULT,
            scheduled_start=START + timedelta(days=2), reason="Aún no",
        ),
    )
    with pytest.raises(ConsultationNotStarted) as exc:
        GetConsultationVitals(ctx.uow, ctx.clock).execute(ctx.nurse, other_appointment.id)
    assert exc.value.code == "consultation.not_started"


def test_the_vitals_view_has_the_patient_the_booking_and_the_doctor_name(ctx):
    _autosave(ctx, ctx.doctor)
    view = _view_vitals(ctx, ctx.nurse)
    assert view.patient is not None and view.appointment is not None
    assert view.doctor_name == ctx.seed.doctor.name


def test_vitals_on_a_signed_consultation_are_refused(ctx):
    AutosaveConsultation(ctx.uow, ctx.clock).execute(
        ctx.doctor, ctx.consultation.id,
        ConsultationPatch(
            note=soap_note("s", "o", "a", "p").texts(), vitals={"heart_rate": 70}
        ),
    )
    _diagnosis(ctx, ctx.doctor)
    _sign(ctx, ctx.doctor)
    with pytest.raises(ConsultationAlreadySigned):
        _record_vitals(ctx, ctx.nurse)


def test_nursing_and_the_doctor_do_not_erase_each_others_vitals(ctx):
    _record_vitals(ctx, ctx.nurse, blood_pressure="130/85", heart_rate=80)
    AutosaveConsultation(ctx.uow, ctx.clock).execute(
        ctx.doctor, ctx.consultation.id, ConsultationPatch(vitals={"weight": Decimal("70")})
    )
    vitals = ctx.uow.consultations.get_by_id(ctx.consultation.id).vitals
    assert (vitals.blood_pressure, vitals.heart_rate, vitals.weight) == (
        "130/85", 80, Decimal("70"),
    )


class TestAudit:
    def test_opening_is_logged_once_per_window(self, ctx):
        _get(ctx, ctx.doctor)
        _get(ctx, ctx.doctor)
        assert len(ctx.audit("consultation.viewed")) == 1
        ctx.clock.set(ctx.clock.now() + timedelta(minutes=11))
        _get(ctx, ctx.doctor)
        assert len(ctx.audit("consultation.viewed")) == 2

    def test_the_two_views_are_logged_separately(self, ctx):
        _get(ctx, ctx.doctor)
        _view_vitals(ctx, ctx.doctor)
        scopes = sorted(e.metadata["scope"] for e in ctx.audit("consultation.viewed"))
        assert scopes == ["full", "vitals"]

    def test_autosave_repeats_of_the_same_section_are_one_entry(self, ctx):
        for text in ("a", "ab", "abc"):
            AutosaveConsultation(ctx.uow, ctx.clock).execute(
                ctx.doctor, ctx.consultation.id, ConsultationPatch(note={"plan": text})
            )
        entries = ctx.audit("consultation.note_updated")
        assert len(entries) == 1 and entries[0].metadata["keys"] == ["plan"]

    def test_a_new_section_adds_an_entry_and_the_window_expires(self, ctx):
        patch = lambda note: AutosaveConsultation(ctx.uow, ctx.clock).execute(  # noqa: E731
            ctx.doctor, ctx.consultation.id, ConsultationPatch(note=note)
        )
        patch({"plan": "a"})
        patch({"subjective": "b"})
        assert [e.metadata["keys"] for e in ctx.audit("consultation.note_updated")] == [
            ["plan"], ["subjective"],
        ]
        ctx.clock.set(ctx.clock.now() + timedelta(minutes=11))
        patch({"plan": "c"})
        assert len(ctx.audit("consultation.note_updated")) == 3

    def test_an_autosave_that_changes_nothing_logs_nothing(self, ctx):
        _autosave(ctx, ctx.doctor)
        before = len(ctx.audit("consultation.note_updated"))
        _autosave(ctx, ctx.doctor)
        AutosaveConsultation(ctx.uow, ctx.clock).execute(
            ctx.doctor, ctx.consultation.id, ConsultationPatch(note={}, vitals={})
        )
        assert len(ctx.audit("consultation.note_updated")) == before
        assert ctx.audit("consultation.vitals_updated") == []

    def test_vitals_entries_name_the_fields_and_record_who(self, ctx):
        _record_vitals(ctx, ctx.nurse, blood_pressure="120/80", heart_rate=70)
        _record_vitals(ctx, ctx.nurse, heart_rate=70)
        (entry,) = ctx.audit("consultation.vitals_updated")
        assert entry.metadata["keys"] == ["blood_pressure", "heart_rate"]
        assert entry.actor_id == ctx.seed.nurse.id

    def test_metadata_never_carries_clinical_text(self, ctx):
        AutosaveConsultation(ctx.uow, ctx.clock).execute(
            ctx.doctor, ctx.consultation.id,
            ConsultationPatch(note={"subjective": SECRET_NOTE}, vitals={"heart_rate": 99}),
        )
        _diagnosis(ctx, ctx.doctor)
        _prescription(ctx, ctx.doctor)
        _exam(ctx, ctx.doctor)
        RemoveDiagnosis(ctx.uow, ctx.clock).execute(ctx.doctor, ctx.consultation.id, "I10")
        for entry in ctx.uow.audit.query():
            text = str(entry.metadata)
            for secret in (SECRET_NOTE, "I10", "HTA", "Enalapril", "Hemograma"):
                assert secret not in text

    def test_draft_changes_log_section_and_operation(self, ctx):
        _diagnosis(ctx, ctx.doctor)
        _exam(ctx, ctx.doctor)
        RemoveDiagnosis(ctx.uow, ctx.clock).execute(ctx.doctor, ctx.consultation.id, "I10")
        entries = ctx.audit("consultation.draft_changed")
        changes = [(e.metadata["section"], e.metadata["op"]) for e in entries]
        assert changes == [("diagnoses", "added"), ("exams", "added"), ("diagnoses", "removed")]

    def test_a_template_change_logs_from_and_to_only_when_it_changed(self, ctx):
        current = ctx.consultation.note.template
        ChangeNoteTemplate(ctx.uow, ctx.clock).execute(ctx.doctor, ctx.consultation.id, current)
        assert ctx.audit("consultation.template_changed") == []
        other = "narrative" if current != "narrative" else "soap"
        ChangeNoteTemplate(ctx.uow, ctx.clock).execute(ctx.doctor, ctx.consultation.id, other)
        (entry,) = ctx.audit("consultation.template_changed")
        assert (entry.metadata["from"], entry.metadata["to"]) == (current, other)

    def test_support_actions_would_carry_the_marker_but_are_refused_before_logging(self, ctx):
        with pytest.raises(PermissionDenied):
            _get(ctx, ctx.support)
        assert ctx.audit("consultation.viewed") == []
