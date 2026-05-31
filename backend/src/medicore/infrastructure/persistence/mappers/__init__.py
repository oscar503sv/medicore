"""Mapper functions: ORM model ↔ domain entity.

Each ``to_*`` function converts an ORM row to a domain entity.
Each ``from_*`` function serializes a domain entity to a dict suitable for ORM construction
or update (does NOT create the ORM model directly — repositories handle that).
"""

from medicore.infrastructure.persistence.mappers.availability import (
    from_doctor_availability,
    to_availability_exception,
    to_doctor_availability,
)
from medicore.infrastructure.persistence.mappers.entities import (
    to_appointment,
    to_audit_log,
    to_consultation,
    to_doctor_profile,
    to_medical_document,
    to_medical_record,
    to_notification,
    to_patient,
    to_prescription,
    to_tenant,
    to_user,
)

__all__ = [
    "from_doctor_availability",
    "to_appointment",
    "to_audit_log",
    "to_availability_exception",
    "to_consultation",
    "to_doctor_availability",
    "to_doctor_profile",
    "to_medical_document",
    "to_medical_record",
    "to_notification",
    "to_patient",
    "to_prescription",
    "to_tenant",
    "to_user",
]
