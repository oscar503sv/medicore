"""Convert domain entities to response schema dicts (no Pydantic dependency on domain)."""

from __future__ import annotations

from datetime import date, datetime

from medicore.application.use_cases.auth import MyProfileDTO
from medicore.application.use_cases.sessions import SessionInfoDTO
from medicore.application.use_cases.subscriptions import SubscriptionNotice, SubscriptionView
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.insurer import Insurer
from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.notification import Notification
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.plan import AddonPricing, Plan
from medicore.domain.entities.prescription import Prescription
from medicore.domain.entities.subscription_payment import SubscriptionPayment
from medicore.domain.entities.tenant import Tenant
from medicore.domain.entities.user import User
from medicore.domain.services.slot_resolver import Slot
from medicore.domain.value_objects.fee import Charge
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import LimitOverrides, PlanLimits
from medicore.infrastructure.persistence.mappers._json import (
    attachment_to_dict,
    diagnoses_to_list,
    exam_to_dict,
    note_to_dict,
    snapshot_to_dict,
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
        "jvpm": u.jvpm,
        "avatar_initials": u.avatar_initials,
        "last_seen_at": u.last_seen_at,
        "joined_at": u.joined_at,
        "permissions_customized": not u.permission_adjustments.is_empty,
    }


def ser_user_permissions(dto) -> dict:
    return {
        "user": ser_user(dto.user),
        "available": dto.available,
        "catalog": list(dto.catalog),
        "role_permissions": list(dto.role_permissions),
        "granted": list(dto.granted),
        "revoked": list(dto.revoked),
        "effective": list(dto.effective),
        "locked": list(dto.locked),
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
        "ip_address": e.ip_address,
        "user_agent": e.user_agent,
    }


def ser_global_audit_row(r) -> dict:
    return {
        "id": r.id,
        "timestamp": r.timestamp,
        "source_kind": r.source_kind,
        "actor_name": r.actor_name,
        "action": r.action,
        "clinic_name": r.clinic_name,
        "metadata": dict(r.metadata),
        "ip_address": r.ip_address,
        "user_agent": r.user_agent,
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
        "tenant_id": str(e.tenant_id) if e.tenant_id else None,
        "ip_address": e.ip_address,
        "user_agent": e.user_agent,
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
        "jvpm": p.jvpm,
        "permissions": list(p.permissions),
    }


def ser_session_info(s: SessionInfoDTO) -> dict:
    return {
        "id": str(s.id),
        "user_id": s.user_id,
        "user_name": s.user_name,
        "role": s.role,
        "ip_address": s.ip_address,
        "user_agent": s.user_agent,
        "created_at": s.created_at,
        "expires_at": s.expires_at,
        "current": s.current,
    }


def ser_notification(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "type": n.type,
        "data": dict(n.data),
        "read_at": n.read_at,
        "created_at": n.created_at,
    }


def ser_patient(
    p: Patient, *, next_visit: datetime | None = None, last_visit: datetime | None = None
) -> dict:
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
        "last_visit": last_visit,
    }


