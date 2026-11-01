"""Allergy alert: does a drug clash with the patient's recorded allergies?

Matching is on folded text (case and accents ignored): the allergy names the drug directly
("Diclofenaco"), or names a family the drug belongs to ("Penicilina" → amoxicilina,
"AINE" → ketorolaco). It is a safety net, not a pharmacology database: an empty result does
not mean the drug is safe, and the family lists only cover the drugs commonly applied in a
clinic. The application layer turns a match into a confirmation the nurse must justify.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

# Family → drugs (folded, as substrings of the drug name).
_FAMILIES: dict[str, tuple[str, ...]] = {
    "penicillins": (
        "penicilina", "amoxicilina", "ampicilina", "benzatinica", "dicloxacilina",
        "oxacilina", "piperacilina", "clavulan",
    ),
    "cephalosporins": (
        "cefalexina", "cefadroxilo", "cefazolina", "cefuroxima", "ceftriaxona", "cefotaxima",
        "ceftazidima", "cefepime", "cefixima",
    ),
    "nsaids": (
        "diclofenaco", "ketorolaco", "ibuprofeno", "naproxeno", "ketoprofeno", "piroxicam",
        "meloxicam", "indometacina", "acido acetilsalicilico", "aspirina", "aceclofenaco",
    ),
    "sulfonamides": ("sulfametoxazol", "sulfadiazina", "trimetoprim-sulfa", "cotrimoxazol"),
    "dipyrone": ("metamizol", "dipirona"),
}

# How a recorded allergy may name a family.
_ALIASES: dict[str, str] = {
    "penicilina": "penicillins",
    "penicilinas": "penicillins",
    "betalactamico": "penicillins",
    "betalactamicos": "penicillins",
    "cefalosporina": "cephalosporins",
    "cefalosporinas": "cephalosporins",
    "aine": "nsaids",
    "aines": "nsaids",
    "antiinflamatorios": "nsaids",
    "antiinflamatorios no esteroideos": "nsaids",
    "sulfa": "sulfonamides",
    "sulfas": "sulfonamides",
    "sulfonamidas": "sulfonamides",
    "metamizol": "dipyrone",
    "dipirona": "dipyrone",
}


def fold(text: str) -> str:
    stripped = unicodedata.normalize("NFD", text)
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn").lower().strip()


def allergy_conflicts(drug: str, allergies: Iterable[str]) -> list[str]:
    """The patient's allergies (as recorded) that the drug may trigger."""
    name = fold(drug)
    if not name:
        return []
    hits: list[str] = []
    for allergy in allergies:
        a = fold(allergy)
        if not a:
            continue
        family = _ALIASES.get(a)
        first = name.split()[0]
        direct = (len(a) >= 4 and a in name) or (len(first) >= 4 and first in a)
        in_family = family is not None and any(m in name for m in _FAMILIES[family])
        if direct or in_family:
            hits.append(allergy)
    return hits
