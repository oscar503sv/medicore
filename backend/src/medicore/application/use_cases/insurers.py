"""Insurer use cases (admin-managed catalog).

Listing is open to any authenticated role (patients pick an insurer when registering);
creating/updating/archiving requires admin, mirroring organization management.
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.insurer import Insurer
from medicore.domain.shared.identifiers import InsurerId


@dataclass(frozen=True, slots=True)
class CreateInsurerCommand:
    name: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    contact_person: str | None = None
    notes: str | None = None


class ListInsurers:
    """All insurers for the tenant. Open to every role — populates the patient selector."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext, active_only: bool = False) -> list[Insurer]:
        ensure_permission(actor, Permission.INSURERS_VIEW)
        return self._uow.insurers.list(active_only=active_only)


class CreateInsurer:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: CreateInsurerCommand) -> Insurer:
        ensure_permission(actor, Permission.INSURERS_MANAGE)
        insurer = Insurer(
            id=InsurerId.new(),
            tenant_id=actor.tenant_id,
            name=cmd.name,
            phone=cmd.phone,
            email=cmd.email,
            address=cmd.address,
            contact_person=cmd.contact_person,
            notes=cmd.notes,
            created_at=self._clock.now(),
            updated_at=self._clock.now(),
        )
        with self._uow:
            self._uow.insurers.save(insurer)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "insurer.created", "Insurer", str(insurer.id),
                    subject=subject(insurer.name),
                )
            )
            self._uow.commit()
        return insurer


class UpdateInsurer:
    _EDITABLE = {"name", "phone", "email", "address", "contact_person", "notes"}

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, insurer_id: InsurerId, **changes: object) -> Insurer:
        ensure_permission(actor, Permission.INSURERS_MANAGE)
        insurer = self._require(insurer_id)
        with self._uow:
            for key, value in changes.items():
                if key in self._EDITABLE:
                    setattr(insurer, key, value)
            insurer.updated_at = self._clock.now()
            self._uow.insurers.save(insurer)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "insurer.updated", "Insurer", str(insurer.id),
                    subject=subject(insurer.name),
                )
            )
            self._uow.commit()
        return insurer

    def _require(self, insurer_id: InsurerId) -> Insurer:
        insurer = self._uow.insurers.get_by_id(insurer_id)
        if insurer is None:
            raise EntityNotFound("Insurer", insurer_id)
        return insurer


class ArchiveInsurer:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, insurer_id: InsurerId) -> Insurer:
        ensure_permission(actor, Permission.INSURERS_MANAGE)
        insurer = self._uow.insurers.get_by_id(insurer_id)
        if insurer is None:
            raise EntityNotFound("Insurer", insurer_id)
        with self._uow:
            insurer.archive()
            self._uow.insurers.save(insurer)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "insurer.archived", "Insurer", str(insurer.id),
                    subject=subject(insurer.name),
                )
            )
            self._uow.commit()
        return insurer
