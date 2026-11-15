"""Checking the integrity seal of a record's chain of versions, and recording a failure."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import SealStatus
from medicore.domain.services.record_seal import worst

INTEGRITY_FAILED_ACTION = "record.integrity_failed"


def upto(statuses: Sequence[SealStatus], index: int) -> SealStatus:
    """The status of the version at ``index`` taken together with every version it rests on:
    a record whose ancestor was altered cannot be trusted either."""
    return worst(statuses[: index + 1])


def integrity_failure(
    actor: ActorContext, when: datetime, chain: Sequence[MedicalRecord],
    statuses: Sequence[SealStatus], at: MedicalRecord, label: str | None,
) -> AuditLog | None:
    """The audit entry for a chain that does not verify, or None when it does. It names the
    failing versions by id only: the audit log is read by people who may not read content."""
    failed = [str(r.id) for r, s in zip(chain, statuses, strict=True) if s != SealStatus.OK]
    if not failed:
        return None
    return audit_entry(
        actor, when, INTEGRITY_FAILED_ACTION, "MedicalRecord", str(at.id),
        versions=failed, subject=label,
    )
