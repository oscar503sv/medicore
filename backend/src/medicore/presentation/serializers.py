"""Convert domain entities to response schema dicts (no Pydantic dependency on domain)."""

from __future__ import annotations

from datetime import datetime

from medicore.application.use_cases.auth import MyProfileDTO
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.insurer import Insurer
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
        "sex": str(u.sex) if u.sex else None,
        "specialty": u.specialty,
        "phone": u.phone,
        "avatar_initials": u.avatar_initials,
        "last_seen_at": u.last_seen_at,
        "joined_at": u.joined_at,
    }


def ser_platform_admin(a) -> dict:
    return {
        "id": str(a.id),
        "name": a.name,
        "email": a.email,
        "avatar_initials": a.avatar_initials,
        "last_seen_at": a.last_seen_at,
    }


def ser_tenant_stats(s) -> dict:
    return {
        "tenant_id": s.tenant_id,
        "legal_name": s.legal_name,
        "status": s.status,
        "patients": s.patients,
        "users": s.users,
        "appointments": s.appointments,
        "consultations": s.consultations,
        "records": s.records,
    }


def ser_global_stats(s) -> dict:
    return {
        "total_clinics": s.total_clinics,
        "active_clinics": s.active_clinics,
        "total_patients": s.total_patients,
        "total_users": s.total_users,
        "total_appointments": s.total_appointments,
        "by_clinic": [ser_tenant_stats(c) for c in s.by_clinic],
    }


def ser_audit(e) -> dict:
    return {
        "id": str(e.id),
        "tenant_id": str(e.tenant_id),
        "actor_id": str(e.actor_id),
        "action": e.action,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "metadata": dict(e.metadata),
        "timestamp": e.timestamp,
    }


def ser_platform_audit(e) -> dict:
    return {
        "id": str(e.id),
        "actor_id": str(e.actor_id),
        "action": e.action,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "metadata": dict(e.metadata),
        "timestamp": e.timestamp,
    }


def ser_my_profile(p: MyProfileDTO) -> dict:
    return {
        "name": p.name,
        "email": p.email,
        "role": str(p.role),
        "sex": str(p.sex) if p.sex else None,
        "specialty": p.specialty,
        "phone": p.phone,
        "bio": p.bio,
    }


def ser_patient(p: Patient, *, next_visit: datetime | None = None) -> dict:
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
        "next_visit": next_visit,
    }


def ser_insurer(i: Insurer) -> dict:
    return {
        "id": str(i.id),
        "tenant_id": str(i.tenant_id),
        "name": i.name,
        "phone": i.phone,
        "email": i.email,
        "address": i.address,
        "contact_person": i.contact_person,
        "notes": i.notes,
        "active": i.active,
        "created_at": i.created_at,
        "updated_at": i.updated_at,
    }


def ser_appointment(
    a: Appointment,
    *,
    patient_name: str | None = None,
    doctor_name: str | None = None,
    insurer_name: str | None = None,
) -> dict:
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
        "insurance_id": str(a.insurance_id) if a.insurance_id else None,
        "patient_name": patient_name,
        "doctor_name": doctor_name,
        "insurer_name": insurer_name,
        "created_by_id": str(a.created_by_id),
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def ser_slot(s: Slot) -> dict:
    return {"start": s.start, "end": s.end, "status": str(s.status)}


def ser_consultation(c: Consultation, uow=None) -> dict:
    """Serialize a consultation. When ``uow`` is provided, embed the (immutable for the
    consultation's life) patient and appointment context the live consultation screen needs
    for its header — patient summary, allergies, the booked reason and scheduled duration."""
    patient = uow.patients.get_by_id(c.patient_id) if uow else None
    appointment = uow.appointments.get_by_id(c.appointment_id) if uow else None
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
        "patient": ser_patient(patient) if patient else None,
        "appointment": ser_appointment(appointment) if appointment else None,
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
        "status": str(t.status),
        "icd_version": str(t.icd_version),
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
