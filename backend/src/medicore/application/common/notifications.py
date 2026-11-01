"""In-app notification emission, used by use cases inside their own transaction.

A notification is written through the same unit of work as the action that caused it, so it
is committed (or rolled back) together with that action — no event bus, no outbox.

Rules shared by every emitter:
- the actor never notifies themselves;
- payloads carry ids (for linking) and display labels frozen at emission time — patient
  names, codes, dates — but never clinical content (diagnoses, results, file names).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from medicore.application.common.context import ActorContext
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.notification import Notification
from medicore.domain.entities.patient import Patient
from medicore.domain.enums import AppointmentStatus, Role, UserStatus
from medicore.domain.repositories._support import Paging, UserFilter
from medicore.domain.shared.identifiers import NotificationId, UserId

# Notification types — the client keys its i18n templates on these.
APPOINTMENT_CREATED = "appointment.created"
APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
APPOINTMENT_CANCELLED = "appointment.cancelled"
APPOINTMENT_NO_SHOW = "appointment.no_show"
RECORD_AMENDED = "record.amended"
DOCUMENT_UPLOADED = "document.uploaded"
USER_CREATED = "user.created"
USER_ROLE_CHANGED = "user.role_changed"
APPLICATION_REACTION = "application.reaction"


def notify(
    uow: UnitOfWork,
    actor: ActorContext,
    when: datetime,
    type: str,
    recipients: Iterable[UserId | None],
    **data: str | None,
) -> None:
    """Queue one notification per distinct recipient (minus the actor) on ``uow``.

    Must be called inside the caller's ``with uow`` block, before ``commit()``.
    """
    targets = {r for r in recipients if r is not None and r != actor.user_id}
    if not targets:
        return
    actor_user = uow.users.get_by_id(actor.user_id)
    payload = {k: v for k, v in data.items() if v is not None}
    if actor_user is not None:
        payload["actor_name"] = actor_user.name
    for user_id in sorted(targets, key=lambda u: str(u)):
        uow.notifications.save(
            Notification(
                id=NotificationId.new(),
                tenant_id=actor.tenant_id,
                user_id=user_id,
                type=type,
                data=dict(payload),
                created_at=when,
            )
        )


def active_admins(uow: UnitOfWork, exclude: UserId | None = None) -> list[UserId]:
    """Every active clinic admin — the audience for user-management notifications.

    ``exclude`` drops the user the notification is about (a new admin, or someone just
    promoted to admin, is not told about themselves).
    """
    page = uow.users.list(
        UserFilter(role=str(Role.ADMIN), status=str(UserStatus.ACTIVE)), Paging(limit=1000)
    )
    return [u.id for u in page.items if u.id != exclude]


def treating_doctor(uow: UnitOfWork, patient: Patient) -> UserId | None:
    """The patient's assigned doctor or, failing that, the doctor of their most recent
    completed appointment. None when the patient has neither."""
    if patient.primary_doctor_id is not None:
        return patient.primary_doctor_id
    completed = [
        a
        for a in uow.appointments.list_by_patient(patient.id)
        if a.status == AppointmentStatus.COMPLETED
    ]
    if not completed:
        return None
    return max(completed, key=lambda a: a.scheduled_start).doctor_id


def appointment_payload(uow: UnitOfWork, appointment: Appointment) -> dict[str, str | None]:
    patient = uow.patients.get_by_id(appointment.patient_id)
    return {
        "appointment_id": str(appointment.id),
        "appointment_code": appointment.code,
        "patient_id": str(appointment.patient_id),
        "patient_name": patient.full_name if patient else None,
        # Naive clinic wall-clock, like every appointment time the API returns.
        "scheduled_start": appointment.scheduled_start.isoformat(),
    }
