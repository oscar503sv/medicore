"""API tests: per-user permissions (GET/PUT /users/{id}/permissions)."""

from __future__ import annotations


def _url(seed):
    return f"/api/v1/users/{seed.receptionist.id}/permissions"


def test_get_as_admin(seed, client, admin_headers):
    resp = client.get(_url(seed), headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["available"] is True
    assert data["user"]["permissions_customized"] is False
    assert data["effective"] == data["role_permissions"]
    assert "audit.view" in data["catalog"]


def test_forbidden_for_doctor(seed, client, auth_headers):
    assert client.get(_url(seed), headers=auth_headers).status_code == 403


def test_grant_applies_to_the_users_requests(seed, client, admin_headers, receptionist_headers):
    assert client.get("/api/v1/audit", headers=receptionist_headers).status_code == 403
    role_set = client.get(_url(seed), headers=admin_headers).json()["role_permissions"]

    resp = client.put(
        _url(seed), json={"permissions": [*role_set, "audit.view"]}, headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["granted"] == ["audit.view"]
    assert data["user"]["permissions_customized"] is True
    assert client.get("/api/v1/audit", headers=receptionist_headers).status_code == 200

    listed = client.get("/api/v1/users", headers=admin_headers).json()["items"]
    mine = next(u for u in listed if u["id"] == str(seed.receptionist.id))
    assert mine["permissions_customized"] is True


def test_cannot_edit_own_permissions(seed, client, admin_headers):
    resp = client.put(
        f"/api/v1/users/{seed.admin.id}/permissions",
        json={"permissions": []},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "user_permissions.self"
