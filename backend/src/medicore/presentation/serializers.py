"""Convert domain entities to response schema dicts (no Pydantic dependency on domain)."""

from __future__ import annotations

from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.tenant import Tenant
from medicore.domain.entities.user import User
from medicore.domain.services.slot_resolver import Slot
from medicore.infrastructure.persistence.mappers._json import (
    attachment_to_dict,
    diagnoses_to_list,
    snapshot_to_dict,
    soap_to_dict,
    time_range_to_dict,
    vaccine_to_dict,
    vitals_to_dict,
)


def ser_user(u: User) -> dict:
    return {
        "id": str(u.id),
        "tenant_id": str(u.tenant_id),
        "name": u.name,
        "email": u.email,
        "role": str(u.role),
        "status": str(u.status),
        "specialty": u.specialty,
        "avatar_initials": u.avatar_initials,
        "last_seen_at": u.last_seen_at,
        "joined_at": u.joined_at,
    }


def ser_patient(p: Patient) -> dict:
    return {
        "id": str(p.id),
        "tenant_id": str(p.tenant_id),
        "code": p.code,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "sex": str(p.sex),
        "date_of_birth": p.date_of_birth,
        "age": p.age(),
        "blood_type": str(p.blood_type) if p.blood_type else None,
        "insurance": p.insurance,
        "primary_doctor_id": str(p.primary_doctor_id) if p.primary_doctor_id else None,
        "status": str(p.status),
        "tags": p.tags,
        "allergies": p.allergies,
        "contact": {
            "phone": p.contact.phone,
            "email": p.contact.email,
            "address": p.contact.address,
            "emergency_contact_name": p.contact.emergency_contact_name,
            "emergency_contact_phone": p.contact.emergency_contact_phone,
        },
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def ser_appointment(a: Appointment) -> dict:
    return {
        "id": str(a.id),
        "tenant_id": str(a.tenant_id),
        "code": a.code,
        "patient_id": str(a.patient_id),
        "doctor_id": str(a.doctor_id),
        "location_id": str(a.location_id),
        "type": str(a.type),
        "status": str(a.status),
        "scheduled_start": a.scheduled_start,
        "scheduled_end": a.scheduled_end,
        "duration_minutes": a.duration_minutes,
        "reason": a.reason,
        "room": a.room,
        "created_by_id": str(a.created_by_id),
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def ser_slot(s: Slot) -> dict:
    return {"start": s.start, "end": s.end, "status": str(s.status)}


def ser_consultation(c: Consultation) -> dict:
    return {
        "id": str(c.id),
        "tenant_id": str(c.tenant_id),
        "appointment_id": str(c.appointment_id),
        "patient_id": str(c.patient_id),
        "doctor_id": str(c.doctor_id),
        "status": str(c.status),
        "started_at": c.started_at,
        "ended_at": c.ended_at,
        "vitals": vitals_to_dict(c.vitals),
        "soap": soap_to_dict(c.soap),
        "diagnoses": diagnoses_to_list(c.diagnoses),
        "draft_prescriptions": [
            {"drug": d.drug, "dose": d.dose, "schedule": d.schedule,
             "duration_days": d.duration_days}
            for d in c.draft_prescriptions
        ],
        "attachments": [attachment_to_dict(a) for a in c.attachments],
        "completion_percent": c.compute_completion(),
        "last_saved_at": c.last_saved_at,
    }


def ser_record(r: MedicalRecord) -> dict:
    return {
        "id": str(r.id),
        "tenant_id": str(r.tenant_id),
        "code": r.code,
        "patient_id": str(r.patient_id),
        "author_id": str(r.author_id),
        "type": str(r.type),
        "status": str(r.status),
        "encounter_at": r.encounter_at,
        "location_name": r.location_name,
        "chief_complaint": r.chief_complaint,
        "soap": soap_to_dict(r.soap),
        "vitals": vitals_to_dict(r.vitals),
        "diagnoses": diagnoses_to_list(r.diagnoses),
        "prescriptions": [snapshot_to_dict(p) for p in r.prescriptions],
        "vaccines": [vaccine_to_dict(v) for v in r.vaccines],
        "attachments": [attachment_to_dict(a) for a in r.attachments],
        "signed_at": r.signed_at,
        "signed_by_id": str(r.signed_by_id),
        "appointment_id": str(r.appointment_id) if r.appointment_id else None,
        "consultation_id": str(r.consultation_id) if r.consultation_id else None,
        "amends_record_id": str(r.amends_record_id) if r.amends_record_id else None,
    }


def ser_document(d: MedicalDocument) -> dict:
    return {
        "id": str(d.id),
        "tenant_id": str(d.tenant_id),
        "patient_id": str(d.patient_id),
        "file_name": d.file_name,
        "kind": str(d.kind),
        "mime_type": d.mime_type,
        "size_bytes": d.size_bytes,
        "storage_key": d.storage_key,
        "uploaded_by_id": str(d.uploaded_by_id),
        "uploaded_at": d.uploaded_at,
        "record_id": str(d.record_id) if d.record_id else None,
    }


def ser_availability(av: DoctorAvailability) -> dict:
    return {
        "id": str(av.id),
        "doctor_id": str(av.doctor_id),
        "weekly": [
            {
                "day_of_week": d.day_of_week,
                "enabled": d.enabled,
                "blocks": [time_range_to_dict(b) for b in d.blocks],
            }
            for d in av.weekly
        ],
        "exceptions": [
            {
                "id": str(ex.id),
                "date": ex.date.isoformat(),
                "kind": str(ex.kind),
                "reason": ex.reason,
                "blocks": [time_range_to_dict(b) for b in ex.blocks],
            }
            for ex in av.exceptions
        ],
        "rules": {
            "slot_minutes": av.rules.slot_minutes,
            "buffer_minutes": av.rules.buffer_minutes,
            "min_advance_hours": av.rules.min_advance_hours,
            "max_advance_days": av.rules.max_advance_days,
            "allow_same_day": av.rules.allow_same_day,
        },
    }


def ser_tenant(t: Tenant) -> dict:
    return {
        "id": str(t.id),
        "legal_name": t.legal_name,
        "tax_id": t.tax_id,
        "slug": str(t.slug),
        "timezone": t.timezone,
        "plan": t.plan,
        "seat_limit": t.seat_limit,
        "locations": [
            {
                "id": str(loc.id),
                "name": loc.name,
                "address": loc.address,
                "is_primary": loc.is_primary,
            }
            for loc in t.locations
        ],
    }
