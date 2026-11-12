"""CSV rendering of a report table, in the language of the interface that asked for it.

The screen translates headers and enum values itself; a downloaded file cannot, so the
labels live here (Spanish and English, like the rest of the interface). Files open cleanly
in Excel: UTF-8 with BOM, comma-separated, ISO dates, amounts as plain decimals. Text that
starts like a formula (``=``, ``+``, ``-``, ``@``) is quoted with an apostrophe so a
spreadsheet never runs it (CSV injection).
"""

from __future__ import annotations

import csv
import io
from datetime import date, time
from decimal import Decimal
from typing import Any

from medicore.application.use_cases.reports import ReportColumn, ReportTable

LANGS = ("es", "en")

HEADERS: dict[str, dict[str, str]] = {
    "es": {
        "date": "Fecha", "time": "Hora", "code": "Código", "patient_code": "Expediente",
        "patient": "Paciente", "phone": "Teléfono", "doctor": "Médico", "type": "Tipo",
        "status": "Estado", "insurer": "Aseguradora", "listed": "Precio de lista",
        "charged": "Cobrado", "fee_note": "Nota del cobro", "appointments": "Citas",
        "source": "Origen", "concept": "Concepto", "visits": "Consultas",
        "procedures": "Procedimientos", "income": "Ingreso estimado", "attended": "Atendidas",
        "booked": "Agendadas", "no_shows": "No asistió", "cancelled": "Canceladas",
        "sex": "Sexo", "age": "Edad", "vaccine": "Vacuna", "dose": "Dosis", "lot": "Lote",
        "recorded_by": "Registrado por", "age_lt1": "Menores de 1 año", "age_1_4": "1 a 4 años",
        "age_5_9": "5 a 9 años", "age_10_19": "10 a 19 años", "age_20_59": "20 a 59 años",
        "age_60": "60 años y más", "total": "Total", "procedure": "Procedimiento",
        "ordered_by": "Indicado por", "performed_by": "Realizado por",
        "included": "Incluido en la consulta", "performed": "Realizados", "drug": "Medicamento",
        "route": "Vía", "dose_number": "N.º de dosis", "doses": "Dosis aplicadas",
    },
    "en": {
        "date": "Date", "time": "Time", "code": "Code", "patient_code": "Patient no.",
        "patient": "Patient", "phone": "Phone", "doctor": "Doctor", "type": "Type",
        "status": "Status", "insurer": "Insurer", "listed": "Listed price",
        "charged": "Charged", "fee_note": "Charge note", "appointments": "Appointments",
        "source": "Source", "concept": "Concept", "visits": "Visits",
        "procedures": "Procedures", "income": "Estimated income", "attended": "Attended",
        "booked": "Booked", "no_shows": "No-shows", "cancelled": "Cancelled",
        "sex": "Sex", "age": "Age", "vaccine": "Vaccine", "dose": "Dose", "lot": "Lot",
        "recorded_by": "Recorded by", "age_lt1": "Under 1", "age_1_4": "1–4 years",
        "age_5_9": "5–9 years", "age_10_19": "10–19 years", "age_20_59": "20–59 years",
        "age_60": "60 and over", "total": "Total", "procedure": "Procedure",
        "ordered_by": "Ordered by", "performed_by": "Performed by",
        "included": "Included in the visit", "performed": "Performed", "drug": "Drug",
        "route": "Route", "dose_number": "Dose no.", "doses": "Doses applied",
    },
}

ENUMS: dict[str, dict[str, dict[str, str]]] = {
    "es": {
        "appointment_type": {"consult": "Consulta", "follow_up": "Seguimiento",
                             "check_up": "Chequeo", "procedure": "Procedimiento",
                             "emergency": "Urgencia"},
        "appointment_status": {"scheduled": "Agendada", "confirmed": "Confirmada",
                               "in_progress": "En curso", "completed": "Completada",
                               "cancelled": "Cancelada", "no_show": "No asistió"},
        "income_source": {"visit": "Consulta", "procedure": "Procedimiento",
                          "procedure_included": "Procedimiento incluido en la consulta"},
        "sex": {"male": "Masculino", "female": "Femenino", "other": "Otro"},
        "application_route": {"im": "Intramuscular", "iv": "Intravenosa",
                              "sc": "Subcutánea", "id": "Intradérmica",
                              "nebulized": "Nebulización", "oral": "Oral"},
    },
    "en": {
        "appointment_type": {"consult": "Consultation", "follow_up": "Follow-up",
                             "check_up": "Check-up", "procedure": "Procedure",
                             "emergency": "Emergency"},
        "appointment_status": {"scheduled": "Scheduled", "confirmed": "Confirmed",
                               "in_progress": "In progress", "completed": "Completed",
                               "cancelled": "Cancelled", "no_show": "No show"},
        "income_source": {"visit": "Visit", "procedure": "Procedure",
                          "procedure_included": "Procedure included in the visit"},
        "sex": {"male": "Male", "female": "Female", "other": "Other"},
        "application_route": {"im": "Intramuscular", "iv": "Intravenous",
                              "sc": "Subcutaneous", "id": "Intradermal",
                              "nebulized": "Nebulization", "oral": "Oral"},
    },
}

