"""ConsultationRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.consultation import Consultation
from medicore.domain.shared.identifiers import AppointmentId, ConsultationId


class ConsultationRepository(Protocol):
    def get_by_id(self, consultation_id: ConsultationId) -> Consultation | None: ...

    def get_by_appointment(self, appointment_id: AppointmentId) -> Consultation | None: ...

    def get_for_update(self, consultation_id: ConsultationId) -> Consultation | None:
        """Load the consultation and hold its row until the transaction ends, so a sign and
        any edit of the same consultation run one after another and each sees what the
        other committed.

        Lock order everywhere (see ``AppointmentRepository.get_for_update``): consultation,
        then the appointment, then the record-code counter. Starting a consultation only
        locks the appointment.
        """
        ...

    def save(self, consultation: Consultation) -> None: ...
