"""Per-user permissions: one person's exceptions to their role (plans with the
``user_permissions`` feature, Clínica and up).

The clinic edits the user's full permission set; it is stored as the difference from the
role (grants and revocations), so later changes to the role still reach the user except
where an exception was made. Same guardrails as role customization: admins aren't
customizable and signing/amending records stays with doctors. Nobody edits their own.
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.entitlements import granted_permissions, has_feature
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import (
    DOCTOR_ONLY,
    Permission,
    effective_permissions,
    ensure_permission,
    locked_permissions,
)
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.tenant import Tenant
from medicore.domain.entities.user import User
from medicore.domain.enums import PlanFeature, Role
from medicore.domain.shared.identifiers import UserId
from medicore.domain.value_objects.permission_adjustments import PermissionAdjustments


@dataclass(frozen=True, slots=True)
class UserPermissionsDTO:
    user: User
    available: bool  # the plan includes per-user permissions
    catalog: tuple[str, ...]
    role_permissions: tuple[str, ...]  # what the role gives (with the clinic's customization)
    granted: tuple[str, ...]  # the user's extra permissions
    revoked: tuple[str, ...]  # role permissions taken from the user
    effective: tuple[str, ...]  # what the user can actually do now
    locked: tuple[str, ...]  # permissions of uncontracted modules


def _sorted(items) -> tuple[str, ...]:
    return tuple(sorted(str(p) for p in items))


def _role_set(uow: UnitOfWork, role: Role) -> frozenset[Permission]:
    override = uow.role_permissions.get_by_role(role)
    return effective_permissions(role, override.permissions if override else None)


def _load(uow: UnitOfWork, actor: ActorContext, user_id: UserId) -> tuple[Tenant, User]:
    tenant = uow.tenants.get_by_id(actor.tenant_id)
    if tenant is None:
        raise EntityNotFound("Tenant", actor.tenant_id)
    user = uow.users.get_by_id(user_id)
    if user is None:
        raise EntityNotFound("User", user_id)
    return tenant, user


def _dto(uow: UnitOfWork, tenant: Tenant, user: User) -> UserPermissionsDTO:
    adj = user.permission_adjustments
    return UserPermissionsDTO(
        user=user,
        available=has_feature(uow, tenant, PlanFeature.USER_PERMISSIONS),
        catalog=_sorted(Permission),
        role_permissions=_sorted(_role_set(uow, user.role)),
        granted=tuple(sorted(adj.granted)),
        revoked=tuple(sorted(adj.revoked)),
        effective=_sorted(granted_permissions(uow, tenant, user)),
        locked=_sorted(locked_permissions(tenant.subscription.modules)),
    )


class GetUserPermissions:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext, user_id: UserId) -> UserPermissionsDTO:
        ensure_permission(actor, Permission.PERMISSIONS_MANAGE)
        with self._uow:
            tenant, user = _load(self._uow, actor, user_id)
            return _dto(self._uow, tenant, user)


def _parse(user: User, permissions: list[str]) -> frozenset[Permission]:
    catalog = {str(p): p for p in Permission}
    unknown = sorted(s for s in permissions if s not in catalog)
    if unknown:
        raise ValidationError(
            f"unknown permissions: {', '.join(unknown)}",
            code="roles.unknown_permissions", permissions=",".join(unknown),
        )
    wanted = frozenset(catalog[s] for s in permissions)
    if user.role == Role.DOCTOR:
        missing = DOCTOR_ONLY - wanted
        if missing:
            raise ValidationError(
                "a doctor must keep: " + ", ".join(_sorted(missing)),
                code="roles.doctor_must_keep", permissions=",".join(_sorted(missing)),
            )
    elif DOCTOR_ONLY & wanted:
        forbidden = _sorted(DOCTOR_ONLY & wanted)
        raise ValidationError(
            "only doctors may hold: " + ", ".join(forbidden),
            code="roles.doctor_only", permissions=",".join(forbidden),
        )
    return wanted


class UpdateUserPermissions:
    """Set a user's permissions. ``permissions`` is the full set wanted; sending exactly
    the role's set (or calling with ``reset``) removes every exception."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, user_id: UserId, permissions: list[str]
    ) -> UserPermissionsDTO:
        ensure_permission(actor, Permission.PERMISSIONS_MANAGE)
        with self._uow:
            tenant, user = _load(self._uow, actor, user_id)
            if not has_feature(self._uow, tenant, PlanFeature.USER_PERMISSIONS):
                raise ValidationError(
                    "the clinic's plan doesn't include per-user permissions",
                    code="plan.feature_required", feature=str(PlanFeature.USER_PERMISSIONS),
                )
            if user.id == actor.user_id:
                raise ValidationError(
                    "you can't change your own permissions", code="user_permissions.self"
                )
            if user.role == Role.ADMIN:
                raise ValidationError(
                    "administrators always have full access", code="user_permissions.admin"
                )
            wanted = _parse(user, permissions)
            before = granted_permissions(self._uow, tenant, user)
            role_set = _role_set(self._uow, user.role)
            user.adjust_permissions(
                PermissionAdjustments.between(
                    (str(p) for p in role_set), (str(p) for p in wanted)
                )
            )
            self._uow.users.save(user)
            after = granted_permissions(self._uow, tenant, user)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "user.permissions_updated", "User", str(user.id),
                    subject=subject(user.name),
                    added=list(_sorted(after - before)),
                    removed=list(_sorted(before - after)),
                    customized=not user.permission_adjustments.is_empty,
                )
            )
            self._uow.commit()
            return _dto(self._uow, tenant, user)
