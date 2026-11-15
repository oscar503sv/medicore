"""Prescription lifecycle use cases.

Prescriptions are issued when a consultation is signed (see ``SignConsultation``); here
they are listed and moved through their lifecycle: active → completed | cancelled.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import (
    Permission,
    ensure_not_support,
    ensure_permission,
    has_permission,
)
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.prescription import Prescription
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import PatientId, PrescriptionId, UserId


@dataclass(frozen=True, slots=True)
class PrescriptionView:
    prescription: Prescription
    prescriber_name: str | None  # None → the prescriber no longer exists in the tenant
    cancel_reason: str | None  # the reason is clinical: only who may read clinical content sees it


class ListPatientPrescriptions:
    """Every prescription of a patient, any status, newest first."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, patient_id: PatientId) -> list[PrescriptionView]:
        ensure_permission(actor, Permission.RECORDS_VIEW)
        prescriptions = self._uow.prescriptions.list_by_patient(patient_id)
        prescriptions.sort(key=lambda p: p.created_at, reverse=True)
        names: dict[UserId, str | None] = {}
        for p in prescriptions:
            if p.prescriber_id not in names:
                prescriber = self._uow.users.get_by_id(p.prescriber_id)
                names[p.prescriber_id] = prescriber.name if prescriber else None
        can_read_reason = has_permission(actor, Permission.RECORDS_READ_CLINICAL)
        views = [
            PrescriptionView(
                p, names[p.prescriber_id], p.cancel_reason if can_read_reason else None
            )
            for p in prescriptions
        ]
        patient = self._uow.patients.get_by_id(patient_id)
        with self._uow:
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "prescription.listed", "Patient", str(patient_id),
                    count=len(views),
                    subject=subject(patient.code, patient.full_name) if patient else None,
                )
            )
            self._uow.commit()
        return views


class _PrescriptionTransition:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _transition(
        self,
        actor: ActorContext,
        prescription_id: PrescriptionId,
        apply: Callable[[Prescription, datetime], None],
        action: str,
        **audit_details: object,
    ) -> Prescription:
        ensure_permission(actor, Permission.PRESCRIPTIONS_MANAGE)
        ensure_not_support(actor)
        with self._uow:
            # Locked so a concurrent complete/cancel waits and then finds the prescription
            # already closed (invalid_transition) instead of closing it twice.
            prescription = self._uow.prescriptions.get_for_update(prescription_id)
            if prescription is None:
                raise EntityNotFound("Prescription", prescription_id)
            if prescription.prescriber_id != actor.user_id:
                raise PermissionDenied(
                    "only the prescriber closes a prescription", code="prescription.not_own"
                )
            now = self._clock.now()
            apply(prescription, now)
            self._uow.prescriptions.save(prescription)
            self._uow.audit.append(
                audit_entry(
                    actor, now, action, "Prescription", str(prescription.id),
                    subject=subject(prescription.drug), **audit_details,
                )
            )
            self._uow.commit()
        return prescription


class CompletePrescription(_PrescriptionTransition):
    def execute(self, actor: ActorContext, prescription_id: PrescriptionId) -> Prescription:
        return self._transition(
            actor, prescription_id, lambda p, now: p.complete(actor.user_id, now),
            "prescription.completed",
        )


class CancelPrescription(_PrescriptionTransition):
    def execute(
        self, actor: ActorContext, prescription_id: PrescriptionId, *, reason: str
    ) -> Prescription:
        # The reason's text stays in the prescription; the audit trail only records its size.
        return self._transition(
            actor, prescription_id, lambda p, now: p.cancel(actor.user_id, reason, now),
            "prescription.cancelled", reason_chars=len(reason.strip()),
        )
