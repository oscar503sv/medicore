"""API tests: users, availability and organization management."""

from __future__ import annotations


class TestUsers:
    def test_list_users_as_admin(self, seed, client, admin_headers):
        resp = client.get("/api/v1/users", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 4  # admin + doctor + nurse + receptionist

    def test_doctor_cannot_list_users(self, seed, client, auth_headers):
        resp = client.get("/api/v1/users", headers=auth_headers)
        assert resp.status_code == 403

    def test_invite_user(self, seed, client, admin_headers):
        resp = client.post(
            "/api/v1/users",
            json={"name": "Nuevo", "email": "nuevo@test.es", "role": "nurse"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"

    def test_duplicate_email_rejected(self, seed, client, admin_headers):
        resp = client.post(
            "/api/v1/users",
            json={"name": "Dup", "email": seed.doctor.email, "role": "nurse"},
            headers=admin_headers,
        )
        assert resp.status_code == 400


class TestOrganization:
    def test_get_organization(self, seed, client, admin_headers):
        resp = client.get("/api/v1/organization", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == str(seed.tenant.id)

    def test_non_admin_cannot_see_organization(self, seed, client, auth_headers):
        resp = client.get("/api/v1/organization", headers=auth_headers)
        assert resp.status_code == 403

    def test_update_organization(self, seed, client, admin_headers):
        resp = client.patch(
            "/api/v1/organization",
            json={"legal_name": "Clínica Norte SLU"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["legal_name"] == "Clínica Norte SLU"

    def test_add_location(self, seed, client, admin_headers):
        resp = client.post(
            "/api/v1/organization/locations",
            json={"name": "Madrid · Salamanca"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        names = [loc["name"] for loc in resp.json()["locations"]]
        assert "Madrid · Salamanca" in names


class TestAvailability:
    def test_get_my_availability(self, seed, client, auth_headers):
        resp = client.get("/api/v1/availability/me", headers=auth_headers)
        assert resp.status_code == 200
        av = resp.json()
        assert av["doctor_id"] == str(seed.doctor.id)
        assert len(av["weekly"]) == 7

    def test_update_weekly_schedule(self, seed, client, auth_headers):
        resp = client.put(
            "/api/v1/availability/me/weekly",
            json=[{
                "day_of_week": 5, "enabled": True, "blocks": [{"start": "10:00", "end": "12:00"}]
            }],
            headers=auth_headers,
        )
        assert resp.status_code == 200
        saturday = next(d for d in resp.json()["weekly"] if d["day_of_week"] == 5)
        assert saturday["enabled"]

    def test_preview_returns_seven_days(self, seed, client, auth_headers):
        resp = client.get(
            "/api/v1/availability/preview?week_start=2026-06-01",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["preview"]) == 7

    def test_receptionist_cannot_manage_availability(self, seed, client, receptionist_headers):
        resp = client.get("/api/v1/availability/me", headers=receptionist_headers)
        assert resp.status_code == 403