def ser_prescription(p: Prescription, prescriber_name: str | None = None) -> dict:
    return {
        "id": str(p.id),
        "patient_id": str(p.patient_id),
        "prescriber_id": str(p.prescriber_id),
        "prescriber_name": prescriber_name,
        "drug": p.drug,
        "dose": p.dose,
        "schedule": p.schedule,
        "start_date": p.start_date,
        "end_date": p.end_date,
        "duration_days": p.duration_days,
        "status": str(p.status),
        "record_id": str(p.record_id) if p.record_id else None,
        "created_at": p.created_at,
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
        **ser_charge(a.charge),
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def ser_charge(c: Charge) -> dict:
    return {"listed_fee": ser_money(c.listed), "fee": ser_money(c.charged), "fee_note": c.note}


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
        "note": note_to_dict(c.note),
        "missing": list(c.missing_for_sign()),
        "diagnoses": diagnoses_to_list(c.diagnoses),
        "draft_prescriptions": [
            {"drug": d.drug, "dose": d.dose, "schedule": d.schedule,
             "duration_days": d.duration_days}
            for d in c.draft_prescriptions
        ],
        "draft_applications": [
            {"drug": d.drug, "dose": d.dose, "route": str(d.route), "doses_total": d.doses_total,
             "interval_hours": d.interval_hours, "observation_minutes": d.observation_minutes,
             "instructions": d.instructions}
            for d in c.draft_applications
        ],
        "draft_procedures": [
            {"type_id": str(d.type_id), "type_name": d.type_name, "performer": str(d.performer),
             "requires_consent": d.requires_consent, "indication": d.indication,
             "follow_up_days": d.follow_up_days, "price": ser_money(d.price),
             "included": d.included}
            for d in c.draft_procedures
        ],
        "draft_exams": [exam_to_dict(e) for e in c.draft_exams],
        "attachments": [attachment_to_dict(a) for a in c.attachments],
        "completion_percent": c.compute_completion(),
        "last_saved_at": c.last_saved_at,
        "patient": ser_patient(patient) if patient else None,
        "appointment": ser_appointment(appointment) if appointment else None,
    }


def ser_record(
    r: MedicalRecord, *, patient_name: str | None = None, signed_by_name: str | None = None
) -> dict:
    return {
        "id": str(r.id),
        "tenant_id": str(r.tenant_id),
        "code": r.code,
        "patient_id": str(r.patient_id),
        "patient_name": patient_name,
        "signed_by_name": signed_by_name,
        "author_id": str(r.author_id),
        "type": str(r.type),
        "status": str(r.status),
        "encounter_at": r.encounter_at,
        "location_name": r.location_name,
        "insurer_name": r.insurer_name,
        "chief_complaint": r.chief_complaint,
        "note": note_to_dict(r.note),
        "vitals": vitals_to_dict(r.vitals),
        "diagnoses": diagnoses_to_list(r.diagnoses),
        "prescriptions": [snapshot_to_dict(p) for p in r.prescriptions],
        "vaccines": [vaccine_to_dict(v) for v in r.vaccines],
        "exams": [exam_to_dict(e) for e in r.exams],
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
            "min_advance_hours": av.rules.min_advance_hours,
            "allow_same_day": av.rules.allow_same_day,
        },
    }


def ser_tenant(t: Tenant, today: date | None = None) -> dict:
    """``today`` (the clinic's date) adds the subscription summary the console shows."""
    data = {
        "id": str(t.id),
        "legal_name": t.legal_name,
        "tax_id": t.tax_id,
        "slug": str(t.slug),
        "timezone": t.timezone,
        "status": str(t.status),
        "icd_version": str(t.icd_version),
        "print_settings": {
            "paper": str(t.print_settings.paper),
            "letterhead": t.print_settings.letterhead,
        },
        "locations": [
            {
                "id": str(loc.id),
                "name": loc.name,
                "address": loc.address,
                "phone": loc.phone,
                "is_primary": loc.is_primary,
            }
            for loc in t.locations
        ],
    }
    if today is not None:
        sub = t.subscription
        data["subscription"] = {
            "plan_code": sub.plan_code,
            "modules": sorted(str(m) for m in sub.modules),
            "period_end": sub.period_end,
            "is_trial": sub.is_trial,
            "status": str(sub.status(today)),
            "days_left": sub.days_left(today),
        }
    return data


# ── Subscriptions ─────────────────────────────────────────────────────────────


def ser_money(m: Money | None) -> str | None:
    return None if m is None else f"{m.amount:.2f}"


def _ser_limits(limits: PlanLimits | LimitOverrides) -> dict:
    return {
        "doctors": limits.doctors,
        "support_users": limits.support_users,
        "locations": limits.locations,
        "storage_gb": limits.storage_gb,
    }


