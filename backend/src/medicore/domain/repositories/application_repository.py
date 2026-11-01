"""ApplicationRepository port: in-clinic medication orders and the record of each dose."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from medicore.domain.entities.application import ApplicationOrder, ApplicationRecord
from medicore.domain.shared.identifiers import (
    ApplicationOrderId,
    ApplicationRecordId,
    PatientId,
)


class ApplicationRepository(Protocol):
    def get_order(self, order_id: ApplicationOrderId) -> ApplicationOrder | None: ...

    def list_orders_by_patient(self, patient_id: PatientId) -> list[ApplicationOrder]:
        """Every order of the patient, newest first."""
        ...

    def list_open_orders(self) -> list[ApplicationOrder]:
        """Pending or in-progress orders (the worklist)."""
        ...

    def save_order(self, order: ApplicationOrder) -> None: ...

    def get_record(self, record_id: ApplicationRecordId) -> ApplicationRecord | None: ...

    def list_records_by_orders(
        self, order_ids: list[ApplicationOrderId]
    ) -> list[ApplicationRecord]:
        """Every record (voided included) of the given orders, oldest first."""
        ...

    def list_records_between(self, start: datetime, end: datetime) -> list[ApplicationRecord]:
        """Non-voided records with ``start <= recorded_at < end`` (instants), newest first."""
        ...

    def list_observing(self) -> list[ApplicationRecord]:
        """Applied doses whose observation is still open, oldest first."""
        ...

    def save_record(self, record: ApplicationRecord) -> None: ...
