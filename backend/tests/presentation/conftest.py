"""Shared fixtures for presentation tests.

We wire the FastAPI app with in-memory adapters (same as the application tests)
so the presentation tests never touch the real database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from medicore.presentation.app import create_app
from medicore.presentation.dependencies import (
    get_clock,
    get_codes,
    get_hasher,
    get_jwt_issuer,
    get_uow,
    get_uow_factory,
)
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import (
    FakeTokenIssuer,
    FixedClock,
    PlainPasswordHasher,
    SequentialCodeGenerator,
)


@pytest.fixture
def seed():
    return seed_clinic()


@pytest.fixture
def client(seed):
    """TestClient wired with in-memory adapters for the given seed."""
    app = create_app()
    factory = seed.factory
    clock = FixedClock()
    codes = SequentialCodeGenerator()
    hasher = PlainPasswordHasher()
    issuer = FakeTokenIssuer()

    def _factory():
        return factory

    app.dependency_overrides[get_uow_factory] = _factory
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_hasher] = lambda: hasher
    app.dependency_overrides[get_jwt_issuer] = lambda: issuer
    app.dependency_overrides[get_uow] = lambda: factory.for_tenant(seed.tenant.id)
    app.dependency_overrides[get_codes] = lambda: codes

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def auth_headers(seed, client):
    """Login as the doctor and return Authorization header."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(seed, client):
    """Login as admin."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": seed.admin.email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture
def platform_headers(seed, client):
    """Login as the platform superadmin and return Authorization header."""
    resp = client.post(
        "/api/v1/platform/login",
        json={"email": seed.platform_admin.email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture
def receptionist_headers(seed, client):
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "slug": str(seed.tenant.slug),
            "email": seed.receptionist.email,
            "password": PASSWORD,
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}
