"""API tests: insurer catalog endpoints."""

from __future__ import annotations


def _create_insurer(client, admin_headers, name="Sanitas"):
    resp = client.post("/api/v1/insurers", json={"name": name}, headers=admin_headers)
    assert resp.status_code == 201
    return resp.json()


def test_archive_then_reactivate_insurer(seed, client, admin_headers):
    insurer = _create_insurer(client, admin_headers)

    archived = client.post(
        f"/api/v1/insurers/{insurer['id']}/archive", headers=admin_headers
    )
    assert archived.status_code == 200
    assert archived.json()["active"] is False

    restored = client.post(
        f"/api/v1/insurers/{insurer['id']}/reactivate", headers=admin_headers
    )
    assert restored.status_code == 200
    assert restored.json()["active"] is True


def test_doctor_cannot_reactivate_insurer(seed, client, admin_headers, auth_headers):
    insurer = _create_insurer(client, admin_headers, name="Adeslas")
    client.post(f"/api/v1/insurers/{insurer['id']}/archive", headers=admin_headers)
    resp = client.post(
        f"/api/v1/insurers/{insurer['id']}/reactivate", headers=auth_headers
    )
    assert resp.status_code == 403
