"""API tests: in-clinic applications endpoints (doctor login: applications.administer)."""

from __future__ import annotations


def _order(client, headers, patient_id, **kw):
    body = {"patient_id": patient_id, "drug": "Dexametasona", "dose": "8 mg", "route": "im",
            "prescriber": "Dra. Ana Ramos", "jvpm": "4321", **kw}
    return client.post("/api/v1/applications/orders", json=body, headers=headers)


def test_external_order_apply_observe_and_void(seed, client, auth_headers):
    pid = str(seed.patient.id)
    resp = _order(client, auth_headers, pid, observation_minutes=20)
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["source"] == "external" and order["external_jvpm"] == "4321"

    wl = client.get("/api/v1/applications/worklist", headers=auth_headers).json()
    assert [d["order"]["id"] for d in wl["due"]] == [order["id"]]
    assert wl["due"][0]["order"]["next_dose"] == 1

    resp = client.post(f"/api/v1/applications/orders/{order['id']}/records",
                       json={"lot": "DX-12", "site": "left_gluteus", "blood_pressure": "120/80"},
                       headers=auth_headers)
    assert resp.status_code == 201, resp.text
    rec = resp.json()
    assert rec["observe_until"] and rec["recorded_by_name"]

    wl = client.get("/api/v1/applications/worklist", headers=auth_headers).json()
    assert wl["due"] == [] and [o["record"]["id"] for o in wl["observing"]] == [rec["id"]]

    resp = client.post(f"/api/v1/applications/records/{rec['id']}/observation",
                       json={"reaction": False}, headers=auth_headers)
    assert resp.status_code == 200 and resp.json()["observation_closed_by_name"]

    resp = client.post(f"/api/v1/applications/records/{rec['id']}/void",
                       json={"reason": "Lote mal digitado"}, headers=auth_headers)
    assert resp.status_code == 200 and resp.json()["voided_by_name"]

    orders = client.get(f"/api/v1/applications/patients/{pid}", headers=auth_headers).json()
    assert orders[0]["status"] == "pending" and len(orders[0]["records"]) == 1


def test_errors_carry_codes(seed, client, auth_headers):
    pid = str(seed.patient.id)
    resp = _order(client, auth_headers, pid, jvpm="X1")
    assert resp.json()["code"] == "application.invalid_jvpm"
    resp = _order(client, auth_headers, pid, doses_total=3)
    assert resp.json()["code"] == "application.interval_required"
    order = _order(client, auth_headers, pid).json()
    resp = client.post(f"/api/v1/applications/orders/{order['id']}/cancel",
                       json={"reason": "No vino"}, headers=auth_headers)
    assert resp.json()["status"] == "cancelled"
    resp = client.post(f"/api/v1/applications/orders/{order['id']}/records", json={},
                       headers=auth_headers)
    assert resp.json()["code"] == "application.order_closed"


def test_reception_sees_but_cannot_apply(seed, client, auth_headers, receptionist_headers):
    order = _order(client, auth_headers, str(seed.patient.id)).json()
    assert client.get("/api/v1/applications/worklist",
                      headers=receptionist_headers).status_code == 200
    resp = client.post(f"/api/v1/applications/orders/{order['id']}/records", json={},
                       headers=receptionist_headers)
    assert resp.status_code == 403
