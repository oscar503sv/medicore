"""Granular permission catalog, enforced in the application layer (not only the UI).

Permissions are code-defined (``resource.action``) and mapped to the existing roles in
``ROLE_PERMISSIONS`` — those are the DEFAULTS. Each tenant may customize a role's set via
a ``RolePermissionOverride`` row; ``effective_permissions`` resolves defaults vs override
and the presentation layer puts the result on ``ActorContext.permissions``, so every
``ensure_permission`` check honors the clinic's customization.

Summary of the DOMAIN_MODEL rules the defaults encode:
  * receptionist → manage appointments + register/edit patients; NOT clinical records.
  * nurse        → view patients/agenda, edit open consultations (vitals), view/upload
                   records; NOT book appointments, NOT edit patients, NOT start/sign.
  * doctor       → all clinical work for their patients + their own availability.
  * admin        → user & organization management; full access except sign/amend.

Ownership checks (e.g. doctors only edit their own consultations) stay next to the use
cases — they answer "may they do it to *this* object", not "may the role do it at all".
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from medicore.application.common.context import ActorContext
from medicore.domain.enums import Role
from medicore.domain.shared.errors import PermissionDenied


class Permission(StrEnum):
    PATIENTS_VIEW = "patients.view"
    PATIENTS_CREATE = "patients.create"
    PATIENTS_EDIT = "patients.edit"
    PATIENTS_ARCHIVE = "patients.archive"
    APPOINTMENTS_VIEW = "appointments.view"
    APPOINTMENTS_MANAGE = "appointments.manage"
    AVAILABILITY_MANAGE = "availability.manage"
    CONSULTATIONS_START = "consultations.start"
    CONSULTATIONS_EDIT = "consultations.edit"
    RECORDS_VIEW = "records.view"
    RECORDS_UPLOAD = "records.upload"
    RECORDS_SIGN = "records.sign"
    RECORDS_AMEND = "records.amend"
    PRESCRIPTIONS_MANAGE = "prescriptions.manage"
    DIAGNOSES_VIEW = "diagnoses.view"
    INSURERS_VIEW = "insurers.view"
    INSURERS_MANAGE = "insurers.manage"
    USERS_VIEW = "users.view"
    USERS_MANAGE = "users.manage"
    ORGANIZATION_VIEW = "organization.view"
    ORGANIZATION_MANAGE = "organization.manage"
    AUDIT_VIEW = "audit.view"
    PERMISSIONS_MANAGE = "permissions.manage"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset({
        Permission.PATIENTS_VIEW,
        Permission.PATIENTS_CREATE,
        Permission.PATIENTS_EDIT,
        Permission.PATIENTS_ARCHIVE,
        Permission.APPOINTMENTS_VIEW,
        Permission.APPOINTMENTS_MANAGE,
        Permission.AVAILABILITY_MANAGE,
        Permission.CONSULTATIONS_START,
        Permission.CONSULTATIONS_EDIT,
        Permission.RECORDS_VIEW,
        Permission.RECORDS_UPLOAD,
        Permission.DIAGNOSES_VIEW,
        Permission.INSURERS_VIEW,
        Permission.INSURERS_MANAGE,
        Permission.USERS_VIEW,
        Permission.USERS_MANAGE,
        Permission.ORGANIZATION_VIEW,
        Permission.ORGANIZATION_MANAGE,
        Permission.AUDIT_VIEW,
        Permission.PERMISSIONS_MANAGE,
    }),
    Role.DOCTOR: frozenset({
        Permission.PATIENTS_VIEW,
        Permission.PATIENTS_CREATE,
        Permission.PATIENTS_EDIT,
        Permission.PATIENTS_ARCHIVE,
        Permission.APPOINTMENTS_VIEW,
        Permission.APPOINTMENTS_MANAGE,
        Permission.AVAILABILITY_MANAGE,
        Permission.CONSULTATIONS_START,
        Permission.CONSULTATIONS_EDIT,
        Permission.RECORDS_VIEW,
        Permission.RECORDS_UPLOAD,
        Permission.RECORDS_SIGN,
        Permission.RECORDS_AMEND,
        Permission.PRESCRIPTIONS_MANAGE,
        Permission.DIAGNOSES_VIEW,
        Permission.INSURERS_VIEW,
    }),
    Role.NURSE: frozenset({
        Permission.PATIENTS_VIEW,
        Permission.PATIENTS_CREATE,
        Permission.APPOINTMENTS_VIEW,
        Permission.CONSULTATIONS_EDIT,
        Permission.RECORDS_VIEW,
        Permission.RECORDS_UPLOAD,
        Permission.DIAGNOSES_VIEW,
        Permission.INSURERS_VIEW,
    }),
    Role.RECEPTIONIST: frozenset({
        Permission.PATIENTS_VIEW,
        Permission.PATIENTS_CREATE,
        Permission.PATIENTS_EDIT,
        Permission.PATIENTS_ARCHIVE,
        Permission.APPOINTMENTS_VIEW,
        Permission.APPOINTMENTS_MANAGE,
        Permission.DIAGNOSES_VIEW,
        Permission.INSURERS_VIEW,
    }),
}


def permissions_for(role: Role) -> frozenset[Permission]:
    """The CODE-DEFAULT permission set for a role (no tenant customization applied)."""
    return ROLE_PERMISSIONS[role]


def effective_permissions(role: Role, stored: Iterable[str] | None) -> frozenset[Permission]:
    """Resolve a role's effective set: the tenant's stored override, or the defaults.

    ``stored`` is the override row's string list (None when the role is not customized).
    Stored strings are intersected with the current catalog so a permission removed from
    the code never breaks reads; validation against the catalog happens only on write.
    """
    if stored is None:
        return ROLE_PERMISSIONS[role]
    catalog = {str(p): p for p in Permission}
    return frozenset(catalog[s] for s in stored if s in catalog)


def has_permission(actor: ActorContext, permission: Permission) -> bool:
    # actor.permissions carries the per-request effective set (tenant overrides applied);
    # when absent (tests, scripts), the role's code defaults decide.
    if actor.permissions is not None:
        return str(permission) in actor.permissions
    return permission in ROLE_PERMISSIONS[actor.role]


def ensure_permission(actor: ActorContext, permission: Permission) -> None:
    if not has_permission(actor, permission):
        raise PermissionDenied(f"role {actor.role} lacks permission '{permission}'")
