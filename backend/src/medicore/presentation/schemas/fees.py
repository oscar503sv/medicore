"""Fee schemas: doctors' prices per appointment type and adjusting what a visit is charged.

Amounts go out as strings with two decimals ("25.00") and come in as numbers or numeric
strings; the domain checks the range and the cents.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from medicore.domain.enums import AppointmentType

FeeAmount = Decimal


class DoctorFeesResponse(BaseModel):
    doctor_id: str
    doctor_name: str
    prices: dict[str, str]  # appointment type → "25.00"; a type without a price is absent
    editable: bool


class DoctorFeesRequest(BaseModel):
    prices: dict[AppointmentType, FeeAmount]


class ChargeRequest(BaseModel):
    amount: FeeAmount
    note: str | None = Field(None, max_length=200)


class ProcedureChargeRequest(BaseModel):
    included: bool = False  # included in the consultation fee
    amount: FeeAmount | None = None  # required unless included
    note: str | None = Field(None, max_length=200)
