"""Role-permission customization use cases (tenant admin).

A tenant may customize which permissions each role holds, within guardrails:

* ADMIN is never customizable — it always keeps the code defaults, so the clinic can
  never lock itself out of permission management.
* ``records.sign`` and ``records.amend`` belong exclusively to DOCTOR: they cannot be
  granted to other roles nor removed from the doctor (a clinic where nobody can sign
  is broken).
* Writes must be a subset of the current catalog; reads tolerate stale strings.
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import ValidationError
from medicore.application.common.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    effective_permissions,
    ensure_permission,
)
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.role_permission_override import RolePermissionOverride
from medicore.domain.enums import Role
from medicore.domain.shared.identifiers import RolePermissionOverrideId, TenantId

DOCTOR_ONLY = frozenset({Permission.RECORDS_SIGN, Permission.RECORDS_AMEND})


@dataclass(frozen=True, slots=True)
class RolePermissionsDTO:
    defaults: tuple[str, ...]
    effective: tuple[str, ...]
    customized: bool


@dataclass(frozen=True, slots=True)
class PermissionsMatrixDTO:
    catalog: tuple[str, ...]
    roles: dict[Role, RolePermissionsDTO]


def build_matrix(uow: UnitOfWork) -> PermissionsMatrixDTO:
    """Assemble catalog + per-role defaults/effective/customized for one tenant."""
    overrides = {o.role: o for o in uow.role_permissions.list()}
    roles: dict[Role, RolePermissionsDTO] = {}
    for role in Role:
        override = overrides.get(role)
        stored = override.permissions if override else None
        roles[role] = RolePermissionsDTO(
            defaults=tuple(sorted(str(p) for p in ROLE_PERMISSIONS[role])),
            effective=tuple(sorted(str(p) for p in effective_permissions(role, stored))),
            customized=override is not None,
        )
    return PermissionsMatrixDTO(
        catalog=tuple(sorted(str(p) for p in Permission)),
        roles=roles,
    )


def validate_role_update(role: Role, permissions: list[str]) -> frozenset[Permission]:
    """Apply the customization guardrails; return the parsed permission set."""
    if role == Role.ADMIN:
        raise ValidationError("the admin role is not customizable")
    catalog = {str(p): p for p in Permission}
    unknown = [s for s in permissions if s not in catalog]
    if unknown:
        raise ValidationError(f"unknown permissions: {', '.join(sorted(unknown))}")
    parsed = frozenset(catalog[s] for s in permissions)
    if role == Role.DOCTOR:
        missing = DOCTOR_ONLY - parsed
        if missing:
            raise ValidationError(
                "the doctor role must keep: " + ", ".join(sorted(str(p) for p in missing))
            )
    else:
        forbidden = DOCTOR_ONLY & parsed
        if forbidden:
            raise ValidationError(
                "only the doctor role may hold: "
                + ", ".join(sorted(str(p) for p in forbidden))
            )
    return parsed


def upsert_override(
    uow: UnitOfWork, tenant_id: TenantId, role: Role, parsed: frozenset[Permission], now
) -> RolePermissionOverride:
    existing = uow.role_permissions.get_by_role(role)
    override = existing or RolePermissionOverride(
        id=RolePermissionOverrideId.new(),
        tenant_id=tenant_id,
        role=role,
        permissions=(),
        created_at=now,
    )
    override.permissions = tuple(sorted(str(p) for p in parsed))
    override.updated_at = now
    uow.role_permissions.save(override)
    return override


def diff_for_audit(role: Role, before: frozenset[Permission], after: frozenset[Permission]):
    return {
        "role": str(role),
        "added": sorted(str(p) for p in after - before),
        "removed": sorted(str(p) for p in before - after),
    }


class GetPermissionsMatrix:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext) -> PermissionsMatrixDTO:
        ensure_permission(actor, Permission.PERMISSIONS_MANAGE)
        return build_matrix(self._uow)


class UpdateRolePermissions:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, role: Role, permissions: list[str]
    ) -> PermissionsMatrixDTO:
        ensure_permission(actor, Permission.PERMISSIONS_MANAGE)
        parsed = validate_role_update(role, permissions)
        existing = self._uow.role_permissions.get_by_role(role)
        before = effective_permissions(role, existing.permissions if existing else None)
        with self._uow:
            upsert_override(self._uow, actor.tenant_id, role, parsed, self._clock.now())
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "permissions.updated", "RolePermissionOverride",
                    str(role), **diff_for_audit(role, before, parsed),
                )
            )
            self._uow.commit()
        return build_matrix(self._uow)


class ResetRolePermissions:
    """Drop the override so the role returns to the code defaults."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, role: Role) -> PermissionsMatrixDTO:
        ensure_permission(actor, Permission.PERMISSIONS_MANAGE)
        if role == Role.ADMIN:
            raise ValidationError("the admin role is not customizable")
        with self._uow:
            self._uow.role_permissions.delete_by_role(role)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "permissions.reset", "RolePermissionOverride",
                    str(role), role=str(role),
                )
            )
            self._uow.commit()
        return build_matrix(self._uow)
