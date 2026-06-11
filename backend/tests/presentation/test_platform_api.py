"""API tests: platform (superadmin) endpoints."""

from __future__ import annotations

from tests.support.builders import PASSWORD


def test_platform_login_and_me(seed, client, platform_headers):
    resp = client.get("/api/v1/platform/me", headers=platform_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == seed.platform_admin.email


def test_platform_login_bad_credentials(seed, client):
    resp = client.post(
        "/api/v1/platform/login",
        json={"email": seed.platform_admin.email, "password": "wrong"},
    )
    assert resp.status_code == 401


def test_platform_endpoints_require_platform_token(seed, client, auth_headers):
    # a normal tenant token must not access platform endpoints
    assert client.get("/api/v1/platform/tenants", headers=auth_headers).status_code == 401
    # and a platform token must not access tenant endpoints
    client.post(
        "/api/v1/platform/login",
        json={"email": seed.platform_admin.email, "password": PASSWORD},
    )
    plat = client.cookies.get("mc_platform")
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {plat}"}
    assert client.get("/api/v1/patients", headers=headers).status_code == 401


def test_list_and_create_tenant(seed, client, platform_headers):
    listing = client.get("/api/v1/platform/tenants", headers=platform_headers)
    assert listing.status_code == 200
    initial_total = listing.json()["total"]

    resp = client.post(
        "/api/v1/platform/tenants",
        headers=platform_headers,
        json={
            "legal_name": "Clínica Este SL",
            "tax_id": "B77",
            "slug": "clinica-este",
            "location_name": "Valencia",
            "admin_name": "Admin Este",
            "admin_email": "admin@este.test",
            "admin_password": "temp-pass-123",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["tenant"]["slug"] == "clinica-este"
    assert data["tenant"]["icd_version"] == "cie11"

    listing2 = client.get("/api/v1/platform/tenants", headers=platform_headers)
    assert listing2.json()["total"] == initial_total + 1


def test_set_tenant_status_blocks_login(seed, client, platform_headers):
    resp = client.post(
        f"/api/v1/platform/tenants/{seed.tenant.id}/status",
        headers=platform_headers,
        json={"status": "suspended"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"
    # the clinic's users can no longer log in
    login = client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD},
    )
    assert login.status_code == 401


def test_update_tenant_icd_version(seed, client, platform_headers):
    resp = client.patch(
        f"/api/v1/platform/tenants/{seed.tenant.id}",
        headers=platform_headers,
        json={"icd_version": "cie10"},
    )
    assert resp.status_code == 200
    assert resp.json()["icd_version"] == "cie10"


def test_global_stats_endpoint(seed, client, platform_headers):
    resp = client.get("/api/v1/platform/stats", headers=platform_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_clinics"] == 1
    assert data["total_users"] == 4
    assert data["by_clinic"][0]["patients"] == 1


def test_tenant_stats_endpoint(seed, client, platform_headers):
    resp = client.get(f"/api/v1/platform/tenants/{seed.tenant.id}/stats", headers=platform_headers)
    assert resp.status_code == 200
    assert resp.json()["users"] == 4


def test_list_tenant_users_and_reset_password(seed, client, platform_headers):
    listing = client.get(
        f"/api/v1/platform/tenants/{seed.tenant.id}/users", headers=platform_headers
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 4

    resp = client.post(
        f"/api/v1/platform/tenants/{seed.tenant.id}/users/{seed.doctor.id}/reset-password",
        headers=platform_headers,
        json={"password": "fresh-temp-pass"},
    )
    assert resp.status_code == 200, resp.text
    # the doctor must now change password on next login
    login = client.post(
        "/api/v1/auth/login",
        json={
            "slug": str(seed.tenant.slug),
            "email": seed.doctor.email,
            "password": "fresh-temp-pass",
        },
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True


def test_unlock_user_endpoint(seed, client, platform_headers):
    from medicore.domain.enums import UserStatus

    seed.doctor.status = UserStatus.SUSPENDED
    seed.factory.store.users[seed.doctor.id.value] = seed.doctor

    resp = client.post(
        f"/api/v1/platform/tenants/{seed.tenant.id}/users/{seed.doctor.id}/unlock",
        headers=platform_headers,
    )
    assert resp.status_code == 200
    assert seed.factory.store.users[seed.doctor.id.value].status == UserStatus.ACTIVE


def test_global_audit_endpoint(seed, client, platform_headers):
    # generate a tenant audit entry by logging in a clinic user
    client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD},
    )
    resp = client.get("/api/v1/platform/audit", headers=platform_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    login = next(e for e in body["items"] if e["action"] == "auth.login")
    assert login["source_kind"] == "tenant"
    assert login["clinic_name"] == seed.tenant.legal_name
    assert login["actor_name"] == seed.doctor.name
    assert "ip_address" in login
