"""Login throttling policy: attempt counting with temporary lockout.

Pure code shared by the SQL and in-memory throttle repositories so the thresholds live in
one place and stay unit-testable without a database. Three counters guard every sign-in
(see ``login_gate``): per IP, per account and IP, and per account.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timedelta

WINDOW_MINUTES = 15  # an attempt older than this restarts the count
WINDOW = timedelta(minutes=WINDOW_MINUTES)
KNOWN_IP_TTL = timedelta(days=30)  # how long a successful sign-in vouches for its IP

UNKNOWN_IP = "unknown"
IPV6_BUCKET_PREFIX = 64  # one customer line is usually handed a whole /64


@dataclass(frozen=True, slots=True)
class ThrottlePolicy:
    max_attempts: int
    max_lockout_minutes: int
    backoff: bool  # exponential from 1 min (per account and IP) vs a flat lockout

    def lockout_until(self, count: int, now: datetime) -> datetime | None:
        """Lockout deadline after the Nth attempt in the window (None below the threshold).

        Applied to existing and non-existing accounts alike so the response does not
        reveal whether an account exists.
        """
        if count < self.max_attempts:
            return None
        if not self.backoff:
            return now + timedelta(minutes=self.max_lockout_minutes)
        minutes = min(2 ** (count - self.max_attempts), self.max_lockout_minutes)
        return now + timedelta(minutes=minutes)


ACCOUNT_IP_POLICY = ThrottlePolicy(max_attempts=5, max_lockout_minutes=15, backoff=True)
ACCOUNT_POLICY = ThrottlePolicy(max_attempts=20, max_lockout_minutes=15, backoff=False)
IP_POLICY = ThrottlePolicy(max_attempts=30, max_lockout_minutes=15, backoff=False)
MFA_POLICY = ACCOUNT_IP_POLICY
PASSWORD_CHECK_POLICY = ACCOUNT_IP_POLICY


@dataclass(frozen=True, slots=True)
class Reservation:
    allowed: bool
    # Rejected: the active lock. Allowed: the lock this very attempt engaged, if any.
    locked_until: datetime | None
    last_success_at: datetime | None = None

    @property
    def engaged(self) -> bool:
        return self.allowed and self.locked_until is not None


def tenant_login_identifier(slug: str, email: str) -> str:
    return f"tenant:{slug.strip().lower()}:{email.strip().lower()}"


def platform_login_identifier(email: str) -> str:
    return f"platform:{email.strip().lower()}"


def platform_mfa_identifier(admin_id: str) -> str:
    # By admin id, not email: the second factor is attacked after the password is known.
    return f"platform-mfa:{admin_id}"


def password_change_identifier(user_id: str) -> str:
    # By account id, not by IP: whoever is guessing the current password already holds a
    # session of that account.
    return f"pwchange:{user_id}"


def ip_bucket_key(ip: str | None) -> str:
    """The unit an address is throttled as: IPv4 as is, IPv6 by its /64, IPv4-mapped IPv6 as
    the IPv4 it wraps; a missing or unparseable address shares one "unknown" bucket."""
    if not ip:
        return UNKNOWN_IP
    try:
        address = ipaddress.ip_address(ip.strip())
    except ValueError:
        return UNKNOWN_IP
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/{IPV6_BUCKET_PREFIX}", strict=False))
    return str(address)


def ip_identifier(ip: str | None) -> str:
    return f"ip:{ip_bucket_key(ip)}"


def account_ip_identifier(account: str, ip: str | None) -> str:
    return f"{account}|{ip_bucket_key(ip)}"


def parse_identifier(identifier: str) -> tuple[str, str | None, str, str | None]:
    """(scope, clinic_slug, email, ip) of a stored identifier, for monitoring.

    IP rows are ("ip", None, "", key); account and IP pairs carry the key in ``ip``.
    """
    if identifier.startswith("ip:"):
        return "ip", None, "", identifier.removeprefix("ip:")
    account, separator, ip = identifier.rpartition("|")
    if not separator:
        account, ip = identifier, None
    scope, _, rest = account.partition(":")
    slug, email = rest.split(":", 1) if scope == "tenant" and ":" in rest else (None, rest)
    return scope, slug, email, ip
