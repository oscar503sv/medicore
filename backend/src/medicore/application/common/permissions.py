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
  * doctor       → all clinical work for their patients + their own availability and fees
                   (doctors set their own prices by default: the "associated doctors" setup;
                   a clinic of employed doctors takes ``fees.manage_own`` away).
  * admin        → user & organization management; full access except sign/amend.
                   Only admins act on other admins and hand out permissions.

Ownership checks (e.g. doctors only edit their own consultations) stay next to the use
cases — they answer "may they do it to *this* object", not "may the role do it at all".
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import ValidationError
from medicore.domain.enums import AddonModule, Role
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.value_objects.permission_adjustments import PermissionAdjustments


class Permission(StrEnum):
    PATIENTS_VIEW = "patients.view"
    PATIENTS_CREATE = "patients.create"
    PATIENTS_EDIT = "patients.edit"
    PATIENTS_ARCHIVE = "patients.archive"
    APPOINTMENTS_VIEW = "appointments.view"
    APPOINTMENTS_MANAGE = "appointments.manage"
    AVAILABILITY_MANAGE = "availability.manage"
    FEES_MANAGE_OWN = "fees.manage_own"  # set one's own fees and adjust one's own charges
    FEES_MANAGE_ALL = "fees.manage_all"  # the same for every doctor
    CONSULTATIONS_START = "consultations.start"
    CONSULTATIONS_EDIT = "consultations.edit"
    RECORDS_VIEW = "records.view"
    RECORDS_UPLOAD = "records.upload"
    RECORDS_SIGN = "records.sign"
    RECORDS_AMEND = "records.amend"
    PRESCRIPTIONS_MANAGE = "prescriptions.manage"
    VACCINATIONS_VIEW = "vaccinations.view"
    VACCINATIONS_RECORD = "vaccinations.record"
    APPLICATIONS_VIEW = "applications.view"
    APPLICATIONS_ADMINISTER = "applications.administer"
    PROCEDURES_VIEW = "procedures.view"
    PROCEDURES_PERFORM = "procedures.perform"
    PROCEDURES_CATALOG = "procedures.catalog"
    DIAGNOSES_VIEW = "diagnoses.view"
    INSURERS_VIEW = "insurers.view"
    INSURERS_MANAGE = "insurers.manage"
    USERS_VIEW = "users.view"
    USERS_MANAGE = "users.manage"
    ORGANIZATION_VIEW = "organization.view"
    ORGANIZATION_MANAGE = "organization.manage"
    LOCATIONS_MANAGE = "locations.manage"
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
        Permission.FEES_MANAGE_ALL,
        Permission.CONSULTATIONS_START,
        Permission.CONSULTATIONS_EDIT,
        Permission.RECORDS_VIEW,
        Permission.RECORDS_UPLOAD,
        Permission.VACCINATIONS_VIEW,
        Permission.APPLICATIONS_VIEW,
        Permission.PROCEDURES_VIEW,
        Permission.PROCEDURES_CATALOG,
        Permission.DIAGNOSES_VIEW,
        Permission.INSURERS_VIEW,
        Permission.INSURERS_MANAGE,
        Permission.USERS_VIEW,
        Permission.USERS_MANAGE,
        Permission.ORGANIZATION_VIEW,
        Permission.ORGANIZATION_MANAGE,
        Permission.LOCATIONS_MANAGE,
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
        Permission.FEES_MANAGE_OWN,
        Permission.CONSULTATIONS_START,
        Permission.CONSULTATIONS_EDIT,
        Permission.RECORDS_VIEW,
        Permission.RECORDS_UPLOAD,
        Permission.RECORDS_SIGN,
        Permission.RECORDS_AMEND,
        Permission.PRESCRIPTIONS_MANAGE,
        Permission.VACCINATIONS_VIEW,
        Permission.VACCINATIONS_RECORD,
        Permission.APPLICATIONS_VIEW,
        Permission.APPLICATIONS_ADMINISTER,
        Permission.PROCEDURES_VIEW,
        Permission.PROCEDURES_PERFORM,
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
        Permission.VACCINATIONS_VIEW,
        Permission.VACCINATIONS_RECORD,
        Permission.APPLICATIONS_VIEW,
        Permission.APPLICATIONS_ADMINISTER,
        Permission.PROCEDURES_VIEW,
        Permission.PROCEDURES_PERFORM,
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
        Permission.VACCINATIONS_VIEW,
        Permission.APPLICATIONS_VIEW,
        Permission.PROCEDURES_VIEW,
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


