"""CodeGenerator port — produces human-readable display codes.

Sequential, per-tenant display codes (``P-00142``, ``A-2401``, ``REC-2026-0512-CR``) need
coordination, so generation is an infrastructure concern injected into use cases rather than
something the domain does.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from medicore.domain.enums import ClinicalRecordType


class CodeGenerator(Protocol):
    def next_patient_code(self) -> str: ...

    def next_appointment_code(self) -> str: ...

    def next_record_code(self, record_type: ClinicalRecordType, on: date) -> str: ...
