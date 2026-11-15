"""API: what the integrity check of a record looks like to the client."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from tests.presentation.test_consultations_api import _book_and_start
from tests.support.records import store_record

RECORDS = "/api/v1/records"
PRINT = "/api/v1/print"
REASON = "Se añade el resultado de laboratorio recibido"


@pytest.fixture
def record(seed):
    return store_record(seed, code="REC-2026-0001", encounter_at=datetime(2026, 5, 20, 9))


def _tamper(seed, record):
    seed.factory.store.medical_records[record.id.value] = replace(
        record, chief_complaint="Otra cosa"
    )


def _amend(client, record, headers):
    return client.post(
        f"{RECORDS}/{record.id}/amend",
        json={"reason": REASON, "chief_complaint": "Fiebre alta"}, headers=headers,
    )


class TestDetailAndVersions:
    def test_a_sound_record_says_ok_and_exposes_its_seal(self, client, auth_headers, record):
        body = client.get(f"{RECORDS}/{record.id}", headers=auth_headers).json()
        assert body["integrity"] == "ok"
        assert body["seal"] == {"version": 1, "digest": record.seal.digest}

    def test_an_altered_record_says_tampered(self, seed, client, auth_headers, record):
        _tamper(seed, record)
        resp = client.get(f"{RECORDS}/{record.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["integrity"] == "tampered"

    def test_versions_carry_their_integrity(self, seed, client, auth_headers, record):
        amendment = _amend(client, record, auth_headers).json()
        _tamper(seed, record)
        versions = client.get(f"{RECORDS}/{record.id}/versions", headers=auth_headers).json()
        assert [(v["id"], v["integrity"]) for v in versions] == [
            (str(record.id), "tampered"), (amendment["id"], "tampered"),
        ]

    def test_the_history_leaves_the_integrity_out(self, seed, client, auth_headers, record):
        body = client.get(
            f"/api/v1/patients/{seed.patient.id}/records", headers=auth_headers
        ).json()
        assert body[0]["integrity"] is None


class TestAmending:
    def test_an_amendment_answers_integrity_ok(self, client, auth_headers, record):
        resp = _amend(client, record, auth_headers)
        assert resp.status_code == 200
        assert resp.json()["integrity"] == "ok"

    def test_an_altered_record_is_refused_with_409(self, seed, client, auth_headers, record):
        _tamper(seed, record)
        resp = _amend(client, record, auth_headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "record.tampered"


def test_signing_answers_integrity_ok(seed, client, auth_headers):
    _, cid = _book_and_start(seed, client, auth_headers)
    client.patch(
        f"/api/v1/consultations/{cid}/autosave",
        json={
            "vitals": {"heart_rate": 72, "weight": "70"},
            "note": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"},
        },
        headers=auth_headers,
    )
    client.post(f"/api/v1/consultations/{cid}/diagnoses",
                json={"code": "I10", "label": "Hipertensión"}, headers=auth_headers)
    resp = client.post(f"/api/v1/consultations/{cid}/sign", json={"chief_complaint": "Control"},
                       headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["integrity"] == "ok" and body["seal"]["version"] == 1


class TestPrinting:
    def test_the_copy_carries_the_seal_fingerprint(self, client, auth_headers, record):
        body = client.get(f"{PRINT}/records/{record.id}?document=record",
                          headers=auth_headers).json()
        assert body["integrity"] == "ok"
        assert body["seal_version"] == 1
        assert body["seal_fingerprint"] == record.seal.digest[:16]

    def test_an_altered_record_still_prints_flagged(self, seed, client, auth_headers, record):
        _tamper(seed, record)
        resp = client.get(f"{PRINT}/records/{record.id}?document=record", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["integrity"] == "tampered"
