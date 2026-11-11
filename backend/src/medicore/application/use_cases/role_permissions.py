"""Role-permission customization use cases (tenant admin).

A tenant may customize which permissions each role holds, within guardrails:

* ADMIN is never customizable — it always keeps the code defaults, so the clinic can
  never lock itself out of permission management.
* ``records.sign`` and ``records.amend`` belong exclusively to DOCTOR: they cannot be
  granted to other roles nor removed from the doctor (a clinic where nobody can sign
  is broken).
* Writes must be a subset of the current catalog; reads tolerate stale strings.

The defaults themselves depend on the clinic's practice model (associated or employed
doctors): changing it moves the defaults of every role, and customized roles get the same
shift applied to their stored set, so their other customizations survive.
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import (
    Permission,
    effective_permissions,
    ensure_permission,
    locked_permissions,
    role_defaults,
    validate_for_role,
)
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.role_permission_override import RolePermissionOverride
from medicore.domain.enums import PracticeModel, Role
from medicore.domain.shared.identifiers import RolePermissionOverrideId, TenantId


@dataclass(frozen=True, slots=True)
class RolePermissionsDTO:
    defaults: tuple[str, ...]
    effective: tuple[str, ...]
    customized: bool


@dataclass(frozen=True, slots=True)
class PermissionsMatrixDTO:
    catalog: tuple[str, ...]
    roles: dict[Role, RolePermissionsDTO]
    # Permissions of optional modules the clinic hasn't contracted: they can be configured,
    # but no role gets them until the module is added to the subscription.
    locked: tuple[str, ...] = ()
    practice_model: PracticeModel = PracticeModel.ASSOCIATED


def build_matrix(uow: UnitOfWork, tenant_id: TenantId) -> PermissionsMatrixDTO:
    """Assemble catalog + per-role defaults/effective/customized for one tenant."""
    tenant = uow.tenants.get_by_id(tenant_id)
    if tenant is None:
        raise EntityNotFound("Tenant", tenant_id)
    overrides = {o.role: o for o in uow.role_permissions.list()}
    model = tenant.practice_model
    roles: dict[Role, RolePermissionsDTO] = {}
    for role in Role:
        override = overrides.get(role)
        stored = override.permissions if override else None
        roles[role] = RolePermissionsDTO(
            defaults=tuple(sorted(str(p) for p in role_defaults(role, model))),
            effective=tuple(
                sorted(str(p) for p in effective_permissions(role, stored, model))
            ),
            customized=override is not None,
        )
    return PermissionsMatrixDTO(
        catalog=tuple(sorted(str(p) for p in Permission)),
        roles=roles,
        locked=tuple(sorted(str(p) for p in locked_permissions(tenant.subscription.modules))),
        practice_model=model,
    )


def _tenant(uow: UnitOfWork, tenant_id: TenantId):
    tenant = uow.tenants.get_by_id(tenant_id)
    if tenant is None:
        raise EntityNotFound("Tenant", tenant_id)
    return tenant


def validate_role_update(role: Role, permissions: list[str]) -> frozenset[Permission]:
    """Apply the customization guardrails; return the parsed permission set."""
    if role == Role.ADMIN:
        raise ValidationError(
            "the admin role is not customizable", code="roles.admin_not_customizable"
        )
    return validate_for_role(role, permissions)


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
        return build_matrix(self._uow, actor.tenant_id)


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
        model = _tenant(self._uow, actor.tenant_id).practice_model
        before = effective_permissions(role, existing.permissions if existing else None, model)
        with self._uow:
            upsert_override(self._uow, actor.tenant_id, role, parsed, self._clock.now())
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "permissions.updated", "RolePermissionOverride",
                    str(role), **diff_for_audit(role, before, parsed),
                )
            )
            self._uow.commit()
        return build_matrix(self._uow, actor.tenant_id)


class ResetRolePermissions:
    """Drop the override so the role returns to the code defaults."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, role: Role) -> PermissionsMatrixDTO:
        ensure_permission(actor, Permission.PERMISSIONS_MANAGE)
        if role == Role.ADMIN:
            raise ValidationError(
                "the admin role is not customizable", code="roles.admin_not_customizable"
            )
        with self._uow:
            self._uow.role_permissions.delete_by_role(role)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "permissions.reset", "RolePermissionOverride",
                    str(role), role=str(role),
                )
            )
            self._uow.commit()
        return build_matrix(self._uow, actor.tenant_id)


class SetPracticeModel:
    """Say how the clinic's doctors work (associated or employed). The defaults of every
    role follow the model; a customized role gets the same shift applied to its stored set
    (e.g. employed doctors lose ``fees.manage_own`` and ``analytics.money``), keeping the
    rest of its customization. Per-user exceptions are left as they are."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, model: PracticeModel) -> PermissionsMatrixDTO:
        ensure_permission(actor, Permission.PERMISSIONS_MANAGE)
        with self._uow:
            tenant = _tenant(self._uow, actor.tenant_id)
            previous = tenant.practice_model
            if model == previous:
                return build_matrix(self._uow, actor.tenant_id)
            now = self._clock.now()
            shifted = []
            for override in self._uow.role_permissions.list():
                role = override.role
                old, new = role_defaults(role, previous), role_defaults(role, model)
                if role == Role.ADMIN or old == new:
                    continue
                current = effective_permissions(role, override.permissions, previous)
                updated = validate_for_role(
                    role, [str(p) for p in (current | (new - old)) - (old - new)]
                )
                upsert_override(self._uow, actor.tenant_id, role, updated, now)
                shifted.append(diff_for_audit(role, current, updated))
            tenant.practice_model = model
            self._uow.tenants.save(tenant)
            self._uow.audit.append(
                audit_entry(
                    actor, now, "organization.practice_model_changed", "Tenant",
                    str(tenant.id), before=str(previous), after=str(model),
                    customized_roles=shifted,
                )
            )
            self._uow.commit()
            return build_matrix(self._uow, actor.tenant_id)
