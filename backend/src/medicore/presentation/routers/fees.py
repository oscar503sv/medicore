"""Fees router: each doctor's price per appointment type."""

from __future__ import annotations

from fastapi import APIRouter

from medicore.application.use_cases.fees import DoctorFees, ListDoctorFees, UpdateDoctorFees
from medicore.application.use_cases.vaccine_prices import (
    ListVaccinePrices,
    SetVaccinePrice,
    VaccinePriceItem,
)
from medicore.domain.shared.identifiers import UserId
from medicore.domain.value_objects.fee import fee
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.fees import (
    DoctorFeesRequest,
    DoctorFeesResponse,
    VaccinePriceItemResponse,
    VaccinePriceRequest,
    VaccinePricesResponse,
)
from medicore.presentation.serializers import ser_money

router = APIRouter(prefix="/fees", tags=["fees"])


def _ser(d: DoctorFees) -> dict:
    return {
        "doctor_id": str(d.doctor.id),
        "doctor_name": d.doctor.name,
        "prices": {str(k): ser_money(v) for k, v in d.prices.items()},
        "editable": d.editable,
    }


def _ser_vaccine_price(i: VaccinePriceItem) -> dict:
    return {
        "vaccine_code": i.vaccine_code,
        "in_schedule": i.in_schedule,
        "price": ser_money(i.price),
        "updated_at": i.updated_at,
    }


@router.get("/vaccines", response_model=VaccinePricesResponse)
def list_vaccine_prices(actor: Actor, uow: UoW):
    with uow:
        view = ListVaccinePrices(uow).execute(actor)
    return {"editable": view.editable, "items": [_ser_vaccine_price(i) for i in view.items]}


@router.put("/vaccines/{vaccine_code}", response_model=VaccinePriceItemResponse)
def set_vaccine_price(
    vaccine_code: str, body: VaccinePriceRequest, actor: Actor, uow: UoW, clock: Clock
):
    price = fee(body.price) if body.price is not None else None
    return _ser_vaccine_price(SetVaccinePrice(uow, clock).execute(actor, vaccine_code, price))


@router.get("", response_model=list[DoctorFeesResponse])
def list_fees(actor: Actor, uow: UoW):
    with uow:
        return [_ser(d) for d in ListDoctorFees(uow).execute(actor)]


@router.put("/{doctor_id}", response_model=DoctorFeesResponse)
def update_fees(doctor_id: str, body: DoctorFeesRequest, actor: Actor, uow: UoW, clock: Clock):
    prices = {kind: fee(amount) for kind, amount in body.prices.items()}
    return _ser(UpdateDoctorFees(uow, clock).execute(actor, UserId.parse(doctor_id), prices))
