"""API tests: reports on screen and as CSV (the test clock is 2026-05-31)."""

from __future__ import annotations

from datetime import datetime

import pytest

from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentStatus, AppointmentType
from medicore.domain.shared.identifiers import AppointmentId
from medicore.domain.value_objects.fee import Charge, fee

MAY = "start=2026-05-01&end=2026-05-31"


@pytest.fixture
def booked(seed):
    seed.patient.first_name = "=HYPERLINK(1)"  # a name that looks like a formula
    for code, day, status in (("A-1", 4, AppointmentStatus.COMPLETED),
                              ("A-2", 6, AppointmentStatus.NO_SHOW)):
        a = Appointment(
            id=AppointmentId.new(), tenant_id=seed.tenant.id, code=code,
            patient_id=seed.patient.id, doctor_id=seed.doctor.id,
            location_id=seed.tenant.primary_location.id, type=AppointmentType.CONSULT,
            scheduled_start=datetime(2026, 5, day, 9, 30), duration_minutes=30,
            reason="Control", created_by_id=seed.receptionist.id, status=status,
            charge=Charge.at_list_price(fee("25")), created_at=datetime(2026, 5, 1),
        )
        seed.factory.store.appointments[a.id.value] = a
    return seed


def test_report_json(client, auth_headers, booked):
    resp = client.get(f"/api/v1/reports/appointments?{MAY}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["scope"], body["money"]) == ("own", True)
    keys = [c["key"] for c in body["detail"]["columns"]]
    first = dict(zip(keys, body["detail"]["rows"][0], strict=True))
    assert (first["date"], first["time"], first["code"], first["charged"]) == (
        "2026-05-04", "09:30", "A-1", "25.00")
    assert {"key": "status", "kind": "enum:appointment_status"} in body["detail"]["columns"]


def test_csv_export(client, auth_headers, booked, seed):
    resp = client.get(f"/api/v1/reports/appointments/csv?{MAY}&lang=es", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'filename="medicore-appointments-2026-05-01-2026-05-31.csv"' in resp.headers[
        "content-disposition"]
    text = resp.content.decode("utf-8")
    assert text.startswith("﻿Fecha,Hora,Código")
    lines = text.strip().splitlines()
    assert len(lines) == 3
    assert "Completada" in lines[1] and "No asistió" in lines[2]
    assert ",'=HYPERLINK(1)" in lines[1]  # never handed to a spreadsheet as a formula
    assert "Particular" in lines[1]
    actions = [a.action for a in seed.factory.store.audit.values()]
    assert "report.exported" in actions

    summary = client.get(f"/api/v1/reports/appointments/csv?{MAY}&part=summary&lang=en",
                         headers=auth_headers)
    assert summary.content.decode("utf-8").startswith("﻿Status,Appointments")


def test_errors(client, admin_headers, receptionist_headers):
    resp = client.get(f"/api/v1/reports/appointments?{MAY}", headers=receptionist_headers)
    assert resp.status_code == 403 and resp.json()["code"] == "report.not_allowed"
    resp = client.get(f"/api/v1/reports/income?{MAY}", headers=admin_headers)
    assert resp.status_code == 403 and resp.json()["code"] == "report.money_required"
    resp = client.get("/api/v1/reports/appointments?start=2026-05-10&end=2026-05-01",
                      headers=admin_headers)
    assert resp.status_code == 400 and resp.json()["code"] == "report.invalid_range"
    resp = client.get(f"/api/v1/reports/appointments/csv?{MAY}&lang=fr", headers=admin_headers)
    assert resp.status_code == 422
