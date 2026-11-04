"""API tests for the first-login onboarding checklist."""

from __future__ import annotations


def test_requires_authentication(client):
    assert client.get("/api/v1/auth/me/onboarding").status_code == 401


def test_doctor_checklist_and_dismiss(client, auth_headers):
    resp = client.get("/api/v1/auth/me/onboarding", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["welcome_seen"] is False and body["dismissed"] is False
    assert [s["key"] for s in body["steps"]] == [
        "availability",
        "patient",
        "appointment",
        "consultation",
        "profile",
    ]

    resp = client.patch(
        "/api/v1/auth/me/onboarding", json={"welcome_seen": True}, headers=auth_headers
    )
    assert resp.status_code == 204
    assert client.get("/api/v1/auth/me/onboarding", headers=auth_headers).json()["welcome_seen"]

    client.patch("/api/v1/auth/me/onboarding", json={"dismissed": True}, headers=auth_headers)
    body = client.get("/api/v1/auth/me/onboarding", headers=auth_headers).json()
    assert body["dismissed"] is True and body["steps"] == []


def test_receptionist_has_no_steps(client, receptionist_headers):
    body = client.get("/api/v1/auth/me/onboarding", headers=receptionist_headers).json()
    assert body["steps"] == []
