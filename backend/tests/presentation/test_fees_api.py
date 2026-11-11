"""API tests: doctors' fees, the price on bookings, adjusting charges, procedure prices."""

from __future__ import annotations

from tests.presentation.test_appointments_api import _booking_payload


def test_fees_list_update_and_booking(seed, client, auth_headers, receptionist_headers,
                                      admin_headers):
    doctor = str(seed.doctor.id)
    resp = client.put(f"/api/v1/fees/{doctor}", json={"prices": {
        "consult": 30, "follow_up": "15.5"}}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["prices"] == {"consult": "30.00", "follow_up": "15.50"}

    resp = client.put(f"/api/v1/fees/{doctor}", json={"prices": {"consult": 30}},
                      headers=receptionist_headers)
    assert resp.status_code == 403 and resp.json()["code"] == "fee.not_allowed"
    resp = client.put(f"/api/v1/fees/{doctor}", json={"prices": {"procedure": 30}},
                      headers=auth_headers)
    assert resp.json()["code"] == "fee.procedure_from_catalog"
    resp = client.put(f"/api/v1/fees/{doctor}", json={"prices": {"consult": "12.345"}},
                      headers=auth_headers)
    assert resp.json()["code"] == "fee.invalid_amount"

    (row,) = client.get("/api/v1/fees", headers=receptionist_headers).json()
    assert row["prices"]["consult"] == "30.00" and row["editable"] is False

    appt = client.post("/api/v1/appointments", json=_booking_payload(seed),
                       headers=receptionist_headers).json()
    assert (appt["listed_fee"], appt["fee"], appt["fee_note"]) == ("30.00", "30.00", None)

    resp = client.put(f"/api/v1/appointments/{appt['id']}/fee", json={"amount": 20},
                      headers=auth_headers)
    assert resp.json()["code"] == "fee.note_required"
    resp = client.put(f"/api/v1/appointments/{appt['id']}/fee",
                      json={"amount": 20, "note": "Adulto mayor"}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["fee"], resp.json()["fee_note"]) == ("20.00", "Adulto mayor")
    resp = client.put(f"/api/v1/appointments/{appt['id']}/fee",
                      json={"amount": 20, "note": "x"}, headers=receptionist_headers)
    assert resp.status_code == 403


def test_procedure_prices_and_charges(seed, client, auth_headers, admin_headers):
    catalog = {t["name"]: t for t in client.get(
        "/api/v1/procedures/catalog", headers=admin_headers).json()}
    suture = catalog["Sutura de herida"]
    payload = {k: suture[k] for k in (
        "name", "performer", "requires_consent", "follow_up_days", "takes_specimen",
        "technique_template", "instructions_template")}
    resp = client.put(f"/api/v1/procedures/catalog/{suture['id']}",
                      json={**payload, "price": "35"}, headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["price"] == "35.00"

    detail = client.post("/api/v1/procedures", json={
        "patient_id": str(seed.patient.id), "type_id": suture["id"],
        "indication": "Herida en mano"}, headers=auth_headers).json()
    p = detail["procedure"]
    assert (p["listed_fee"], p["fee"], p["fee_included"]) == ("35.00", "35.00", False)
    assert detail["fee_editable"] is True

    resp = client.put(f"/api/v1/procedures/{p['id']}/fee", json={"included": True},
                      headers=auth_headers)
    assert resp.json()["code"] == "fee.included_needs_consultation"
    resp = client.put(f"/api/v1/procedures/{p['id']}/fee",
                      json={"amount": "30", "note": "Descuento"}, headers=auth_headers)
    assert resp.json()["procedure"]["fee"] == "30.00"
