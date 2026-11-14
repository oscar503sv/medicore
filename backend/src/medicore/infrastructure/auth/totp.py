"""RFC 6238 TOTP (HMAC-SHA1) with the standard library only."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

_SECRET_BYTES = 20  # 160 bits, the SHA-1 block recommended by RFC 4226


class Rfc6238Totp:
    def __init__(self, digits: int = 6, period: int = 30, window: int = 1) -> None:
        self._digits = digits
        self._period = period
        self._window = window

    def new_secret(self) -> str:
        return base64.b32encode(secrets.token_bytes(_SECRET_BYTES)).decode().rstrip("=")

    def step_at(self, at: datetime) -> int:
        # Naive datetimes (test clocks) are taken as UTC.
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        return int(at.timestamp() // self._period)

    def code_at(self, secret: str, at: datetime) -> str:
        return self._code(secret, self.step_at(at))

    def matching_step(self, secret: str, code: str, at: datetime) -> int | None:
        candidate = code.replace(" ", "")
        if len(candidate) != self._digits or not (candidate.isascii() and candidate.isdigit()):
            return None
        current = self.step_at(at)
        matched: int | None = None
        # No early exit: the loop takes the same time wherever the code falls.
        for step in range(current - self._window, current + self._window + 1):
            if hmac.compare_digest(self._code(secret, step), candidate):
                matched = step
        return matched

    def provisioning_uri(self, secret: str, account: str, issuer: str) -> str:
        label = f"{quote(issuer, safe='')}:{quote(account, safe='')}"
        query = urlencode(
            {
                "secret": secret,
                "issuer": issuer,
                "algorithm": "SHA1",
                "digits": self._digits,
                "period": self._period,
            },
            quote_via=quote,
        )
        return f"otpauth://totp/{label}?{query}"

    def _code(self, secret: str, step: int) -> str:
        padded = secret.upper() + "=" * (-len(secret) % 8)
        key = base64.b32decode(padded)
        digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        return str(value % 10**self._digits).zfill(self._digits)
