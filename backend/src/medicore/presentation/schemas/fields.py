"""Reusable bounded field types for request bodies.

Limits mirror the database columns so an oversized value is a 422, never a 500.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from medicore.domain.value_objects.email import EMAIL_MAX_LENGTH, is_valid_email

SLUG_MAX_LENGTH = 63  # a DNS label: the slug is the clinic's subdomain
# Well above bcrypt's 72 bytes; the password policy explains the real limit (password.too_long).
PASSWORD_MAX_LENGTH = 256


def _email_format(value: str) -> str:
    # ValueError (not InvalidValueObject) so pydantic reports it as a 422 field error.
    if not is_valid_email(value):
        raise ValueError("not a valid email address")
    return value


# Login checks length only: the format is validated where an address is created.
LoginEmail = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, min_length=1, max_length=EMAIL_MAX_LENGTH
    ),
]
Email = Annotated[LoginEmail, AfterValidator(_email_format)]
SlugText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, min_length=1, max_length=SLUG_MAX_LENGTH
    ),
]
Password = Annotated[str, StringConstraints(min_length=1, max_length=PASSWORD_MAX_LENGTH)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
Specialty = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
Bio = Annotated[str, StringConstraints(max_length=2000)]
Jvpm = Annotated[str, StringConstraints(max_length=20)]
LegalName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
TaxId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
PlaceName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Address = Annotated[str, StringConstraints(max_length=500)]
