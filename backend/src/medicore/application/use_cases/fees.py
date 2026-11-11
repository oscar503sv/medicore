"""Fees: each doctor's price per appointment type, and adjusting what one visit is charged.

Prices are copied onto each appointment when it is booked (and onto each procedure when it
is ordered), so changing a price never rewrites what past visits were charged. Anyone who
books appointments sees the prices (patients ask); who may change them is in
``application.common.fees``.
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.fees import can_price, ensure_can_price
from medicore.application.common.permissions import (
    Permission,
    ensure_permission,
    has_permission,
)
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.fee_schedule import FeeSchedule
from medicore.domain.entities.procedure import Procedure
from medicore.domain.entities.user import User
from medicore.domain.enums import AppointmentType, Role, UserStatus
from medicore.domain.repositories._support import UserFilter
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import (
    AppointmentId,
    FeeScheduleId,
    ProcedureId,
    UserId,
)
from medicore.domain.value_objects.money import Money

_SEE_FEES = (Permission.APPOINTMENTS_VIEW, Permission.FEES_MANAGE_OWN, Permission.FEES_MANAGE_ALL)


@dataclass(frozen=True, slots=True)
class DoctorFees:
    doctor: User
    prices: dict[AppointmentType, Money]
    editable: bool  # the actor may change them


def _active_doctors(uow: UnitOfWork) -> list[User]:
    return uow.users.list(UserFilter(role="doctor", status="active")).items


def list_price(uow: UnitOfWork, doctor_id: UserId, kind: AppointmentType) -> Money | None:
    """The doctor's current price for an appointment type (None when there is none)."""
    schedule = uow.fees.get_by_doctor(doctor_id)
    return schedule.price_for(kind) if schedule else None


class ListDoctorFees:
    """The active doctors' prices. Everyone who views the agenda sees them; ``editable``
    says which ones the actor may change."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext) -> list[DoctorFees]:
        if not any(has_permission(actor, p) for p in _SEE_FEES):
            ensure_permission(actor, Permission.APPOINTMENTS_VIEW)  # raises
        doctors = _active_doctors(self._uow)
        schedules = self._uow.fees.list_for_doctors([d.id for d in doctors])
        return [
            DoctorFees(
                doctor=d,
                prices=dict(schedules[d.id].prices) if d.id in schedules else {},
                editable=can_price(actor, d.id),
            )
            for d in doctors
        ]


class UpdateDoctorFees:
    """Replace a doctor's prices (a type left out has no price)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, doctor_id: UserId, prices: dict[AppointmentType, Money]
    ) -> DoctorFees:
        ensure_can_price(actor, doctor_id)
        doctor = self._uow.users.get_by_id(doctor_id)
        if doctor is None or doctor.role != Role.DOCTOR or doctor.status != UserStatus.ACTIVE:
            raise EntityNotFound("Doctor", doctor_id)
        now = self._clock.now()
        with self._uow:
            schedule = self._uow.fees.get_by_doctor(doctor_id) or FeeSchedule(
                id=FeeScheduleId.new(), tenant_id=actor.tenant_id, doctor_id=doctor_id,
            )
            schedule.set_prices(prices, now)
            self._uow.fees.save(schedule)
            self._uow.audit.append(audit_entry(
                actor, now, "fees.updated", "FeeSchedule", str(schedule.id),
                subject=subject(doctor.name),
                prices={str(k): f"{v.amount:.2f}" for k, v in schedule.prices.items()},
            ))
            self._uow.commit()
        return DoctorFees(doctor=doctor, prices=dict(schedule.prices), editable=True)


class AdjustAppointmentFee:
    """Charge an appointment a different amount than its listed price."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, appointment_id: AppointmentId,
                charged: Money, note: str | None) -> Appointment:
        ensure_permission(actor, Permission.APPOINTMENTS_VIEW)
        appointment = self._uow.appointments.get_by_id(appointment_id)
        if appointment is None:
            raise EntityNotFound("Appointment", appointment_id)
        ensure_can_price(actor, appointment.doctor_id)
        with self._uow:
            appointment.adjust_fee(charged, note)
            self._uow.appointments.save(appointment)
            patient = self._uow.patients.get_by_id(appointment.patient_id)
            self._uow.audit.append(audit_entry(
                actor, self._clock.now(), "appointment.fee_adjusted", "Appointment",
                str(appointment.id),
                subject=subject(appointment.code, patient.full_name if patient else None),
                fee=f"{charged.amount:.2f}", note=appointment.charge.note,
            ))
            self._uow.commit()
        return appointment


class SetProcedureFee:
    """Change what a procedure is charged, or include it in its consultation's fee."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, procedure_id: ProcedureId, *, included: bool,
                charged: Money | None, note: str | None) -> Procedure:
        ensure_permission(actor, Permission.PROCEDURES_VIEW)
        procedure = self._uow.procedures.get(procedure_id)
        if procedure is None:
            raise EntityNotFound("Procedure", procedure_id)
        if not can_price(actor, procedure.ordered_by_id):
            raise PermissionDenied("you may not set this procedure's fee",
                                   code="fee.not_allowed")
        with self._uow:
            procedure.set_fee(included=included, charged=charged, note=note)
            self._uow.procedures.save(procedure)
            patient = self._uow.patients.get_by_id(procedure.patient_id)
            self._uow.audit.append(audit_entry(
                actor, self._clock.now(), "procedure.fee_adjusted", "Procedure",
                str(procedure.id),
                subject=subject(patient.code, patient.full_name) if patient else None,
                procedure=procedure.type_name, included=included,
                fee=f"{procedure.charge.charged.amount:.2f}" if procedure.charge.charged else None,
            ))
            self._uow.commit()
        return procedure
