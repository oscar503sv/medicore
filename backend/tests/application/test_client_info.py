"""Bounds on client-supplied network details."""

from __future__ import annotations

from medicore.application.common.client_info import (
    IP_ADDRESS_MAX_LENGTH,
    USER_AGENT_MAX_LENGTH,
    clip_ip,
    clip_user_agent,
)


def test_user_agent_is_clipped_and_blank_becomes_none():
    assert clip_user_agent("x" * 5000) == "x" * USER_AGENT_MAX_LENGTH
    assert clip_user_agent("  Firefox/159.0 ") == "Firefox/159.0"
    assert clip_user_agent("   ") is None
    assert clip_user_agent(None) is None


def test_ip_is_clipped_and_empty_becomes_none():
    assert clip_ip("203.0.113.7") == "203.0.113.7"
    assert clip_ip("1" * 100) == "1" * IP_ADDRESS_MAX_LENGTH
    assert clip_ip("") is None
    assert clip_ip(None) is None
