"""API tests: the note template catalog, clinic settings, the doctor's favourite and
switching the template of a live consultation."""

from __future__ import annotations

from tests.presentation.test_consultations_api import _book_and_start


def test_catalog_and_settings(client, auth_headers, admin_headers):
    resp = client.get("/api/v1/note-templates", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [t["key"] for t in body["templates"]][:2] == ["soap", "psoap"]
    assert body["templates"][0]["sections"][0] == {
        "key": "subjective", "role": "subjective", "title": "Subjetivo", "required": True}
    assert (body["can_configure"], body["favourite"]) == (False, None)
    assert len(body["allowed"]) == 5

    settings = {"enabled": ["soap", "history"], "default": "soap",
                "rules": {"first_visit": "history", "follow_up": ""}, "locked": True}
    resp = client.put("/api/v1/note-templates/settings", json=settings, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["settings"]["rules"] == {"first_visit": "history"}  # blanks dropped
    assert resp.json()["allowed"] == ["soap", "history"]

    resp = client.put("/api/v1/note-templates/settings", json=settings, headers=auth_headers)
    assert resp.status_code == 403 and resp.json()["code"] == "note.cannot_configure"
    bad = {**settings, "default": "narrative"}
    resp = client.put("/api/v1/note-templates/settings", json=bad, headers=admin_headers)
    assert resp.status_code in (400, 422) and resp.json()["code"] == "note.default_not_enabled"


def test_favourite(client, auth_headers):
    resp = client.put("/api/v1/note-templates/favourite", json={"template": "narrative"},
                      headers=auth_headers)
    assert resp.status_code == 200 and resp.json()["favourite"] == "narrative"
    resp = client.put("/api/v1/note-templates/favourite", json={"template": "dap"},
                      headers=auth_headers)
    assert resp.json()["code"] == "note.unknown_template"


def test_switch_template_and_autosave_sections(seed, client, auth_headers):
    seed.patient.tags = ["Asma"]
    _, cid = _book_and_start(seed, client, auth_headers)
    resp = client.patch(f"/api/v1/consultations/{cid}/autosave",
                        json={"note": {"subjective": "Tos"}}, headers=auth_headers)
    assert resp.json()["note"]["template"] == "soap"
    assert resp.json()["missing"] == ["objective", "assessment", "plan", "diagnosis", "vitals"]

    resp = client.post(f"/api/v1/consultations/{cid}/note-template",
                       json={"template": "psoap"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    sections = {s["key"]: s["text"] for s in resp.json()["note"]["sections"]}
    assert sections["problems"] == "- Asma" and sections["subjective"] == "Tos"

    resp = client.patch(f"/api/v1/consultations/{cid}/autosave",
                        json={"note": {"anamnesis": "x"}}, headers=auth_headers)
    assert resp.status_code in (400, 422) and resp.json()["code"] == "note.unknown_section"


def test_custom_templates(client, admin_headers, auth_headers):
    body = {"name": "Control prenatal", "sections": [
        {"title": "Evolución del embarazo", "role": "subjective"},
        {"title": "Altura uterina y FCF", "role": "objective"},
        {"title": "Plan", "role": "plan", "required": False}]}
    resp = client.post("/api/v1/note-templates", json=body, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["custom_allowed"] is True
    [custom] = [t for t in resp.json()["templates"] if not t["system"]]
    assert custom["name"] == "Control prenatal"
    assert [s["key"] for s in custom["sections"]] == ["s1", "s2", "s3"]

    resp = client.post("/api/v1/note-templates", json=body, headers=auth_headers)
    assert resp.status_code == 403 and resp.json()["code"] == "note.cannot_configure"
    resp = client.post("/api/v1/note-templates", json={**body, "sections": []},
                       headers=admin_headers)
    assert resp.status_code == 422

    body["name"] = "Prenatal"
    resp = client.put(f"/api/v1/note-templates/{custom['key']}", json=body,
                      headers=admin_headers)
    assert [t["name"] for t in resp.json()["templates"] if not t["system"]] == ["Prenatal"]
    resp = client.delete(f"/api/v1/note-templates/{custom['key']}", headers=admin_headers)
    assert resp.status_code == 200
    assert all(t["system"] for t in resp.json()["templates"])