def ser_plan(p: Plan) -> dict:
    return {
        "code": p.code,
        "name": p.name,
        "monthly_price": ser_money(p.monthly_price),
        "limits": _ser_limits(p.limits),
        "features": sorted(str(f) for f in p.features),
        "active": p.active,
        "sort_order": p.sort_order,
        "analytics_tier": str(p.analytics_tier),
    }


def ser_addon_pricing(a: AddonPricing) -> dict:
    return {
        "prices": {str(m): ser_money(price) for m, price in a.prices.items()},
        "bundle_price": ser_money(a.bundle_price),
    }


def ser_subscription(v: SubscriptionView) -> dict:
    sub = v.subscription
    return {
        "plan": ser_plan(v.plan),
        "modules": sorted(str(m) for m in sub.modules),
        "period_end": sub.period_end,
        "is_trial": sub.is_trial,
        "grace_days": sub.grace_days,
        "status": str(v.status),
        "today": v.today,
        "days_left": v.days_left,
        "limits": _ser_limits(v.limits),
        "limit_overrides": _ser_limits(sub.limit_overrides) if sub.limit_overrides else None,
        "price_override": ser_money(sub.price_override),
        "monthly_price": ser_money(v.monthly_price),
        "usage": {
            "doctors": v.usage.doctors,
            "support_users": v.usage.support_users,
            "locations": v.locations_used,
        },
        "addon_prices": ser_addon_pricing(v.addon_prices),
        "analytics_tier": str(v.analytics_tier),
    }


def ser_payment(p: SubscriptionPayment) -> dict:
    return {
        "id": str(p.id),
        "amount": ser_money(p.amount),
        "paid_on": p.paid_on,
        "months": p.months,
        "plan_code": p.plan_code,
        "period_end": p.period_end,
        "method": str(p.method),
        "reference": p.reference,
        "notes": p.notes,
        "recorded_at": p.recorded_at,
    }


def ser_subscription_notice(n: SubscriptionNotice) -> dict:
    return {
        "status": str(n.status),
        "is_trial": n.is_trial,
        "period_end": n.period_end,
        "grace_until": n.grace_until,
        "days_left": n.days_left,
    }


def _ser_clinic_business(r) -> dict:
    return {
        "tenant_id": r.tenant_id,
        "legal_name": r.legal_name,
        "slug": r.slug,
        "standing": r.standing,
        "plan_code": r.plan_code,
        "plan_name": r.plan_name,
        "modules": list(r.modules),
        "period_end": r.period_end,
        "days_left": r.days_left,
        "monthly": ser_money(r.monthly),
        "paying": r.paying,
        "usage": r.usage,
        "limits": _ser_limits(r.limits),
        "at_capacity": list(r.at_capacity),
        "last_activity": r.activity.last_activity,
        "active_users": r.activity.active_users,
        "signed_records": r.activity.signed_records,
    }


def ser_business_overview(dto) -> dict:
    return {
        "today": dto.today,
        "mrr": ser_money(dto.mrr),
        "unpriced": dto.unpriced,
        "collected_this_month": ser_money(dto.collected_this_month),
        "collected_last_month": ser_money(dto.collected_last_month),
        "by_standing": dto.by_standing,
        "by_plan": [
            {"code": p.code, "name": p.name, "clinics": p.clinics, "mrr": ser_money(p.mrr)}
            for p in dto.by_plan
        ],
        "by_module": dto.by_module,
        "active_clinics": dto.active_clinics,
        "inactive_clinics": dto.inactive_clinics,
        "at_capacity_clinics": dto.at_capacity_clinics,
        "weekly_signed": [{"week": w, "count": n} for w, n in dto.weekly_signed],
        "expiring": [_ser_clinic_business(r) for r in dto.expiring],
        "clinics": [_ser_clinic_business(r) for r in dto.clinics],
    }


# ── Platform monitoring ────────────────────────────────────────────────────────


