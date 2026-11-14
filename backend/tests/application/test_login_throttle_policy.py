"""Pure rules of the sign-in throttle: lockout schedule, IP buckets, identifier parsing."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from medicore.application.common.login_throttle import (
    ACCOUNT_IP_POLICY,
    ACCOUNT_POLICY,
    IP_POLICY,
    account_ip_identifier,
    ip_bucket_key,
    ip_identifier,
    parse_identifier,
    tenant_login_identifier,
)

NOW = datetime(2026, 6, 11, 9, 0)


@pytest.mark.parametrize(
    ("count", "minutes"),
    [(5, 1), (6, 2), (7, 4), (8, 8), (9, 15), (12, 15)],
)
def test_pair_lockout_backs_off_up_to_the_cap(count, minutes):
    assert ACCOUNT_IP_POLICY.lockout_until(count, NOW) == NOW + timedelta(minutes=minutes)


def test_below_the_threshold_nothing_locks():
    assert ACCOUNT_IP_POLICY.lockout_until(4, NOW) is None
    assert ACCOUNT_POLICY.lockout_until(19, NOW) is None
    assert IP_POLICY.lockout_until(29, NOW) is None


@pytest.mark.parametrize(("policy", "threshold"), [(ACCOUNT_POLICY, 20), (IP_POLICY, 30)])
def test_flat_lockout_does_not_grow(policy, threshold):
    assert policy.lockout_until(threshold, NOW) == NOW + timedelta(minutes=15)
    assert policy.lockout_until(threshold + 10, NOW) == NOW + timedelta(minutes=15)


def test_ipv4_is_its_own_bucket():
    assert ip_bucket_key("203.0.113.7") == "203.0.113.7"


def test_ipv6_addresses_of_one_prefix_share_a_bucket():
    a = ip_bucket_key("2001:db8:1:2:aaaa:bbbb:cccc:dddd")
    b = ip_bucket_key("2001:db8:1:2::1")
    assert a == b
    assert a != ip_bucket_key("2001:db8:1:3::1")


def test_ipv4_mapped_ipv6_is_the_ipv4():
    assert ip_bucket_key("::ffff:203.0.113.7") == "203.0.113.7"


@pytest.mark.parametrize("ip", [None, "", "testclient", "not-an-ip"])
def test_missing_or_invalid_address_shares_one_bucket(ip):
    assert ip_bucket_key(ip) == "unknown"


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("ip:198.51.100.1", ("ip", None, "", "198.51.100.1")),
        ("ip:2001:db8:1:2::/64", ("ip", None, "", "2001:db8:1:2::/64")),
        ("tenant:clinica:ana@x.test", ("tenant", "clinica", "ana@x.test", None)),
        ("platform:root@x.test", ("platform", None, "root@x.test", None)),
        (
            "tenant:clinica:ana@x.test|198.51.100.1",
            ("tenant", "clinica", "ana@x.test", "198.51.100.1"),
        ),
        ("platform:root@x.test|unknown", ("platform", None, "root@x.test", "unknown")),
        (
            "tenant:clinica:a|b@x.test|198.51.100.1",
            ("tenant", "clinica", "a|b@x.test", "198.51.100.1"),
        ),
    ],
)
def test_parse_identifier(identifier, expected):
    assert parse_identifier(identifier) == expected


def test_identifiers_round_trip_through_the_parser():
    account = tenant_login_identifier("Clinica", "Ana@X.test")
    assert parse_identifier(account_ip_identifier(account, "203.0.113.7")) == (
        "tenant", "clinica", "ana@x.test", "203.0.113.7",
    )
    assert parse_identifier(ip_identifier("203.0.113.7"))[0] == "ip"
