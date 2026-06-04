"""HTTP tests for the tenant audit trail endpoint."""

from __future__ import annotations


class TestAuditApi:
    def test_doctor_cannot_list_audit(self, seed, client, auth_headers):
        resp = client.get("/api/v1/audit", headers=auth_headers)
        assert resp.status_code == 403

    def test_admin_lists_audit_with_actor_name(self, seed, client, admin_headers):
        # Generate an audited action (user.invited) as the admin.
        invite = client.post(
            "/api/v1/users",
            json={"name": "Nuevo", "email": "nuevo@clinic.test", "role": "nurse",
                  "password": "tempPass12"},
            headers=admin_headers,
        )
        assert invite.status_code == 201, invite.text

        resp = client.get("/api/v1/audit", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 1 and "offset" in body and "limit" in body
        invited = [e for e in body["items"] if e["action"] == "user.invited"]
        assert invited, body
        assert invited[0]["actor_name"] == seed.admin.name
        assert "ip_address" in invited[0]

    def test_admin_filters_audit_by_category(self, seed, client, admin_headers):
        client.post(
            "/api/v1/users",
            json={"name": "Otra", "email": "otra@clinic.test", "role": "nurse",
                  "password": "tempPass12"},
            headers=admin_headers,
        )
        resp = client.get(
            "/api/v1/audit", params={"category": "appointment"}, headers=admin_headers
        )
        assert resp.status_code == 200
        assert all(e["action"].startswith("appointment.") for e in resp.json()["items"])
