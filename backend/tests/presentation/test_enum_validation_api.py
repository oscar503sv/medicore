"""An unknown enum value in a request body is a 422 naming the field, never a 500.

Bodies are otherwise valid, so without schema-level validation each request would reach the
router's ``Enum(value)`` conversion and blow up with a ValueError.
"""

from __future__ import annotations

import pytest


def _cases(seed) -> list[tuple[str, str, str, str, dict]]:
    tid = seed.tenant.id
    doctor = seed.doctor.id
    new_user = {"name": "Nuevo", "email": "nuevo@x.test", "password": "temporal1"}
    tenant = {
        "legal_name": "Clínica Nueva",
        "tax_id": "B00000000",
        "slug": "clinica-nueva",
        "location_name": "Sede",
        "admin_name": "Admin",
        "admin_email": "admin@nueva.test",
        "admin_password": "temporal1",
    }
    return [
        ("admin", "post", "/users", "role", {**new_user, "role": "chief"}),
        ("admin", "post", "/users", "sex", {**new_user, "role": "nurse", "sex": "x"}),
        ("admin", "patch", f"/users/{doctor}", "role", {"role": "chief"}),
        ("admin", "patch", f"/users/{doctor}", "sex", {"sex": "x"}),
        ("admin", "put", f"/users/{doctor}/role", "role", {"role": "chief"}),
        (
            "receptionist", "post", "/patients", "sex",
            {"first_name": "A", "last_name": "B", "sex": "x", "date_of_birth": "1990-01-01"},
        ),
        (
            "receptionist", "post", "/appointments", "type",
            {
                "patient_id": str(seed.patient.id),
                "doctor_id": str(doctor),
                "location_id": str(seed.tenant.primary_location.id),
                "type": "x",
                "scheduled_start": "2026-06-08T10:00:00",
                "reason": "Control",
            },
        ),
        (
            "doctor", "post", "/documents", "kind",
            {
                "patient_id": str(seed.patient.id),
                "file_name": "a.pdf",
                "kind": "x",
                "mime_type": "application/pdf",
                "size_bytes": 10,
                "storage_key": "k/a.pdf",
            },
        ),
        (
            "doctor", "post", "/availability/me/exceptions", "kind",
            {"date": "2026-07-01", "kind": "x"},
        ),
        ("doctor", "post", "/auth/theme", "theme", {"theme": "neon"}),
        ("doctor", "post", "/auth/locale", "language", {"language": "fr"}),
        ("platform", "post", "/platform/tenants", "icd_version", {**tenant, "icd_version": "cie9"}),
        ("platform", "patch", f"/platform/tenants/{tid}", "icd_version", {"icd_version": "cie9"}),
        ("platform", "post", f"/platform/tenants/{tid}/status", "status", {"status": "deleted"}),
        (
            "platform", "patch", f"/platform/tenants/{tid}/users/{doctor}", "role",
            {"role": "chief"},
        ),
    ]


_HEADERS = {
    "admin": "admin_headers",
    "doctor": "auth_headers",
    "receptionist": "receptionist_headers",
    "platform": "platform_headers",
}


@pytest.mark.parametrize("index", range(15))
def test_unknown_enum_value_is_a_422_naming_the_field(index, request, seed, client):
    who, method, path, field, body = _cases(seed)[index]
    headers = request.getfixturevalue(_HEADERS[who])

    resp = getattr(client, method)(f"/api/v1{path}", json=body, headers=headers)

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "request_invalid"
    assert field in resp.json()["params"]["fields"].split(", ")


def test_case_count_matches_parametrization(seed):
    assert len(_cases(seed)) == 15
