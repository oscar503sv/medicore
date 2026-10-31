"""API tests for the notification inbox."""

from __future__ import annotations

from medicore.domain.shared.identifiers import NotificationId

BASE = "/api/v1/notifications"


def _book(client, seed, headers):
    resp = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": str(seed.patient.id),
            "doctor_id": str(seed.doctor.id),
            "location_id": str(seed.tenant.primary_location.id),
            "type": "consult",
            "scheduled_start": "2026-06-01T09:00:00",
            "reason": "Control",
        },
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def test_requires_authentication(client):
    assert client.get(BASE).status_code == 401
    assert client.get(f"{BASE}/unread-count").status_code == 401


def test_booking_reaches_the_doctors_inbox_and_can_be_read(
    client, seed, auth_headers, receptionist_headers
):
    appt = _book(client, seed, receptionist_headers)

    assert client.get(f"{BASE}/unread-count", headers=auth_headers).json() == {"unread_count": 1}
    body = client.get(BASE, headers=auth_headers).json()
    assert body["unread_count"] == 1
    [item] = body["items"]
    assert item["type"] == "appointment.created"
    assert item["data"]["appointment_id"] == appt["id"]
    assert item["data"]["actor_name"] == seed.receptionist.name
    assert item["read_at"] is None

    resp = client.post(f"{BASE}/{item['id']}/read", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["read_at"] is not None
    assert client.get(f"{BASE}/unread-count", headers=auth_headers).json() == {"unread_count": 0}
    # The receptionist made the booking: nothing in their inbox.
    assert client.get(BASE, headers=receptionist_headers).json()["items"] == []


def test_read_all_and_unread_filter(client, seed, auth_headers, receptionist_headers):
    _book(client, seed, receptionist_headers)

    assert client.post(f"{BASE}/read-all", headers=auth_headers).json() == {"marked": 1}
    assert client.get(f"{BASE}?unread_only=true", headers=auth_headers).json()["items"] == []
    assert len(client.get(BASE, headers=auth_headers).json()["items"]) == 1


def test_someone_elses_notification_is_not_found(
    client, seed, auth_headers, receptionist_headers
):
    _book(client, seed, receptionist_headers)
    [item] = client.get(BASE, headers=auth_headers).json()["items"]

    resp = client.post(f"{BASE}/{item['id']}/read", headers=receptionist_headers)
    assert resp.status_code == 404
    unknown = client.post(f"{BASE}/{NotificationId.new()}/read", headers=auth_headers)
    assert unknown.status_code == 404
    assert client.post(f"{BASE}/not-a-uuid/read", headers=auth_headers).status_code == 422


def test_limit_is_bounded(client, auth_headers):
    assert client.get(f"{BASE}?limit=101", headers=auth_headers).status_code == 422
