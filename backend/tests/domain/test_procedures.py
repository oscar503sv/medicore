"""Procedure domain rules: catalog validation, who may perform, consent, signing guards,
immutability (amendments) and cancellation."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from medicore.domain.entities.procedure import (
    Procedure,
    ProcedureClosed,
    ProcedureDraft,
    ProcedureNotCompleted,
    ProcedureProgress,
    ProcedureType,
    can_perform,
)
from medicore.domain.enums import ProcedurePerformer, ProcedureSource, ProcedureStatus, Role
from medicore.domain.services.procedure_catalog import DEFAULT_PROCEDURES
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import (
    PatientId,
    ProcedureId,
    ProcedureTypeId,
    TenantId,
    UserId,
)

NOW = datetime(2026, 6, 5, 15, 0, tzinfo=UTC)
TODAY = date(2026, 6, 5)
DOCTOR = UserId.new()


def _procedure(**kw) -> Procedure:
    return Procedure(
        id=ProcedureId.new(), tenant_id=TenantId.new(), patient_id=PatientId.new(),
        type_id=ProcedureTypeId.new(), type_name=kw.pop("type_name", "Sutura de herida"),
        performer=kw.pop("performer", ProcedurePerformer.DOCTOR),
        requires_consent=kw.pop("requires_consent", True), source=ProcedureSource.DIRECT,
        indication=kw.pop("indication", "Herida en antebrazo"), ordered_by_id=DOCTOR,
        created_by_id=DOCTOR, follow_up_days=kw.pop("follow_up_days", 8), **kw,
    )


def _ready(p: Procedure, **kw) -> None:
    p.save_progress(ProcedureProgress(allergies_reviewed=True, technique="Puntos simples", **kw),
                    NOW)


def test_type_validation_and_who_performs():
    t = ProcedureType(id=ProcedureTypeId.new(), tenant_id=TenantId.new(),
                      name="  Lavado   de oído ", performer=ProcedurePerformer.DOCTOR_OR_NURSE)
    assert t.name == "Lavado de oído"
    with pytest.raises(InvalidValueObject) as exc:
        ProcedureType(id=ProcedureTypeId.new(), tenant_id=TenantId.new(), name=" ")
    assert exc.value.code == "procedure.name_required"
    with pytest.raises(InvalidValueObject) as exc:
        ProcedureType(id=ProcedureTypeId.new(), tenant_id=TenantId.new(), name="X",
                      follow_up_days=0)
    assert exc.value.code == "procedure.invalid_follow_up"
    assert can_perform(ProcedurePerformer.DOCTOR, Role.DOCTOR)
    assert can_perform(ProcedurePerformer.DOCTOR_OR_NURSE, Role.NURSE)
    assert not can_perform(ProcedurePerformer.DOCTOR, Role.NURSE)


def test_default_catalog_is_valid_and_mixes_doctor_and_nursing():
    names = [d.name for d in DEFAULT_PROCEDURES]
    assert len(names) == len(set(names)) >= 10
    assert {d.performer for d in DEFAULT_PROCEDURES} == set(ProcedurePerformer)
    for d in DEFAULT_PROCEDURES:
        ProcedureType(id=ProcedureTypeId.new(), tenant_id=TenantId.new(), name=d.name,
                      performer=d.performer, follow_up_days=d.follow_up_days)


def test_draft_freezes_the_type_rules():
    t = ProcedureType(id=ProcedureTypeId.new(), tenant_id=TenantId.new(), name="Biopsia",
                      requires_consent=True, follow_up_days=10, takes_specimen=True)
    d = ProcedureDraft.of(t, "  Lesión pigmentada  ")
    assert (d.type_name, d.requires_consent, d.follow_up_days, d.indication) == (
        "Biopsia", True, 10, "Lesión pigmentada")
    with pytest.raises(InvalidValueObject) as exc:
        ProcedureDraft.of(t, " ")
    assert exc.value.code == "procedure.indication_required"


def test_signing_needs_consent_allergy_review_and_technique():
    p = _procedure()
    with pytest.raises(InvalidValueObject) as exc:
        p.sign(DOCTOR, NOW, TODAY, False)
    assert exc.value.code == "procedure.consent_required"
    with pytest.raises(InvalidValueObject) as exc:
        p.record_consent("Ana Pérez", None, " ", DOCTOR, NOW)
    assert exc.value.code == "procedure.consent_incomplete"
    p.record_consent("Ana Pérez", None, "Lucía Méndez", DOCTOR, NOW)
    assert p.status == ProcedureStatus.IN_PROGRESS and p.has_consent
    with pytest.raises(InvalidValueObject) as exc:
        p.sign(DOCTOR, NOW, TODAY, False)
    assert exc.value.code == "procedure.allergies_not_reviewed"
    p.save_progress(ProcedureProgress(allergies_reviewed=True), NOW)
    with pytest.raises(InvalidValueObject) as exc:
        p.sign(DOCTOR, NOW, TODAY, False)
    assert exc.value.code == "procedure.technique_required"
    _ready(p, specimen_sent=True)
    with pytest.raises(InvalidValueObject) as exc:
        p.sign(DOCTOR, NOW, TODAY, False)
    assert exc.value.code == "procedure.specimen_required"
    _ready(p, anesthesia="Lidocaína 2 %")
    with pytest.raises(InvalidValueObject) as exc:
        p.sign(DOCTOR, NOW, TODAY, True)
    assert exc.value.code == "procedure.allergy_conflict"
    _ready(p, anesthesia="Lidocaína 2 %", allergy_override="Prueba previa negativa")
    p.sign(DOCTOR, NOW, TODAY, True)
    assert p.status == ProcedureStatus.COMPLETED and p.performed_by_id == DOCTOR
    assert p.follow_up_on == date(2026, 6, 13)
    assert p.allergy_override == "Prueba previa negativa"


def test_signed_note_is_immutable_and_takes_amendments():
    p = _procedure(requires_consent=False, follow_up_days=None)
    _ready(p, allergy_override="sin choque")
    p.sign(DOCTOR, NOW, TODAY, False)
    assert p.follow_up_on is None and p.allergy_override is None  # no clash → dropped
    with pytest.raises(ProcedureClosed):
        _ready(p)
    with pytest.raises(ProcedureClosed):
        p.cancel(DOCTOR, "x", NOW)
    with pytest.raises(InvalidValueObject) as exc:
        p.amend(DOCTOR, "Fueron 4 puntos", " ", NOW)
    assert exc.value.code == "procedure.amendment_required"
    p.amend(DOCTOR, "Fueron 4 puntos, no 3", "Conteo corregido", NOW)
    assert [a.text for a in p.amendments] == ["Fueron 4 puntos, no 3"]
    assert p.technique == "Puntos simples"


def test_cancel_and_amend_guards_and_vitals_validation():
    p = _procedure()
    with pytest.raises(ProcedureNotCompleted):
        p.amend(DOCTOR, "x", "y", NOW)
    with pytest.raises(InvalidValueObject) as exc:
        p.cancel(DOCTOR, " ", NOW)
    assert exc.value.code == "procedure.reason_required"
    p.cancel(DOCTOR, "El paciente no se presentó", NOW)
    assert p.status == ProcedureStatus.CANCELLED and not p.is_open
    with pytest.raises(InvalidValueObject) as exc:
        ProcedureProgress(bp_before="120-80")
    assert exc.value.code == "vitals.invalid_blood_pressure"
    with pytest.raises(InvalidValueObject) as exc:
        ProcedureProgress(spo2_after=30)
    assert exc.value.code == "procedure.invalid_vitals"
