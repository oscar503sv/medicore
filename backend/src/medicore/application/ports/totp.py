"""TOTP port — time-based one-time passwords (RFC 6238) for the second login factor."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Totp(Protocol):
    def new_secret(self) -> str:
        """A fresh random shared secret, base32 (the form authenticator apps import)."""
        ...

    def matching_step(self, secret: str, code: str, at: datetime) -> int | None:
        """Time step whose code equals ``code`` within the accepted clock-drift window, or
        None. The step lets the caller reject a code that was already used."""
        ...

    def provisioning_uri(self, secret: str, account: str, issuer: str) -> str:
        """``otpauth://`` URI that authenticator apps understand."""
        ...
