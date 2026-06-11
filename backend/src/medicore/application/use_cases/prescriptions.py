"""Prescription lifecycle use cases.

Prescriptions are issued when a consultation is signed (see ``SignConsultation``); here
they are listed and moved through their lifecycle: active → completed | cancelled.
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.prescription import Prescription
from medicore.domain.shared.identifiers import PatientId, PrescriptionId


@dataclass(frozen=True, slots=True)
class PrescriptionView:
    prescription: Prescription
    prescriber_name: str | None  # None → the prescriber no longer exists in the tenant


class ListPatientPrescriptions:
    """Every prescription of a patient, any status, newest first."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext, patient_id: PatientId) -> list[PrescriptionView]:
        ensure_permission(actor, Permission.RECORDS_VIEW)
        prescriptions = self._uow.prescriptions.list_by_patient(patient_id)
        prescriptions.sort(key=lambda p: p.created_at, reverse=True)
        views = []
        for p in prescriptions:
            prescriber = self._uow.users.get_by_id(p.prescriber_id)
            views.append(PrescriptionView(p, prescriber.name if prescriber else None))
        return views


class _PrescriptionTransition:
    action: str  # audit action, e.g. "prescription.completed"

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, prescription_id: PrescriptionId) -> Prescription:
        ensure_permission(actor, Permission.PRESCRIPTIONS_MANAGE)
        prescription = self._uow.prescriptions.get_by_id(prescription_id)
        if prescription is None:
            raise EntityNotFound("Prescription", prescription_id)
        with self._uow:
            self._apply(prescription)
            self._uow.prescriptions.save(prescription)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), self.action, "Prescription",
                    str(prescription.id), subject=subject(prescription.drug),
                )
            )
            self._uow.commit()
        return prescription

    def _apply(self, prescription: Prescription) -> None:
        raise NotImplementedError


class CompletePrescription(_PrescriptionTransition):
    action = "prescription.completed"

    def _apply(self, prescription: Prescription) -> None:
        prescription.complete()


class CancelPrescription(_PrescriptionTransition):
    action = "prescription.cancelled"

    def _apply(self, prescription: Prescription) -> None:
        prescription.cancel()