def ser_system_status(dto, retention_days: int) -> dict:
    rt = dto.runtime
    return {
        "now": dto.now,
        "runtime": {
            "version": rt.version,
            "commit": rt.commit,
            "environment": rt.environment,
            "python": rt.python,
            "started_at": rt.started_at,
            "uptime_seconds": dto.uptime_seconds,
        },
        "database": {
            "version": dto.database.version,
            "size_bytes": dto.database.size_bytes,
            "revision": dto.database.revision,
            "latency_ms": dto.database_latency_ms,
            "connections": {
                "total": dto.connections.total,
                "active": dto.connections.active,
                "idle": dto.connections.idle,
                "idle_in_transaction": dto.connections.idle_in_transaction,
                "max_connections": dto.connections.max_connections,
            },
        },
        "largest_tables": [
            {"name": t.name, "size_bytes": t.size_bytes, "rows": t.rows}
            for t in dto.largest_tables
        ],
        "logins": {
            "failing_accounts": dto.logins.failing_accounts,
            "failed_attempts": dto.logins.failed_attempts,
            "lockouts_24h": dto.lockouts_24h,
            "locked": [
                {
                    "scope": lk.scope,
                    "clinic_slug": lk.clinic_slug,
                    "email": lk.email,
                    "failed_count": lk.failed_count,
                    "locked_until": lk.locked_until,
                }
                for lk in dto.logins.locked
            ],
            "console": [
                {
                    "admin_name": c.admin_name,
                    "action": c.action,
                    "at": c.at,
                    "ip_address": c.ip_address,
                    "user_agent": c.user_agent,
                }
                for c in dto.console_logins
            ],
        },
        "sessions": dto.sessions,
        "impersonations": [
            {
                "session_id": i.session_id,
                "admin_name": i.admin_name,
                "tenant_id": i.tenant_id,
                "clinic_name": i.clinic_name,
                "started_at": i.started_at,
                "expires_at": i.expires_at,
                "ip_address": i.ip_address,
            }
            for i in dto.impersonations
        ],
        "errors": {
            "last_24h": dto.errors_24h,
            "last_7d": dto.errors_7d,
            "retention_days": retention_days,
            "groups": [
                {
                    "method": g.method,
                    "route": g.route,
                    "error_type": g.error_type,
                    "location": g.location,
                    "count": g.count,
                    "last_at": g.last_at,
                    "first_at": g.first_at,
                    "first_commit": g.first_commit,
                    "last_commit": g.last_commit,
                }
                for g in dto.error_groups
            ],
            "daily": [{"day": d, "count": n} for d, n in dto.errors_daily],
        },
        "jobs": [_ser_job(j) for j in dto.jobs],
        "performance": _ser_performance(dto.performance),
    }


def _ser_performance(p) -> dict:
    return {
        "window_hours": p.window_hours,
        "requests": p.requests,
        "client_errors": p.client_errors,
        "server_errors": p.server_errors,
        "p50_ms": p.p50_ms,
        "p95_ms": p.p95_ms,
        "slowest": [
            {
                "method": r.method,
                "route": r.route,
                "count": r.count,
                "client_errors": r.client_errors,
                "server_errors": r.server_errors,
                "avg_ms": r.avg_ms,
                "p95_ms": r.p95_ms,
                "max_ms": r.max_ms,
            }
            for r in p.slowest
        ],
        "hourly": [
            {"hour": h.hour, "count": h.count, "server_errors": h.server_errors}
            for h in p.hourly
        ],
    }


def _ser_job(j) -> dict:
    s = j.summary
    return {
        "job": j.job,
        "state": j.state,
        "expected_every_hours": j.expected_every.total_seconds() / 3600
        if j.expected_every else None,
        "last_started_at": s.last_started_at if s else None,
        "last_finished_at": s.last_finished_at if s else None,
        "last_ok": s.last_ok if s else None,
        "last_detail": s.last_detail if s else None,
        "last_success_at": s.last_success_at if s else None,
    }


def ser_error_event(e) -> dict:
    return {
        "id": str(e.id),
        "occurred_at": e.occurred_at,
        "method": e.method,
        "route": e.route,
        "status": e.status,
        "error_type": e.error_type,
        "location": e.location,
        "commit": e.commit,
    }