# Optional modules (sold separately): a clinic that hasn't contracted one gets none of its
# permissions, whatever its roles say. Role customizations keep them stored, so contracting
# the module later restores exactly what the clinic had configured.
MODULE_PERMISSIONS: dict[AddonModule, frozenset[Permission]] = {
    AddonModule.VACCINATION: frozenset(
        {Permission.VACCINATIONS_VIEW, Permission.VACCINATIONS_RECORD}
    ),
    AddonModule.APPLICATIONS: frozenset(
        {Permission.APPLICATIONS_VIEW, Permission.APPLICATIONS_ADMINISTER}
    ),
    AddonModule.PROCEDURES: frozenset(
        {Permission.PROCEDURES_VIEW, Permission.PROCEDURES_PERFORM, Permission.PROCEDURES_CATALOG}
    ),
}


def locked_permissions(modules: Iterable[AddonModule]) -> frozenset[Permission]:
    """Permissions belonging to the modules the clinic has NOT contracted."""
    contracted = set(modules)
    return frozenset(
        p for module, perms in MODULE_PERMISSIONS.items() if module not in contracted
        for p in perms
    )


# Clinical acts only a doctor may perform, whatever a role or user customization says.
DOCTOR_ONLY = frozenset({Permission.RECORDS_SIGN, Permission.RECORDS_AMEND})

# Handing out permissions stays with administrators: delegating it would let anyone who
# holds it grant themselves (through a colleague) everything else.
ADMIN_ONLY = frozenset({Permission.PERMISSIONS_MANAGE})


def _names(perms: Iterable[Permission]) -> str:
    return ",".join(sorted(str(p) for p in perms))


def validate_for_role(role: Role, permissions: Iterable[str]) -> frozenset[Permission]:
    """Parse a permission set meant for someone of ``role`` (a role customization or one
    user's set) and apply the guardrails: known permissions only, doctors keep signing and
    amending and nobody else gets them, administration of permissions stays with admins."""
    catalog = {str(p): p for p in Permission}
    wanted = list(permissions)
    unknown = sorted(s for s in wanted if s not in catalog)
    if unknown:
        raise ValidationError(
            f"unknown permissions: {', '.join(unknown)}",
            code="roles.unknown_permissions", permissions=",".join(unknown),
        )
    parsed = frozenset(catalog[s] for s in wanted)
    if role == Role.DOCTOR:
        missing = DOCTOR_ONLY - parsed
        if missing:
            raise ValidationError(
                "a doctor must keep: " + _names(missing),
                code="roles.doctor_must_keep", permissions=_names(missing),
            )
    elif DOCTOR_ONLY & parsed:
        raise ValidationError(
            "only doctors may hold: " + _names(DOCTOR_ONLY & parsed),
            code="roles.doctor_only", permissions=_names(DOCTOR_ONLY & parsed),
        )
    if role != Role.ADMIN and ADMIN_ONLY & parsed:
        raise ValidationError(
            "only administrators may hold: " + _names(ADMIN_ONLY & parsed),
            code="roles.admin_only", permissions=_names(ADMIN_ONLY & parsed),
        )
    return parsed


def granted(
    role: Role,
    stored: Iterable[str] | None,
    modules: Iterable[AddonModule],
    adjustments: PermissionAdjustments | None = None,
) -> frozenset[Permission]:
    """What a user may actually do in a clinic: the role's effective set, with the user's
    own adjustments when given, minus the permissions of uncontracted modules."""
    perms = effective_permissions(role, stored)
    if adjustments is not None and not adjustments.is_empty:
        catalog = {str(p): p for p in Permission}
        wanted = adjustments.apply(str(p) for p in perms)
        perms = frozenset(catalog[s] for s in wanted if s in catalog)
    if role != Role.DOCTOR:
        perms -= DOCTOR_ONLY
    if role != Role.ADMIN:
        perms -= ADMIN_ONLY
    return perms - locked_permissions(modules)


def has_permission(actor: ActorContext, permission: Permission) -> bool:
    # actor.permissions carries the per-request effective set (tenant overrides applied);
    # when absent (tests, scripts), the role's code defaults decide.
    if actor.permissions is not None:
        return str(permission) in actor.permissions
    return permission in ROLE_PERMISSIONS[actor.role]


def ensure_acts_on_admins(actor: ActorContext, *roles: Role) -> None:
    """Only an administrator may act on an administrator account (edit, suspend, reset its
    password, close its sessions) or make someone an administrator. Someone else holding
    ``users.manage`` still manages the rest of the staff."""
    if Role.ADMIN in roles and actor.role != Role.ADMIN:
        raise PermissionDenied(
            "only administrators may manage administrator accounts", code="users.admin_only"
        )


def ensure_permission(actor: ActorContext, permission: Permission) -> None:
    if not has_permission(actor, permission):
        raise PermissionDenied(
            f"role {actor.role} lacks permission '{permission}'",
            code="permission.missing",
            permission=str(permission),
        )
