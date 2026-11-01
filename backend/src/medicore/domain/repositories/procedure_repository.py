"""ProcedureRepository port: the clinic's procedure catalog and the procedures done."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from medicore.domain.entities.procedure import Procedure, ProcedureType
from medicore.domain.shared.identifiers import (
    AppointmentId,
    PatientId,
    ProcedureId,
    ProcedureTypeId,
)


class ProcedureRepository(Protocol):
    # ── catalog ──
    def get_type(self, type_id: ProcedureTypeId) -> ProcedureType | None: ...

    def list_types(self) -> list[ProcedureType]:
        """Every type of the clinic (archived included), by name."""
        ...

    def save_type(self, kind: ProcedureType) -> None: ...

    # ── procedures ──
    def get(self, procedure_id: ProcedureId) -> Procedure | None: ...

    def list_by_patient(self, patient_id: PatientId) -> list[Procedure]:
        """Every procedure of the patient, newest first."""
        ...

    def list_open(self) -> list[Procedure]:
        """Pending or in-progress procedures, oldest first."""
        ...

    def list_by_appointments(self, appointment_ids: list[AppointmentId]) -> list[Procedure]: ...

    def list_completed_between(self, start: datetime, end: datetime) -> list[Procedure]:
        """Signed with ``start <= performed_at < end`` (instants), newest first."""
        ...

    def save(self, procedure: Procedure) -> None: ...
