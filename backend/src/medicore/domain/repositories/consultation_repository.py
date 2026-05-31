"""ConsultationRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.consultation import Consultation
from medicore.domain.shared.identifiers import AppointmentId, ConsultationId


class ConsultationRepository(Protocol):
    def get_by_id(self, consultation_id: ConsultationId) -> Consultation | None: ...

    def get_by_appointment(self, appointment_id: AppointmentId) -> Consultation | None: ...

    def save(self, consultation: Consultation) -> None: ...
