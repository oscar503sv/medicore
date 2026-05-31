"""Role-based permission checks, enforced in the application layer (not only the UI).

Mapping of the DOMAIN_MODEL permission rules:
  * receptionist → manage appointments + view basic data; NOT full clinical records.
  * nurse        → view patients/appointments, upload files, record vitals; NOT sign records.
  * doctor       → all clinical work for their patients + their own availability.
  * admin        → user & organization management; full access.
"""

from __future__ import annotations

from medicore.application.common.context import ActorContext
from medicore.domain.enums import Role
from medicore.domain.shared.errors import PermissionDenied

# Everyone clinical may *view* records except the receptionist.
CLINICAL_VIEWERS = (Role.ADMIN, Role.DOCTOR, Role.NURSE)
APPOINTMENT_MANAGERS = (Role.ADMIN, Role.DOCTOR, Role.NURSE, Role.RECEPTIONIST)


def ensure_role(actor: ActorContext, *allowed: Role) -> None:
    if actor.role not in allowed:
        raise PermissionDenied(
            f"role {actor.role} is not allowed; requires one of "
            f"{', '.join(str(r) for r in allowed)}"
        )


def ensure_can_manage_appointments(actor: ActorContext) -> None:
    ensure_role(actor, *APPOINTMENT_MANAGERS)


def ensure_can_view_records(actor: ActorContext) -> None:
    ensure_role(actor, *CLINICAL_VIEWERS)


def ensure_can_sign_records(actor: ActorContext) -> None:
    ensure_role(actor, Role.DOCTOR)


def ensure_can_edit_consultation(actor: ActorContext) -> None:
    # Doctors lead consultations; nurses may record vitals; admins for support.
    ensure_role(actor, *CLINICAL_VIEWERS)


def ensure_can_upload_documents(actor: ActorContext) -> None:
    ensure_role(actor, *CLINICAL_VIEWERS)


def ensure_can_manage_users(actor: ActorContext) -> None:
    ensure_role(actor, Role.ADMIN)


def ensure_can_manage_organization(actor: ActorContext) -> None:
    ensure_role(actor, Role.ADMIN)


def ensure_can_manage_availability(actor: ActorContext) -> None:
    ensure_role(actor, Role.DOCTOR, Role.ADMIN)
