"""Fees router: each doctor's price per appointment type."""

from __future__ import annotations

from fastapi import APIRouter

from medicore.application.use_cases.fees import DoctorFees, ListDoctorFees, UpdateDoctorFees
from medicore.domain.shared.identifiers import UserId
from medicore.domain.value_objects.fee import fee
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.fees import DoctorFeesRequest, DoctorFeesResponse
from medicore.presentation.serializers import ser_money

router = APIRouter(prefix="/fees", tags=["fees"])


def _ser(d: DoctorFees) -> dict:
    return {
        "doctor_id": str(d.doctor.id),
        "doctor_name": d.doctor.name,
        "prices": {str(k): ser_money(v) for k, v in d.prices.items()},
        "editable": d.editable,
    }


@router.get("", response_model=list[DoctorFeesResponse])
def list_fees(actor: Actor, uow: UoW):
    with uow:
        return [_ser(d) for d in ListDoctorFees(uow).execute(actor)]


@router.put("/{doctor_id}", response_model=DoctorFeesResponse)
def update_fees(doctor_id: str, body: DoctorFeesRequest, actor: Actor, uow: UoW, clock: Clock):
    prices = {kind: fee(amount) for kind, amount in body.prices.items()}
    return _ser(UpdateDoctorFees(uow, clock).execute(actor, UserId.parse(doctor_id), prices))
