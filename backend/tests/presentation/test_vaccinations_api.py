"""API tests: vaccinations endpoints."""

from __future__ import annotations


def test_catalog_lists_the_national_schedule(client, auth_headers):
    resp = client.get("/api/v1/vaccinations/catalog", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["schedule"] == "sv-minsal"
    assert any(v["code"] == "HEXA" for v in data["vaccines"])
    assert any(d["key"] == "SPR-1" for d in data["doses"])


def test_record_card_and_void_round_trip(seed, client, auth_headers):
    pid = str(seed.patient.id)
    resp = client.post(
        f"/api/v1/vaccinations/patients/{pid}",
        json={"vaccine_code": "TD", "dose_key": "TD-1", "occurred_on": "2026-05-30",
              "lot": "TD-118", "site": "left_arm"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    rec = resp.json()
    assert rec["route"] == "im" and rec["recorded_by_name"]

    card = client.get(f"/api/v1/vaccinations/patients/{pid}", headers=auth_headers).json()
    td = next(s for s in card["states"] if s["key"] == "TD-1")
    assert td["status"] == "upcoming" and td["last_on"] == "2026-05-30"

    resp = client.post(f"/api/v1/vaccinations/{rec['id']}/void",
                       json={"reason": "Registrado en el paciente equivocado"},
                       headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["voided_by_name"]


def test_validation_errors_carry_codes(seed, client, auth_headers):
    resp = client.post(
        f"/api/v1/vaccinations/patients/{seed.patient.id}",
        json={"vaccine_code": "TD", "occurred_on": "2026-05-30"},  # no lot
        headers=auth_headers,
    )
    assert resp.status_code in (400, 422)
    assert resp.json()["code"] == "vaccination.lot_required"
    resp = client.post(
        f"/api/v1/vaccinations/patients/{seed.patient.id}",
        json={"vaccine_code": "TD", "occurred_on": "2026-05-30", "site": "nose"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_worklist(client, auth_headers):
    resp = client.get("/api/v1/vaccinations/worklist?horizon_days=30", headers=auth_headers)
    assert resp.status_code == 200
    assert set(resp.json()) == {"today", "pending", "upcoming", "given_today"}
