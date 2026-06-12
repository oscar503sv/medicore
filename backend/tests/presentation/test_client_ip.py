"""Unit tests for trusted-proxy X-Forwarded-For resolution."""

from __future__ import annotations

import pytest

from medicore.infrastructure.config import Settings, _parse_networks
from medicore.presentation.client_ip import resolve_client_ip

LOOPBACK = _parse_networks("127.0.0.1")
PRIVATE = _parse_networks("127.0.0.1, 10.0.0.0/8")
NONE = _parse_networks("")


def test_no_trusted_proxies_ignores_the_header():
    # The header is attacker-controlled; without a proxy in front, the peer IS the client.
    assert resolve_client_ip("203.0.113.7", "6.6.6.6", NONE) == "203.0.113.7"


def test_untrusted_peer_with_spoofed_header_yields_the_peer():
    assert resolve_client_ip("203.0.113.7", "6.6.6.6", LOOPBACK) == "203.0.113.7"


def test_trusted_peer_takes_rightmost_untrusted_hop():
    # The client sent "6.6.6.6" and the proxy appended the real address: the real one wins.
    assert resolve_client_ip("127.0.0.1", "6.6.6.6, 203.0.113.7", LOOPBACK) == "203.0.113.7"


def test_chain_through_several_trusted_proxies():
    # edge proxy (10.x) and local proxy are both ours → skip them right-to-left.
    assert (
        resolve_client_ip("127.0.0.1", "6.6.6.6, 203.0.113.7, 10.0.0.5", PRIVATE)
        == "203.0.113.7"
    )


def test_fully_trusted_chain_yields_leftmost_hop():
    assert resolve_client_ip("127.0.0.1", "10.0.0.9, 10.0.0.5", PRIVATE) == "10.0.0.9"


def test_no_header_behind_trusted_proxy_yields_peer():
    assert resolve_client_ip("127.0.0.1", None, LOOPBACK) == "127.0.0.1"
    assert resolve_client_ip("127.0.0.1", "  ", LOOPBACK) == "127.0.0.1"


def test_malformed_hop_falls_back_to_peer():
    assert resolve_client_ip("127.0.0.1", "garbage, 203.0.113.7", LOOPBACK) == "203.0.113.7"
    assert resolve_client_ip("127.0.0.1", "203.0.113.7, garbage", LOOPBACK) == "127.0.0.1"


def test_ports_and_ipv6_brackets_are_normalized():
    assert resolve_client_ip("127.0.0.1", "203.0.113.7:5678", LOOPBACK) == "203.0.113.7"
    assert resolve_client_ip("127.0.0.1", "[2001:db8::1]:443", LOOPBACK) == "2001:db8::1"


def test_unparseable_peer_is_returned_as_is():
    # Starlette's TestClient reports "testclient" as the peer; pass it through untouched.
    assert resolve_client_ip("testclient", "6.6.6.6", LOOPBACK) == "testclient"


def test_none_peer_stays_none():
    assert resolve_client_ip(None, "6.6.6.6", LOOPBACK) is None


def test_settings_parse_and_reject_trusted_proxies():
    networks = _parse_networks("127.0.0.1, 10.0.0.0/8")
    assert len(networks) == 2
    with pytest.raises(ValueError, match="invalid IP or CIDR"):
        Settings(trusted_proxies="not-an-ip")
