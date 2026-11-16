"""Vaccine prices and the charge of a vaccination visit over HTTP."""

from __future__ import annotations

import pytest

from tests.presentation.test_service_agendas_api import _walk_in, agenda  # noqa: F401

API = "/api/v1"


def _visit(seed, appointment_id, doses):
    return {"appointment_id": appointment_id, "patient_id": str(seed.patient.id), "doses": doses}


def _dose(vaccine, supply, lot="L-1"):
    return {"vaccine_code": vaccine, "lot": lot, "supply": supply}


@pytest.fixture
def priced(client, admin_headers):
    for code, price in (("TD", 25), ("INFLU", "20.00")):
        resp = client.put(f"{API}/fees/vaccines/{code}", json={"price": price},
                          headers=admin_headers)
        assert resp.status_code == 200, resp.text


class TestPriceList:
    def test_lists_the_catalog_with_prices(self, client, admin_headers, nurse_headers, priced):
        for headers, editable in ((admin_headers, True), (nurse_headers, False)):
            body = client.get(f"{API}/fees/vaccines", headers=headers).json()

            assert body["editable"] is editable
            td = next(i for i in body["items"] if i["vaccine_code"] == "TD")
            assert td["price"] == "25.00" and td["updated_at"]
            assert next(i for i in body["items"] if i["vaccine_code"] == "BCG")["price"] is None

    def test_setting_null_removes_the_price(self, client, admin_headers, priced):
        resp = client.put(f"{API}/fees/vaccines/TD", json={"price": None}, headers=admin_headers)

        assert resp.status_code == 200 and resp.json()["price"] is None

    def test_only_who_manages_every_fee_sets_prices(self, client, nurse_headers, auth_headers):
        for headers in (nurse_headers, auth_headers):  # a nurse and a doctor
            resp = client.put(f"{API}/fees/vaccines/TD", json={"price": 5}, headers=headers)

            assert resp.status_code == 403
            assert resp.json()["code"] == "fee.not_allowed"

    def test_unknown_vaccine_is_400_and_a_bad_amount_422(self, client, admin_headers):
        unknown = client.put(f"{API}/fees/vaccines/NOPE", json={"price": 5},
                             headers=admin_headers)
        bad = client.put(f"{API}/fees/vaccines/TD", json={"price": "1.234"},
                         headers=admin_headers)

        assert (unknown.status_code, unknown.json()["code"]) == (
            400, "vaccine_price.unknown_vaccine")
        assert (bad.status_code, bad.json()["code"]) == (422, "fee.invalid_amount")


class TestVisitCharge:
    def test_a_mixed_visit_returns_the_total(
        self, seed, client, receptionist_headers, nurse_headers, agenda, priced  # noqa: F811
    ):
        appt = _walk_in(seed, client, receptionist_headers, agenda)

        resp = client.post(f"{API}/vaccinations/visits", headers=nurse_headers, json=_visit(
            seed, appt["id"],
            [_dose("TD", "clinic"), _dose("INFLU", "clinic"), _dose("HEPA", "minsal")]))

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert (body["listed_fee"], body["fee"], body["fee_note"]) == ("45.00", "45.00", None)
        assert [r["listed_fee"] for r in body["records"]] == ["25.00", "20.00", "0.00"]
        assert [r["supply"] for r in body["records"]] == ["clinic", "clinic", "minsal"]

    def test_the_supplier_is_required(
        self, seed, client, receptionist_headers, nurse_headers, agenda, priced  # noqa: F811
    ):
        appt = _walk_in(seed, client, receptionist_headers, agenda)

        resp = client.post(f"{API}/vaccinations/visits", headers=nurse_headers, json=_visit(
            seed, appt["id"], [{"vaccine_code": "TD", "lot": "L-1"}]))

        assert resp.status_code == 422
        assert resp.json()["code"] == "vaccination.supply_required"

    def test_a_private_dose_without_a_price_is_422(
        self, seed, client, receptionist_headers, nurse_headers, agenda  # noqa: F811
    ):
        appt = _walk_in(seed, client, receptionist_headers, agenda)

        resp = client.post(f"{API}/vaccinations/visits", headers=nurse_headers, json=_visit(
            seed, appt["id"], [_dose("TD", "clinic")]))

        assert resp.status_code == 422
        body = resp.json()
        assert (body["code"], body["params"]) == (
            "vaccination.price_missing", {"vaccine": "TD"})

    def test_the_charge_goes_down_but_not_up_and_voiding_recalculates(
        self, seed, client, receptionist_headers, nurse_headers, admin_headers,
        agenda, priced,  # noqa: F811
    ):
        appt = _walk_in(seed, client, receptionist_headers, agenda)
        visit = client.post(f"{API}/vaccinations/visits", headers=nurse_headers, json=_visit(
            seed, appt["id"], [_dose("TD", "clinic"), _dose("INFLU", "clinic")])).json()

        up = client.put(f"{API}/appointments/{appt['id']}/fee",
                        json={"amount": 50, "note": "x"}, headers=admin_headers)
        down = client.put(f"{API}/appointments/{appt['id']}/fee",
                          json={"amount": 40, "note": "Cortesía"}, headers=admin_headers)
        voided = client.post(f"{API}/vaccinations/{visit['records'][0]['id']}/void",
                             json={"reason": "Error"}, headers=nurse_headers)

        assert (up.status_code, up.json()["code"], up.json()["params"]) == (
            422, "fee.vaccination_above_list", {"max": "45.00"})
        assert down.status_code == 200 and down.json()["fee"] == "40.00"
        assert voided.status_code == 200
        listing = client.get(
            f"{API}/appointments", params={"on": "2026-05-31"}, headers=admin_headers
        ).json()
        stored = next(a for a in listing if a["id"] == appt["id"])
        assert (stored["listed_fee"], stored["fee"]) == ("20.00", "20.00")


class TestAdjustBeforeAnyDose:
    def test_an_open_vaccination_cannot_be_charged_before_its_doses(
        self, seed, client, admin_headers, receptionist_headers, agenda  # noqa: F811
    ):
        appt = _walk_in(seed, client, receptionist_headers, agenda)
        resp = client.put(f"{API}/appointments/{appt['id']}/fee",
                          json={"amount": 5, "note": "x"}, headers=admin_headers)

        assert resp.status_code == 422
        assert resp.json()["code"] == "fee.vaccination_pending"
