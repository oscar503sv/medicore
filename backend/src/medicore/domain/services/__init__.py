"""Domain services — logic that doesn't naturally belong to a single entity."""

from medicore.domain.services.slot_resolver import (
    BusyInterval,
    Slot,
    SlotStatus,
    is_available,
    resolve_available_slots,
)

__all__ = [
    "BusyInterval",
    "Slot",
    "SlotStatus",
    "is_available",
    "resolve_available_slots",
]
