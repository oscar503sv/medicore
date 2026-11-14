"""A temporary password only lets the account replace it: the rule lives in the backend,
not in the screen that redirects to the change form."""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from medicore.presentation.app import create_app
from medicore.presentation.dependencies import get_actor_allowing_password_change
from tests.presentation.conftest import bearer_login
from tests.support.builders import PASSWORD

NEW_PASSWORD = "nueva-clave-segura-1"


@pytest.fixture
def temporary_headers(seed, client):
    seed.doctor.must_change_password = True
    return bearer_login(
        client,
        "/api/v1/auth/login",
        {"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD},
    )


def test_clinical_data_is_refused_until_the_password_changes(client, temporary_headers):
    resp = client.get("/api/v1/patients", headers=temporary_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.password_change_required"


def test_preferences_and_profile_edits_are_refused(client, temporary_headers):
    theme = client.post("/api/v1/auth/theme", json={"theme": "dark"}, headers=temporary_headers)
    profile = client.patch(
        "/api/v1/auth/me", json={"full_name": "Otro Nombre"}, headers=temporary_headers
    )
    assert theme.status_code == 403
    assert profile.status_code == 403


def test_the_change_screen_can_still_load_the_profile_and_sign_out(client, temporary_headers):
    assert client.get("/api/v1/auth/me", headers=temporary_headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=temporary_headers).status_code == 204


def test_changing_the_password_unlocks_the_same_session(client, temporary_headers):
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=temporary_headers,
    )
    assert resp.status_code == 204
    assert client.get("/api/v1/patients", headers=temporary_headers).status_code == 200


def test_support_session_is_exempt(seed, client, platform_headers):
    seed.admin.must_change_password = True
    resp = client.post(
        f"/api/v1/platform/tenants/{seed.tenant.id}/impersonate",
        headers=platform_headers,
        json={"reason": "soporte: apoyo a la clínica"},
    )
    assert resp.status_code == 200, resp.text
    support = {"Authorization": f"Bearer {client.cookies.get('mc_session')}"}
    client.cookies.clear()
    assert client.get("/api/v1/patients", headers=support).status_code == 200


def _dependants(dependant):
    yield dependant
    for child in dependant.dependencies:
        yield from _dependants(child)


def test_only_the_change_screen_endpoints_skip_the_password_check():
    exempt = set()
    for route in create_app().routes:
        if not isinstance(route, APIRoute):
            continue
        if any(d.call is get_actor_allowing_password_change for d in _dependants(route.dependant)):
            exempt.update((method, route.path) for method in route.methods)
    assert exempt == {("POST", "/api/v1/auth/change-password"), ("GET", "/api/v1/auth/me")}
