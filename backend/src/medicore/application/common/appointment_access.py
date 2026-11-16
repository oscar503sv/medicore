"""Who may act on an appointment: doctors only on their own."""

from __future__ import annotations

from medicore.application.common.context import ActorContext
from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import Role
from medicore.domain.shared.errors import PermissionDenied


def ensure_own_appointment(actor: ActorContext, appointment: Appointment) -> None:
    """A doctor manages only the appointments they attend: not another doctor's, and not a
    service agenda's (no doctor). The other roles are not narrowed here."""
    if actor.role == Role.DOCTOR and appointment.doctor_id != actor.user_id:
        raise PermissionDenied(
            "doctors may only manage their own appointments", code="appointment.not_own"
        )
