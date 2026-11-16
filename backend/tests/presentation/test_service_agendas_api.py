"""API tests: service agendas, their schedule, booking into them and the vaccination visit."""

from __future__ import annotations

from uuid import uuid4

import pytest

MONDAY = "2026-06-01"
WEEK = [{"day_of_week": d, "enabled": True, "blocks": [{"start": "09:00", "end": "13:00"}]}
        for d in range(5)]


@pytest.fixture
def agenda(client, admin_headers):
    resp = client.post("/api/v1/service-agendas", json={"name": "Vacunatorio"},
                       headers=admin_headers)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    base = f"/api/v1/availability/agendas/{created['id']}"
    assert client.put(f"{base}/weekly", json=WEEK, headers=admin_headers).status_code == 200
    rules = {"slot_minutes": 15, "min_advance_hours": 0, "allow_same_day": True}
    assert client.put(f"{base}/rules", json=rules, headers=admin_headers).status_code == 200
    return created


def _booking(seed, agenda, **overrides):
    body = {
        "patient_id": str(seed.patient.id), "agenda_id": agenda["id"],
        "location_id": str(seed.tenant.primary_location.id), "type": "vaccination",
        "scheduled_start": f"{MONDAY}T09:00:00", "reason": "Vacunas",
    }
    return body | overrides


