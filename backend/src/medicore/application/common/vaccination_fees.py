"""The charge of a vaccination appointment: only what its standing private doses add up to."""

from __future__ import annotations

from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentType
from medicore.domain.services.vaccine_fees import doses_total


def price_vaccination_visit(uow: UnitOfWork, appointment: Appointment) -> None:
    """Set the charge of a vaccination appointment from its doses (no doses: $0). Other
    appointment types are left alone. The caller holds the appointment's lock and saves it."""
    if appointment.type == AppointmentType.VACCINATION:
        appointment.price_from_doses(
            doses_total(uow.vaccinations.list_by_appointment(appointment.id))
        )
