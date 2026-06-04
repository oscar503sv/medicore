"""Audit network-context propagation (Phase 1)."""

from __future__ import annotations

from datetime import UTC, datetime

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.domain.enums import Role
from medicore.domain.shared.identifiers import TenantId, UserId


def test_audit_entry_captures_ip_and_user_agent():
    actor = ActorContext(
        user_id=UserId.new(),
        tenant_id=TenantId.new(),
        role=Role.ADMIN,
        ip_address="203.0.113.7",
        user_agent="Mozilla/5.0",
    )
    entry = audit_entry(actor, datetime.now(UTC), "record.signed", "MedicalRecord", "r1")
    assert entry.ip_address == "203.0.113.7"
    assert entry.user_agent == "Mozilla/5.0"


def test_audit_entry_network_context_defaults_to_none():
    actor = ActorContext(user_id=UserId.new(), tenant_id=TenantId.new(), role=Role.ADMIN)
    entry = audit_entry(actor, datetime.now(UTC), "patient.viewed", "Patient", "p1")
    assert entry.ip_address is None
    assert entry.user_agent is None
