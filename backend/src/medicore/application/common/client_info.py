"""Bounds for client-supplied network details stored in sessions and audit rows."""

from __future__ import annotations

USER_AGENT_MAX_LENGTH = 400  # sessions.user_agent is String(400)
IP_ADDRESS_MAX_LENGTH = 45  # audit_logs.ip_address; longest textual IPv6 (IPv4-mapped)


def clip_user_agent(value: str | None) -> str | None:
    return (value or "").strip()[:USER_AGENT_MAX_LENGTH] or None


def clip_ip(value: str | None) -> str | None:
    return value[:IP_ADDRESS_MAX_LENGTH] if value else None
