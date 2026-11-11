"""PrintSettings value object — how the clinic's documents come out on paper."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.domain.enums import PaperSize


@dataclass(frozen=True, slots=True)
class PrintSettings:
    """``paper`` is the default for prescriptions, orders, certificates and slips (it can be
    switched when printing); ``letterhead`` means the clinic prints on pre-printed paper, so
    the clinic header is left out and its space kept blank."""

    paper: PaperSize = PaperSize.HALF_LETTER
    letterhead: bool = False
