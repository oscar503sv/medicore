"""Text helpers shared by search implementations."""

from __future__ import annotations

# Accent folding without the `unaccent` extension: SQL repositories apply the same table with
# translate(), so "alvarez" finds "Álvarez" and vice versa.
ACCENTED = "áàäâãéèëêíìïîóòöôõúùüûñç"
PLAIN = "aaaaaeeeeiiiiooooouuuunc"
_FOLD = str.maketrans(ACCENTED, PLAIN)


def fold(text: str) -> str:
    """Lower-case and strip the accents covered by ``ACCENTED``."""
    return text.lower().translate(_FOLD)
