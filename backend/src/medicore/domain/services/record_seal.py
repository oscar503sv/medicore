"""The integrity seal of a signed record: a SHA-256 over its canonical form, chained to the
seal of the version it amends, so a stored record cannot change (or be swapped in a chain)
without the check noticing.

Honest limit: the digest has no secret key, so whoever can write the database can recompute
it. It detects accidents, buggy scripts and casual edits, and it makes the chain verifiable
by anyone; a keyed seal (HMAC) is a future version.

Version 1 is frozen: the migration that sealed the existing records uses :func:`seal_v1`, and
changing what it hashes would turn every stored record "tampered". A different form is a new
``canonical_vN``, a new ``CURRENT_SEAL_VERSION`` and a branch in :func:`compute_seal`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from medicore.domain.enums import SealStatus
from medicore.domain.value_objects.record_seal import RecordSeal

if TYPE_CHECKING:
    from medicore.domain.entities.medical_record import MedicalRecord

CURRENT_SEAL_VERSION = 1
_V1_PREFIX = b"medicore/medical-record/v1\x00"

_SEVERITY = {SealStatus.OK: 0, SealStatus.UNVERIFIABLE: 1, SealStatus.TAMPERED: 2}


def _instant(moment: datetime) -> str:
    # Only the in-memory tests use naive clocks (the database always hands back aware
    # values), and they mean UTC.
    aware = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
    return aware.isoformat(timespec="microseconds")


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _instant(value)
    if isinstance(value, tuple | list):
        return [_plain(v) for v in value]
    return str(getattr(value, "value", value))


def _id(identifier: Any) -> str | None:
    return None if identifier is None else str(identifier)


def _canonical_fields_v1(record: MedicalRecord, previous: RecordSeal | None) -> dict[str, Any]:
    note = record.note
    vitals = record.vitals
    return {
        "id": _id(record.id),
        "tenant_id": _id(record.tenant_id),
        "code": record.code,
        "patient_id": _id(record.patient_id),
        "author_id": _id(record.author_id),
        "type": _plain(record.type),
        "status": _plain(record.status),
        "encounter_at": _instant(record.encounter_at),
        "location_name": record.location_name,
        "insurer_name": record.insurer_name,
        "chief_complaint": record.chief_complaint,
        "note": {
            "template": note.template,
            "name": note.name,
            "sections": [
                {"key": s.key, "role": _plain(s.role), "title": s.title,
                 "required": s.required, "text": s.text}
                for s in note.sections
            ],
        },
        "vitals": {
            "blood_pressure": vitals.blood_pressure,
            "heart_rate": vitals.heart_rate,
            "spo2": vitals.spo2,
            "temperature": _plain(vitals.temperature),
            "weight": _plain(vitals.weight),
            "glucose": vitals.glucose,
            "height": _plain(vitals.height),
            "fetal_heart_rate": vitals.fetal_heart_rate,
        },
        "diagnoses": [{"code": d.code, "label": d.label} for d in record.diagnoses],
        "prescriptions": [
            {
                "drug": p.drug, "dose": p.dose, "schedule": p.schedule,
                "start_date": p.start_date.isoformat(),
                "end_date": p.end_date.isoformat() if p.end_date else None,
                "duration_days": p.duration_days,
            }
            for p in record.prescriptions
        ],
        "vaccines": [
            {"name": v.name, "lot": v.lot, "dose": v.dose, "site": v.site}
            for v in record.vaccines
        ],
        "exams": [
            {"name": e.name, "kind": _plain(e.kind), "notes": e.notes} for e in record.exams
        ],
        "attachments": [
            {"document_id": _id(a.document_id), "file_name": a.file_name,
             "kind": _plain(a.kind)}
            for a in record.attachments
        ],
        "signed_at": _instant(record.signed_at),
        "signed_by_id": _id(record.signed_by_id),
        "appointment_id": _id(record.appointment_id),
        "consultation_id": _id(record.consultation_id),
        "amends_record_id": _id(record.amends_record_id),
        "amendment_reason": record.amendment_reason,
        "previous_seal": previous.digest if previous else None,
    }


def canonical_v1(record: MedicalRecord, previous: RecordSeal | None) -> bytes:
    """The bytes version 1 hashes: an explicit field list (a new column never joins the seal
    by accident), sorted keys and no insignificant whitespace."""
    return json.dumps(
        _canonical_fields_v1(record, previous),
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def seal_v1(record: MedicalRecord, previous: RecordSeal | None) -> RecordSeal:
    digest = hashlib.sha256(_V1_PREFIX + canonical_v1(record, previous)).hexdigest()
    return RecordSeal(1, digest)


def compute_seal(record: MedicalRecord, previous: RecordSeal | None) -> RecordSeal:
    """The seal a record gets today. ``previous`` is the seal of the version it amends."""
    return seal_v1(record, previous)


def _check(
    record: MedicalRecord, previous: MedicalRecord | None
) -> SealStatus:
    if record.seal is None:
        return SealStatus.TAMPERED
    if previous is not None and record.amends_record_id != previous.id:
        return SealStatus.TAMPERED
    if previous is None and record.amends_record_id is not None:
        return SealStatus.TAMPERED
    if record.seal.version != 1:
        return SealStatus.UNVERIFIABLE
    # Each version is checked against the seal its predecessor stores, so an altered record
    # is reported where it happened; callers that need "this version and what it rests on"
    # take the worst status from the root.
    expected = seal_v1(record, previous.seal if previous else None)
    return SealStatus.OK if expected.digest == record.seal.digest else SealStatus.TAMPERED


def verify_chain(chain: Sequence[MedicalRecord]) -> tuple[SealStatus, ...]:
    """The status of every version of a record, oldest first."""
    return tuple(
        _check(record, chain[i - 1] if i else None) for i, record in enumerate(chain)
    )


def worst(statuses: Sequence[SealStatus]) -> SealStatus:
    return max(statuses, key=_SEVERITY.__getitem__, default=SealStatus.OK)
