"""Email address normalization and validation."""

from __future__ import annotations

import re

from medicore.domain.shared.errors import InvalidValueObject

EMAIL_MAX_LENGTH = 254  # RFC 5321 path limit
_LOCAL_MAX = 64
# Deliberately lenient (no spaces, one @, a dotted domain): the real proof of an address
# is the user receiving mail on it, and strict parsers reject valid reserved TLDs like .test.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def is_valid_email(value: str) -> bool:
    email = normalize_email(value)
    if len(email) > EMAIL_MAX_LENGTH or not _EMAIL_RE.match(email):
        return False
    return len(email.split("@", 1)[0]) <= _LOCAL_MAX


def parse_email(value: str) -> str:
    """The normalized address, or ``InvalidValueObject`` (``user.invalid_email``)."""
    if not is_valid_email(value):
        raise InvalidValueObject("not a valid email address", code="user.invalid_email")
    return normalize_email(value)
