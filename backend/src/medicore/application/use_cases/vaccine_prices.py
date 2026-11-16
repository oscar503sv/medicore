"""Vaccine prices: what the clinic charges for each privately supplied vaccine.

Everyone who books or records vaccinations (or sets fees) sees the list; only
``fees.manage_all`` changes it. Vaccines supplied by the health ministry have no price: they
are free of charge, also in a private clinic. The list belongs to the vaccination module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.application.common.entitlements import ensure_module
from medicore.application.common.errors import ValidationError
from medicore.application.common.permissions import (
    Permission,
    ensure_permission,
    has_permission,
)
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.vaccine_price import VaccinePrice
from medicore.domain.enums import AddonModule
from medicore.domain.services.immunization import VACCINES
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.value_objects.money import Money

_SEE_PRICES = (
    Permission.APPOINTMENTS_VIEW,
    Permission.FEES_MANAGE_OWN,
    Permission.FEES_MANAGE_ALL,
    Permission.VACCINATIONS_VIEW,
)
_MODULE_CODE = "vaccine_price.module_required"


@dataclass(frozen=True, slots=True)
class VaccinePriceItem:
    vaccine_code: str
    in_schedule: bool
    price: Money | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class VaccinePriceView:
    editable: bool
    items: list[VaccinePriceItem]


def _view(actor: ActorContext, prices: dict[str, VaccinePrice]) -> VaccinePriceView:
    return VaccinePriceView(
        editable=has_permission(actor, Permission.FEES_MANAGE_ALL),
        items=[
            VaccinePriceItem(
                vaccine_code=v.code,
                in_schedule=v.in_schedule,
                price=prices[v.code].price if v.code in prices else None,
                updated_at=prices[v.code].updated_at if v.code in prices else None,
            )
            for v in VACCINES.values()
        ],
    )


class ListVaccinePrices:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext) -> VaccinePriceView:
        if not any(has_permission(actor, p) for p in _SEE_PRICES):
            ensure_permission(actor, Permission.APPOINTMENTS_VIEW)  # raises
        ensure_module(self._uow, actor, AddonModule.VACCINATION, _MODULE_CODE)
        return _view(actor, {p.vaccine_code: p for p in self._uow.vaccine_prices.list()})


class SetVaccinePrice:
    """Set (or, with ``None``, remove) a vaccine's price. A $0 price is valid: the clinic
    gives that vaccine away. No row lock is needed: the write is a single upsert."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, vaccine_code: str, price: Money | None
    ) -> VaccinePriceItem:
        if not has_permission(actor, Permission.FEES_MANAGE_ALL):
            raise PermissionDenied("you may not set vaccine prices", code="fee.not_allowed")
        ensure_module(self._uow, actor, AddonModule.VACCINATION, _MODULE_CODE)
        if vaccine_code not in VACCINES:
            raise ValidationError(f"unknown vaccine {vaccine_code!r}",
                                  code="vaccine_price.unknown_vaccine")
        now = self._clock.now()
        with self._uow:
            old = self._uow.vaccine_prices.get_for_update(vaccine_code)
            old_price = old.price if old else None
            if old_price == price:
                return VaccinePriceItem(
                    vaccine_code, VACCINES[vaccine_code].in_schedule, price,
                    old.updated_at if old else None,
                )
            if price is None:
                self._uow.vaccine_prices.delete(vaccine_code)
            else:
                self._uow.vaccine_prices.save(
                    VaccinePrice(actor.tenant_id, vaccine_code, price, now)
                )
            self._uow.audit.append(audit_entry(
                actor, now, "vaccine_price.updated", "VaccinePrice", vaccine_code,
                vaccine=vaccine_code,
                old=f"{old_price.amount:.2f}" if old_price else None,
                new=f"{price.amount:.2f}" if price else None,
            ))
            self._uow.commit()
        return VaccinePriceItem(
            vaccine_code, VACCINES[vaccine_code].in_schedule, price, now if price else None
        )
