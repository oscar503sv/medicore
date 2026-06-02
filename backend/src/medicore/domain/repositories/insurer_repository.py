"""InsurerRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.insurer import Insurer
from medicore.domain.shared.identifiers import InsurerId


class InsurerRepository(Protocol):
    def get_by_id(self, insurer_id: InsurerId) -> Insurer | None: ...

    def list(self, active_only: bool = False) -> list[Insurer]: ...

    def save(self, insurer: Insurer) -> None: ...
