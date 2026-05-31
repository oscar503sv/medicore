"""JSON serialization/deserialization helpers for complex value objects stored as JSONB."""

from __future__ import annotations

from datetime import time
from decimal import Decimal

from medicore.domain.entities.medical_document import AttachmentRef
from medicore.domain.entities.medical_record import VaccineAdministration
from medicore.domain.entities.prescription import PrescriptionDraft, PrescriptionSnapshot
from medicore.domain.enums import DocumentKind
from medicore.domain.shared.identifiers import DocumentId
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.time_range import TimeRange
from medicore.domain.value_objects.vitals import Vitals


# ── Vitals ────────────────────────────────────────────────────────────────────
def vitals_to_dict(v: Vitals) -> dict:
    return {
        "blood_pressure": v.blood_pressure,
        "heart_rate": v.heart_rate,
        "spo2": v.spo2,
        "temperature": str(v.temperature) if v.temperature is not None else None,
        "weight": str(v.weight) if v.weight is not None else None,
        "glucose": v.glucose,
        "height": str(v.height) if v.height is not None else None,
        "fetal_heart_rate": v.fetal_heart_rate,
    }


def dict_to_vitals(d: dict) -> Vitals:
    if not d:
        return Vitals()
    return Vitals(
        blood_pressure=d.get("blood_pressure"),
        heart_rate=d.get("heart_rate"),
        spo2=d.get("spo2"),
        temperature=Decimal(d["temperature"]) if d.get("temperature") else None,
        weight=Decimal(d["weight"]) if d.get("weight") else None,
        glucose=d.get("glucose"),
        height=Decimal(d["height"]) if d.get("height") else None,
        fetal_heart_rate=d.get("fetal_heart_rate"),
    )


# ── SoapNote ──────────────────────────────────────────────────────────────────
def soap_to_dict(s: SoapNote) -> dict:
    return {
        "subjective": s.subjective,
        "objective": s.objective,
        "assessment": s.assessment,
        "plan": s.plan,
    }


def dict_to_soap(d: dict) -> SoapNote:
    if not d:
        return SoapNote()
    return SoapNote(
        subjective=d.get("subjective", ""),
        objective=d.get("objective", ""),
        assessment=d.get("assessment", ""),
        plan=d.get("plan", ""),
    )


# ── IcdCode list ──────────────────────────────────────────────────────────────
def diagnoses_to_list(diagnoses: tuple[IcdCode, ...] | list[IcdCode]) -> list[dict]:
    return [{"code": d.code, "label": d.label} for d in diagnoses]


def dict_to_diagnoses(lst: list[dict]) -> tuple[IcdCode, ...]:
    return tuple(IcdCode(d["code"], d["label"]) for d in lst)


# ── TimeRange ─────────────────────────────────────────────────────────────────
def time_range_to_dict(tr: TimeRange) -> dict:
    return {"start": tr.start.strftime("%H:%M"), "end": tr.end.strftime("%H:%M")}


def dict_to_time_range(d: dict) -> TimeRange:
    return TimeRange(
        time(*map(int, d["start"].split(":"))),
        time(*map(int, d["end"].split(":"))),
    )


# ── PrescriptionDraft ─────────────────────────────────────────────────────────
def draft_to_dict(draft: PrescriptionDraft) -> dict:
    return {
        "drug": draft.drug,
        "dose": draft.dose,
        "schedule": draft.schedule,
        "duration_days": draft.duration_days,
        "start_date": draft.start_date.isoformat() if draft.start_date else None,
        "end_date": draft.end_date.isoformat() if draft.end_date else None,
    }


def dict_to_draft(d: dict) -> PrescriptionDraft:
    from datetime import date

    return PrescriptionDraft(
        drug=d["drug"],
        dose=d["dose"],
        schedule=d["schedule"],
        duration_days=d.get("duration_days"),
        start_date=date.fromisoformat(d["start_date"]) if d.get("start_date") else None,
        end_date=date.fromisoformat(d["end_date"]) if d.get("end_date") else None,
    )


# ── PrescriptionSnapshot ──────────────────────────────────────────────────────
def snapshot_to_dict(s: PrescriptionSnapshot) -> dict:
    return {
        "drug": s.drug,
        "dose": s.dose,
        "schedule": s.schedule,
        "start_date": s.start_date.isoformat(),
        "end_date": s.end_date.isoformat() if s.end_date else None,
        "duration_days": s.duration_days,
    }


def dict_to_snapshot(d: dict) -> PrescriptionSnapshot:
    from datetime import date

    return PrescriptionSnapshot(
        drug=d["drug"],
        dose=d["dose"],
        schedule=d["schedule"],
        start_date=date.fromisoformat(d["start_date"]),
        end_date=date.fromisoformat(d["end_date"]) if d.get("end_date") else None,
        duration_days=d.get("duration_days"),
    )


# ── AttachmentRef ─────────────────────────────────────────────────────────────
def attachment_to_dict(ref: AttachmentRef) -> dict:
    return {
        "document_id": str(ref.document_id),
        "file_name": ref.file_name,
        "kind": str(ref.kind),
    }


def dict_to_attachment(d: dict) -> AttachmentRef:
    return AttachmentRef(
        document_id=DocumentId.parse(d["document_id"]),
        file_name=d["file_name"],
        kind=DocumentKind(d["kind"]),
    )


# ── VaccineAdministration ─────────────────────────────────────────────────────
def vaccine_to_dict(v: VaccineAdministration) -> dict:
    return {"name": v.name, "lot": v.lot, "dose": v.dose, "site": v.site}


def dict_to_vaccine(d: dict) -> VaccineAdministration:
    return VaccineAdministration(name=d["name"], lot=d["lot"], dose=d["dose"], site=d["site"])
