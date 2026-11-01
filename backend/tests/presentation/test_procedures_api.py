"""API tests: procedures endpoints (catalog, lifecycle, consultation orders, permissions)."""

from __future__ import annotations

from tests.presentation.conftest import PASSWORD, bearer_login


def _catalog(client, headers) -> dict[str, dict]:
    resp = client.get("/api/v1/procedures/catalog", headers=headers)
    assert resp.status_code == 200, resp.text
    return {t["name"]: t for t in resp.json()}


def _nurse(seed, client):
    return bearer_login(client, "/api/v1/auth/login", {
        "slug": str(seed.tenant.slug), "email": seed.nurse.email, "password": PASSWORD})


def test_procedure_lifecycle(seed, client, auth_headers):
    types = _catalog(client, auth_headers)
    suture = types["Sutura de herida"]
    assert suture["requires_consent"] and suture["technique_template"]
    resp = client.post("/api/v1/procedures", json={
        "patient_id": str(seed.patient.id), "type_id": suture["id"],
        "indication": "Herida en mano izquierda"}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    detail = resp.json()
    pid = detail["procedure"]["id"]
    assert detail["technique_template"] == suture["technique_template"]

    resp = client.post(f"/api/v1/procedures/{pid}/sign", headers=auth_headers)
    assert resp.status_code == 422 and resp.json()["code"] == "procedure.consent_required"
    resp = client.post(f"/api/v1/procedures/{pid}/consent", json={
        "signer": "Ana Pérez", "witness": "Lucía Méndez"}, headers=auth_headers)
    assert resp.json()["procedure"]["consent_by_name"]
    resp = client.put(f"/api/v1/procedures/{pid}", json={
        "allergies_reviewed": True, "technique": "4 puntos simples", "bp_before": "118/76",
        "specimen_sent": False}, headers=auth_headers)
    assert resp.json()["procedure"]["status"] == "in_progress"
    resp = client.post(f"/api/v1/procedures/{pid}/sign", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    done = resp.json()["procedure"]
    assert done["status"] == "completed" and done["follow_up_on"] and done["performed_by_name"]

    resp = client.put(f"/api/v1/procedures/{pid}", json={"technique": "x"}, headers=auth_headers)
    assert resp.json()["code"] == "procedure.closed"
    resp = client.post(f"/api/v1/procedures/{pid}/amendments", json={
        "text": "Fueron 5 puntos", "reason": "Conteo"}, headers=auth_headers)
    assert resp.json()["procedure"]["amendments"][0]["by_name"]

    wl = client.get("/api/v1/procedures/worklist", headers=auth_headers).json()
    assert [i["procedure"]["id"] for i in wl["done"]] == [pid] and wl["pending"] == []
    mine = client.get(f"/api/v1/procedures/patients/{seed.patient.id}", headers=auth_headers)
    assert [p["id"] for p in mine.json()] == [pid]


def test_nurse_scope_and_reception_read_only(seed, client, auth_headers, receptionist_headers):
    types = _catalog(client, auth_headers)
    nurse = _nurse(seed, client)
    def create(name, headers):
        body = {"patient_id": str(seed.patient.id), "indication": "Control",
                "type_id": types[name]["id"]}
        return client.post("/api/v1/procedures", json=body, headers=headers)

    resp = create("Biopsia de piel", nurse)
    assert resp.status_code == 403 and resp.json()["code"] == "procedure.doctor_only"
    assert create("Lavado de oído", nurse).status_code == 201
    wl = client.get("/api/v1/procedures/worklist", headers=receptionist_headers)
    assert wl.status_code == 200
    assert create("Lavado de oído", receptionist_headers).status_code == 403


def test_catalog_admin_only(seed, client, auth_headers, admin_headers):
    body = {"name": "Taponamiento nasal", "performer": "doctor", "follow_up_days": 2}
    assert client.post("/api/v1/procedures/catalog", json=body,
                       headers=auth_headers).status_code == 403
    resp = client.post("/api/v1/procedures/catalog", json=body, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    tid = resp.json()["id"]
    resp = client.post("/api/v1/procedures/catalog", json=body, headers=admin_headers)
    assert resp.json()["code"] == "procedure.name_taken"
    resp = client.post(f"/api/v1/procedures/catalog/{tid}/active", json={"active": False},
                       headers=admin_headers)
    assert resp.json()["active"] is False
    resp = client.put(f"/api/v1/procedures/catalog/{tid}",
                      json={**body, "performer": "doctor_or_nurse"}, headers=admin_headers)
    assert resp.json()["performer"] == "doctor_or_nurse" and resp.json()["active"] is False
