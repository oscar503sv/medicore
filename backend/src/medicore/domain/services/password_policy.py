"""Password policy: what makes a password acceptable for a Medicore account.

Follows current guidance (NIST SP 800-63B) adapted to a clinical system: length matters
most, so a long minimum; a light composition rule (letters plus a digit or symbol); a
blocklist of common and product-related passwords; nothing derived from the person's own
name, email or clinic. No periodic expiry — it pushes people to weaker passwords — and the
brute-force side is covered by the login lockout.

Pure rules over the plain text; the use cases call it before hashing.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from medicore.domain.shared.errors import InvalidValueObject

MIN_LENGTH = 10
# bcrypt only looks at the first 72 bytes: anything longer would be silently truncated.
MAX_BYTES = 72
MIN_DISTINCT = 4
# Personal words shorter than this are too generic to forbid ("ana", "dr").
_MIN_PERSONAL = 4

# Common passwords and obvious picks for a clinic, compared after normalizing (lowercase,
# no accents) and ignoring a trailing run of digits/symbols ("Clinica2024!" → "clinica").
_COMMON = frozenset({
    "password", "passw0rd", "contrasena", "contrasenia", "clave", "secreto", "qwerty",
    "qwertyuiop", "asdfghjkl", "zxcvbnm", "abc", "abcdef", "abcdefgh", "abcdefghij",
    "iloveyou", "teamo", "admin", "administrador", "administrator", "root", "usuario",
    "user", "welcome", "bienvenido", "bienvenida", "letmein", "monkey", "dragon",
    "football", "futbol", "baseball", "master", "sunshine", "princess", "princesa",
    "superman", "batman", "trustno1", "changeme", "cambiame", "temporal", "default",
    "test", "prueba", "demo", "medicore", "clinica", "clinic", "hospital", "doctor",
    "doctora", "medico", "medica", "enfermera", "enfermero", "recepcion", "paciente",
    "salud", "consulta", "elsalvador", "salvador", "sansalvador", "guanaco", "cuscatlan",
    "mexico", "guatemala", "honduras", "pupusa", "pupusas", "jesus", "dios", "amor",
    "familia", "mama", "papa", "hola", "holamundo",
})


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _core(normalized: str) -> str:
    """The word part of a password: trailing digits/symbols removed ("clinica2024!")."""
    end = len(normalized)
    while end > 0 and not normalized[end - 1].isalpha():
        end -= 1
    return normalized[:end]


def _personal_words(personal: Iterable[str | None]) -> set[str]:
    words: set[str] = set()
    for item in personal:
        if not item:
            continue
        text = _normalize(item).split("@")[0]
        for sep in ".-_+":
            text = text.replace(sep, " ")
        words.update(w for w in text.split() if len(w) >= _MIN_PERSONAL)
    return words


def ensure_acceptable(password: str, *, personal: Iterable[str | None] = ()) -> None:
    """Raise ``InvalidValueObject`` (code ``password.*``) if the password breaks the policy.

    ``personal`` holds what an attacker would try first: the person's name and email, the
    clinic's slug or name.
    """
    password = password or ""
    if len(password) < MIN_LENGTH:
        raise InvalidValueObject(
            f"password must be at least {MIN_LENGTH} characters",
            code="password.too_short", min=MIN_LENGTH,
        )
    if len(password.encode("utf-8")) > MAX_BYTES:
        raise InvalidValueObject(
            f"password must be at most {MAX_BYTES} bytes", code="password.too_long", max=MAX_BYTES
        )
    has_letter = any(ch.isalpha() for ch in password)
    has_other = any(not ch.isalpha() and not ch.isspace() for ch in password)
    if not (has_letter and has_other) or len(set(password)) < MIN_DISTINCT:
        raise InvalidValueObject(
            "password needs letters plus a number or symbol, and some variety",
            code="password.too_simple",
        )
    normalized = _normalize(password)
    compact = "".join(ch for ch in normalized if ch.isalnum())
    candidates = {normalized, compact, _core(normalized), _core(compact)}
    if candidates & _COMMON:
        raise InvalidValueObject("password is too common", code="password.common")
    if any(word in normalized for word in _personal_words(personal)):
        raise InvalidValueObject(
            "password must not contain your name, email or clinic",
            code="password.personal",
        )
