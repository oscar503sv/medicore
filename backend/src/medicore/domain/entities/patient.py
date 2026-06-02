"""Patient aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from medicore.domain.enums import PatientStatus, Sex
from medicore.domain.shared.identifiers import PatientId, TenantId, UserId
from medicore.domain.value_objects.blood_type import BloodType
from medicore.domain.value_objects.contact_info import ContactInfo


@dataclass(slots=True)
class Patient:
    """A patient record.

    Derived facts (last/next visit, note counts) are computed via queries and are NOT stored
    on the aggregate.
    """

    id: PatientId
    tenant_id: TenantId
    code: str  # human-readable, e.g. "P-00142"
    first_name: str
    last_name: str
    sex: Sex
    date_of_birth: date
    contact: ContactInfo = field(default_factory=ContactInfo)
    blood_type: BloodType | None = None
    primary_doctor_id: UserId | None = None
    status: PatientStatus = PatientStatus.ACTIVE
    tags: list[str] = field(default_factory=list)  # clinical conditions, e.g. "Hipertensión"
    allergies: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def age(self, on: date | None = None) -> int:
        """Age in completed years as of ``on`` (defaults to today)."""
        ref = on or date.today()
        years = ref.year - self.date_of_birth.year
        if (ref.month, ref.day) < (self.date_of_birth.month, self.date_of_birth.day):
            years -= 1
        return years

    def archive(self) -> None:
        self.status = PatientStatus.INACTIVE
        self._touch()

    def reactivate(self) -> None:
        self.status = PatientStatus.ACTIVE
        self._touch()

    def add_allergy(self, allergy: str) -> None:
        if allergy not in self.allergies:
            self.allergies.append(allergy)
            self._touch()

    def add_tag(self, tag: str) -> None:
        if tag not in self.tags:
            self.tags.append(tag)
            self._touch()

    def _touch(self) -> None:
        self.updated_at = datetime.now(UTC)