def _walk_in(seed, client, headers, agenda) -> dict:
    resp = client.post(
        "/api/v1/appointments/walk-in",
        json={"patient_id": str(seed.patient.id), "agenda_id": agenda["id"],
              "type": "vaccination", "reason": "Vacuna"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestAgendas:
    def test_create_list_rename_archive(self, client, admin_headers, receptionist_headers):
        created = client.post("/api/v1/service-agendas", json={"name": " Vacunatorio "},
                              headers=admin_headers).json()
        assert created["name"] == "Vacunatorio" and created["kind"] == "vaccination"
        assert created["active"] and created["slot_minutes"] is None

        renamed = client.patch(f"/api/v1/service-agendas/{created['id']}",
                               json={"name": "Sala de vacunas"}, headers=admin_headers)
        assert renamed.json()["name"] == "Sala de vacunas"

        archived = client.post(f"/api/v1/service-agendas/{created['id']}/active",
                               json={"active": False}, headers=admin_headers)
        assert archived.json()["active"] is False

        listed = client.get("/api/v1/service-agendas?active_only=true",
                            headers=receptionist_headers)
        assert listed.status_code == 200 and listed.json() == []

    def test_a_duplicate_name_is_409_with_a_code(self, client, admin_headers, agenda):
        resp = client.post("/api/v1/service-agendas", json={"name": "vacunatorio"},
                           headers=admin_headers)

        assert resp.status_code == 409
        assert resp.json()["code"] == "service_agenda.name_taken"
        assert resp.json()["params"] == {"name": "vacunatorio"}

    def test_only_organization_managers_change_them(self, client, receptionist_headers, agenda):
        assert client.post("/api/v1/service-agendas", json={"name": "Otra"},
                           headers=receptionist_headers).status_code == 403
        assert client.put(f"/api/v1/availability/agendas/{agenda['id']}/rules",
                          json={"slot_minutes": 30}, headers=receptionist_headers
                          ).status_code == 403

    def test_the_schedule_shows_in_the_list_and_the_booking_options(
        self, client, receptionist_headers, agenda
    ):
        listed = client.get("/api/v1/service-agendas", headers=receptionist_headers).json()
        assert listed[0]["slot_minutes"] == 15

        options = client.get("/api/v1/appointments/booking-options",
                             headers=receptionist_headers).json()
        assert [(a["id"], a["slot_minutes"]) for a in options["agendas"]] == [(agenda["id"], 15)]


class TestBooking:
    def test_slots_by_agenda(self, client, receptionist_headers, agenda):
        resp = client.get(f"/api/v1/appointments/slots?agenda_id={agenda['id']}&on={MONDAY}",
                          headers=receptionist_headers)

        assert resp.status_code == 200
        assert len([s for s in resp.json() if s["status"] == "free"]) == 16  # 240 / 15

    def test_both_or_neither_assignee_is_422(self, seed, client, receptionist_headers, agenda):
        both = client.post(
            "/api/v1/appointments",
            json=_booking(seed, agenda, doctor_id=str(seed.doctor.id)),
            headers=receptionist_headers,
        )
        neither = client.get(f"/api/v1/appointments/slots?on={MONDAY}",
                             headers=receptionist_headers)

        assert both.status_code == 422
        assert both.json()["code"] == "appointment.assignee_required"
        assert neither.status_code == 422

    def test_book_and_list_an_agenda_appointment(self, seed, client, receptionist_headers, agenda):
        resp = client.post("/api/v1/appointments", json=_booking(seed, agenda),
                           headers=receptionist_headers)

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["doctor_id"] is None and body["agenda_id"] == agenda["id"]
        assert body["fee"] is None and body["duration_minutes"] == 15

        day = client.get(f"/api/v1/appointments?on={MONDAY}&agenda_id={agenda['id']}",
                         headers=receptionist_headers).json()
        assert [(a["id"], a["agenda_name"], a["doctor_name"]) for a in day] == [
            (body["id"], "Vacunatorio", None)
        ]

    def test_another_type_is_refused_by_the_agenda(
        self, seed, client, receptionist_headers, agenda
    ):
        resp = client.post("/api/v1/appointments", json=_booking(seed, agenda, type="consult"),
                           headers=receptionist_headers)

        assert resp.status_code == 422
        assert resp.json()["code"] == "appointment.type_not_for_agenda"

    def test_a_walk_in_goes_to_the_agenda(self, seed, client, receptionist_headers, agenda):
        resp = client.post(
            "/api/v1/appointments/walk-in",
            json={"patient_id": str(seed.patient.id), "agenda_id": agenda["id"],
                  "type": "vaccination", "reason": "Vacuna"},
            headers=receptionist_headers,
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["is_walk_in"] and resp.json()["agenda_id"] == agenda["id"]

    def test_the_consultation_cannot_start_on_it(self, seed, client, receptionist_headers,
                                                 auth_headers, agenda):
        appt = client.post("/api/v1/appointments", json=_booking(seed, agenda),
                           headers=receptionist_headers).json()

        resp = client.post(f"/api/v1/consultations/start/{appt['id']}", headers=auth_headers)

        assert resp.status_code == 422
        assert resp.json()["code"] == "consultation.not_for_agenda"


class TestOwnership:
    def test_a_doctor_cannot_cancel_an_agenda_appointment(
        self, seed, client, receptionist_headers, auth_headers, agenda
    ):
        appt = client.post("/api/v1/appointments", json=_booking(seed, agenda),
                           headers=receptionist_headers).json()

        resp = client.post(f"/api/v1/appointments/{appt['id']}/cancel", headers=auth_headers)

        assert resp.status_code == 403
        assert resp.json()["code"] == "appointment.not_own"

    def test_reception_cancels_it(self, seed, client, receptionist_headers, agenda):
        appt = client.post("/api/v1/appointments", json=_booking(seed, agenda),
                           headers=receptionist_headers).json()

        resp = client.post(f"/api/v1/appointments/{appt['id']}/cancel",
                           headers=receptionist_headers)

        assert resp.status_code == 200


class TestWhoBooks:
    def test_a_doctor_cannot_book_for_another_doctor(
        self, seed, client, auth_headers, nurse_headers
    ):
        # The nurse's id is not a doctor's, but the ownership check comes first: 403.
        body = {
            "patient_id": str(seed.patient.id), "doctor_id": str(seed.nurse.id),
            "location_id": str(seed.tenant.primary_location.id), "type": "consult",
            "scheduled_start": f"{MONDAY}T09:00:00", "reason": "x",
        }

        resp = client.post("/api/v1/appointments", json=body, headers=auth_headers)

        assert resp.status_code == 403
        assert resp.json()["code"] == "appointment.not_own"

    def test_reception_naming_a_non_doctor_is_a_400(
        self, seed, client, receptionist_headers
    ):
        body = {
            "patient_id": str(seed.patient.id), "doctor_id": str(seed.nurse.id),
            "location_id": str(seed.tenant.primary_location.id), "type": "consult",
            "scheduled_start": f"{MONDAY}T09:00:00", "reason": "x",
        }

        resp = client.post("/api/v1/appointments", json=body, headers=receptionist_headers)

        assert resp.status_code == 400
        assert resp.json()["code"] == "appointment.invalid_doctor"


class TestBookingReferences:
    def test_a_foreign_location_is_a_400_with_a_code(
        self, seed, client, receptionist_headers, agenda
    ):
        resp = client.post(
            "/api/v1/appointments",
            json=_booking(seed, agenda, location_id=str(uuid4())),
            headers=receptionist_headers,
        )

        assert resp.status_code == 400
        assert resp.json()["code"] == "appointment.invalid_location"


class TestVisit:
    def _visit(self, seed, appointment_id, **overrides):
        body = {
            "appointment_id": appointment_id, "patient_id": str(seed.patient.id),
            "doses": [{"vaccine_code": "TD", "lot": "TD-1"},
                      {"vaccine_code": "INFLU", "lot": "IN-9", "site": "left_arm"}],
        }
        return body | overrides

    def test_records_the_doses_and_completes_the_appointment(
        self, seed, client, receptionist_headers, nurse_headers, agenda
    ):
        appt = _walk_in(seed, client, receptionist_headers, agenda)

        resp = client.post("/api/v1/vaccinations/visits",
                           json=self._visit(seed, appt["id"]), headers=nurse_headers)

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["appointment"]["status"] == "completed"
        # The reduced view of the worklist: no reason, fee or insurer.
        assert set(body["appointment"]) == {
            "id", "code", "scheduled_start", "duration_minutes", "status", "type", "is_walk_in"
        }
        assert [r["vaccine_code"] for r in body["records"]] == ["TD", "INFLU"]
        assert {r["appointment_id"] for r in body["records"]} == {appt["id"]}

        again = client.post("/api/v1/vaccinations/visits",
                            json=self._visit(seed, appt["id"]), headers=nurse_headers)
        assert again.status_code == 400
        assert again.json()["code"] == "vaccination.appointment_mismatch"

    def test_a_future_appointment_cannot_be_closed_yet(
        self, seed, client, receptionist_headers, nurse_headers, agenda
    ):
        appt = client.post("/api/v1/appointments", json=_booking(seed, agenda),
                           headers=receptionist_headers).json()

        resp = client.post("/api/v1/vaccinations/visits",
                           json=self._visit(seed, appt["id"]), headers=nurse_headers)

        assert resp.status_code == 400
        assert resp.json()["code"] == "vaccination.appointment_not_today"

    def test_the_worklist_offers_today_visits_without_the_visit_details(
        self, seed, client, receptionist_headers, nurse_headers, agenda
    ):
        appt = _walk_in(seed, client, receptionist_headers, agenda)

        wl = client.get("/api/v1/vaccinations/worklist", headers=nurse_headers).json()

        (item,) = wl["appointments_today"]
        assert set(item) == {"appointment", "patient", "attendant_name"}
        assert set(item["appointment"]) == {
            "id", "code", "scheduled_start", "duration_minutes", "status", "type", "is_walk_in"
        }
        assert item["appointment"]["id"] == appt["id"]
        assert item["attendant_name"] == "Vacunatorio"
        assert item["patient"]["code"] == seed.patient.code

    def test_an_empty_visit_is_422(self, seed, client, nurse_headers, agenda):
        resp = client.post("/api/v1/vaccinations/visits",
                           json=self._visit(seed, agenda["id"], doses=[]), headers=nurse_headers)

        assert resp.status_code == 422