# Same names as the vaccination screens (frontend ``vax.name.*``).
VACCINE_NAMES: dict[str, dict[str, str]] = {
    "es": {
        "BCG": "BCG", "HEPB_PED": "Hepatitis B pediátrica", "HEXA": "Hexavalente",
        "ROTA": "Rotavirus", "PCV13": "Neumococo conjugada 13",
        "INFLU_PED": "Influenza pediátrica", "SPR": "SPR", "DPT": "DPT",
        "BOPV": "Polio oral bivalente", "VPH": "Virus del papiloma humano", "TD": "Td",
        "TDPA": "Tdpa", "INFLU": "Influenza adulto", "PPSV23": "Neumococo polisacárida 23",
        "HEPB_ADULT": "Hepatitis B adulto", "COVID19": "COVID-19", "VARICELA": "Varicela",
        "HEPA": "Hepatitis A", "MENINGO": "Meningococo", "FIEBRE_AMARILLA": "Fiebre amarilla",
    },
    "en": {
        "BCG": "BCG", "HEPB_PED": "Paediatric hepatitis B", "HEXA": "Hexavalent",
        "ROTA": "Rotavirus", "PCV13": "Pneumococcal conjugate 13",
        "INFLU_PED": "Paediatric influenza", "SPR": "MMR", "DPT": "DTP",
        "BOPV": "Bivalent oral polio", "VPH": "Human papillomavirus", "TD": "Td",
        "TDPA": "Tdap", "INFLU": "Adult influenza", "PPSV23": "Pneumococcal polysaccharide 23",
        "HEPB_ADULT": "Adult hepatitis B", "COVID19": "COVID-19", "VARICELA": "Varicella",
        "HEPA": "Hepatitis A", "MENINGO": "Meningococcal", "FIEBRE_AMARILLA": "Yellow fever",
    },
}
DOSE_KINDS = {
    "es": {"dose": "Dosis {n}", "booster": "Refuerzo {n}", "single": "Dosis única",
           "yearly": "Anual", "periodic": "Cada {n} años"},
    "en": {"dose": "Dose {n}", "booster": "Booster {n}", "single": "Single dose",
           "yearly": "Yearly", "periodic": "Every {n} years"},
}
OUTSIDE_SCHEME = {"es": "Fuera del esquema", "en": "Outside the scheme"}

# What an empty insurer means in a summary (visits paid out of pocket).
NO_INSURER = {"es": "Particular", "en": "Out of pocket"}
YES_NO = {"es": ("Sí", "No"), "en": ("Yes", "No")}
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _age(months: int, lang: str) -> str:
    if months < 24:
        return f"{months} meses" if lang == "es" else f"{months} months"
    years = months // 12
    return f"{years} años" if lang == "es" else f"{years} years"


def _safe(text: str) -> str:
    return f"'{text}" if text.startswith(_FORMULA_START) else text


def cell(column: ReportColumn, value: Any, lang: str) -> str:
    if value is None:
        if column.key == "insurer":
            return NO_INSURER[lang]
        if column.kind == "dose":
            return OUTSIDE_SCHEME[lang]
        return ""
    kind = column.kind
    if kind == "money" and isinstance(value, Decimal):
        return f"{value:.2f}"
    if kind == "date" and isinstance(value, date):
        return value.isoformat()
    if kind == "time" and isinstance(value, time):
        return value.strftime("%H:%M")
    if kind == "bool":
        yes, no = YES_NO[lang]
        return yes if value else no
    if kind == "age":
        return _age(int(value), lang)
    if kind == "vaccine":
        return VACCINE_NAMES[lang].get(str(value), str(value))
    if kind == "dose":
        name, _, n = str(value).partition(":")
        return DOSE_KINDS[lang].get(name, name).replace("{n}", n)
    if kind.startswith("enum:"):
        return ENUMS[lang].get(kind[5:], {}).get(str(value), str(value))
    return _safe(str(value))


def render_csv(table: ReportTable, lang: str) -> bytes:
    lang = lang if lang in LANGS else "es"
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([HEADERS[lang].get(c.key, c.key) for c in table.columns])
    for row in table.rows:
        writer.writerow([cell(c, v, lang) for c, v in zip(table.columns, row, strict=True)])
    return ("﻿" + out.getvalue()).encode("utf-8")
