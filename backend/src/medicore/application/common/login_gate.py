"""Admission of a sign-in attempt, decided before any password work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from medicore.application.common.errors import TooManyLoginAttempts
from medicore.application.common.login_throttle import (
    ACCOUNT_IP_POLICY,
    ACCOUNT_POLICY,
    IP_POLICY,
    KNOWN_IP_TTL,
    account_ip_identifier,
    ip_identifier,
)
from medicore.application.ports.unit_of_work import LoginThrottleRepository


@dataclass(frozen=True, slots=True)
class LoginAdmission:
    ip_id: str
    pair_id: str
    account_id: str
    account_counted: bool
    lock_engaged: bool  # a per-account lock engaged with this attempt: audit it if it fails


class LoginGate:
    """Admits a sign-in attempt before any password work (per IP, per account and IP,
    per account), so neither spraying nor parallel requests get past the thresholds."""

    def __init__(self, throttle: LoginThrottleRepository, now: datetime) -> None:
        self._throttle = throttle
        self._now = now

    def admit(self, account: str, ip: str | None) -> LoginAdmission:
        """Count the attempt on all three counters or raise ``TooManyLoginAttempts``.

        The IP is judged first and without looking at the account, so a blocked address
        gets the same answer whether or not the account exists. The account-wide cap does
        not apply to an IP that signed in successfully to that account recently: an
        attacker spreading guesses over many addresses must not lock the owner out of
        their usual place.
        """
        ip_id = ip_identifier(ip)
        pair_id = account_ip_identifier(account, ip)
        by_ip = self._throttle.reserve(ip_id, IP_POLICY, self._now)
        if not by_ip.allowed:
            raise TooManyLoginAttempts(by_ip.locked_until, self._now)
        by_pair = self._throttle.reserve(pair_id, ACCOUNT_IP_POLICY, self._now)
        if not by_pair.allowed:
            raise TooManyLoginAttempts(by_pair.locked_until, self._now)
        by_account = self._throttle.reserve(account, ACCOUNT_POLICY, self._now)
        if not by_account.allowed and not self._is_known(by_pair.last_success_at):
            raise TooManyLoginAttempts(by_account.locked_until, self._now)
        return LoginAdmission(
            ip_id=ip_id,
            pair_id=pair_id,
            account_id=account,
            account_counted=by_account.allowed,
            lock_engaged=by_pair.engaged or by_account.engaged,
        )

    def succeeded(self, admission: LoginAdmission) -> None:
        """Clear the account-and-IP failures and remember the success; the IP and account
        budgets only get this attempt back (a valid login must not wipe an attacker's
        history behind a shared address, nor spend the budget of a busy office)."""
        self._throttle.reset(admission.pair_id, self._now)
        self._throttle.refund(admission.ip_id, IP_POLICY)
        if admission.account_counted:
            self._throttle.refund(admission.account_id, ACCOUNT_POLICY)
        self._throttle.purge_stale(self._now)

    def _is_known(self, last_success_at: datetime | None) -> bool:
        return last_success_at is not None and last_success_at >= self._now - KNOWN_IP_TTL
