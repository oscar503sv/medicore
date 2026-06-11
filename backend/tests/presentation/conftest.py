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


def bearer_login(client, url: str, payload: dict, cookie: str = "mc_session") -> dict:
    """Login and return a Bearer header built from the session cookie.

    The token now travels only in an httpOnly cookie; for header-based tests we read it
    from the cookie jar and then CLEAR the jar, so requests are authenticated exactly the
    way they were before cookies existed (and 401 tests aren't polluted by a stale cookie).
    """
    resp = client.post(url, json=payload)
    assert resp.status_code == 200, resp.text
    token = client.cookies.get(cookie)
    assert token, f"login did not set the {cookie} cookie"
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(seed, client):
    """Login as the doctor and return Authorization header."""
    return bearer_login(
        client,
        "/api/v1/auth/login",
        {"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD},
    )


@pytest.fixture
def admin_headers(seed, client):
    """Login as admin."""
    return bearer_login(
        client,
        "/api/v1/auth/login",
        {"slug": str(seed.tenant.slug), "email": seed.admin.email, "password": PASSWORD},
    )


@pytest.fixture
def platform_headers(seed, client):
    """Login as the platform superadmin and return Authorization header."""
    return bearer_login(
        client,
        "/api/v1/platform/login",
        {"email": seed.platform_admin.email, "password": PASSWORD},
        cookie="mc_platform",
    )


@pytest.fixture
def receptionist_headers(seed, client):
    return bearer_login(
        client,
        "/api/v1/auth/login",
        {
            "slug": str(seed.tenant.slug),
            "email": seed.receptionist.email,
            "password": PASSWORD,
        },
    )
