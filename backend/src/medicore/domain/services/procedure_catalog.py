"""The procedure catalog a new clinic starts with: the most common minor procedures of a
Salvadoran outpatient clinic. Each clinic then edits, archives or adds its own; these are
clinic data, so they are written in Spanish."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.domain.enums import ProcedurePerformer

DOCTOR = ProcedurePerformer.DOCTOR
NURSING = ProcedurePerformer.DOCTOR_OR_NURSE


@dataclass(frozen=True, slots=True)
class DefaultProcedure:
    name: str
    performer: ProcedurePerformer
    requires_consent: bool
    follow_up_days: int | None = None
    takes_specimen: bool = False
    technique: str | None = None
    instructions: str | None = None


DEFAULT_PROCEDURES: tuple[DefaultProcedure, ...] = (
    DefaultProcedure(
        "Curación de herida", NURSING, False, 2,
        technique="Retiro de apósito previo. Lavado con solución salina, limpieza de bordes y "
                  "aplicación de antiséptico. Cubierta con apósito estéril.",
        instructions="Mantener la herida limpia y seca. Volver si hay enrojecimiento, calor, "
                     "pus o fiebre.",
    ),
    DefaultProcedure(
        "Sutura de herida", DOCTOR, True, 8,
        technique="Asepsia y antisepsia. Infiltración de anestesia local. Exploración y lavado "
                  "de la herida. Afrontamiento de bordes con puntos simples.",
        instructions="No mojar la herida en 48 horas. Curación diaria. Retiro de puntos en la "
                     "fecha indicada.",
    ),
    DefaultProcedure(
        "Retiro de puntos", NURSING, False,
        technique="Limpieza de la herida con antiséptico. Corte y retiro de cada punto. "
                  "Verificación de buena cicatrización.",
        instructions="Proteger la cicatriz del sol durante los próximos meses.",
    ),
    DefaultProcedure(
        "Drenaje de absceso", DOCTOR, True, 2,
        technique="Asepsia y antisepsia. Anestesia local. Incisión sobre la zona fluctuante, "
                  "drenaje del contenido, lavado de la cavidad y colocación de drenaje.",
        instructions="Curación diaria. Tomar el tratamiento indicado. Volver si aumenta el "
                     "dolor o hay fiebre.",
    ),
    DefaultProcedure(
        "Extracción de uña (onicectomía)", DOCTOR, True, 7,
        technique="Bloqueo digital con anestesia local. Torniquete. Despegamiento y extracción "
                  "de la lámina ungueal. Hemostasia y vendaje compresivo.",
        instructions="Mantener el pie elevado el primer día. Curación cada 48 horas.",
    ),
    DefaultProcedure(
        "Lavado de oído", NURSING, False,
        technique="Otoscopia previa. Irrigación del conducto auditivo con agua tibia hasta "
                  "extraer el tapón de cerumen. Otoscopia de control.",
        instructions="No introducir hisopos en el oído.",
    ),
    DefaultProcedure(
        "Infiltración articular", DOCTOR, True, 15,
        technique="Asepsia y antisepsia. Punción articular e infiltración del medicamento "
                  "indicado.",
        instructions="Reposo relativo de la articulación por 48 horas. Hielo local si hay "
                     "dolor.",
    ),
    DefaultProcedure(
        "Crioterapia de lesión cutánea", DOCTOR, True, 15,
        technique="Aplicación de nitrógeno líquido sobre la lesión en ciclos de congelación y "
                  "descongelación.",
        instructions="Puede formarse una ampolla: no reventarla. Mantener la zona limpia.",
    ),
    DefaultProcedure(
        "Colocación de DIU", DOCTOR, True, 30,
        technique="Especuloscopia, asepsia del cuello uterino, histerometría e inserción del "
                  "dispositivo. Corte de hilos.",
        instructions="Puede haber cólico y sangrado leve unos días. Control en un mes.",
    ),
    DefaultProcedure(
        "Retiro de DIU", DOCTOR, False,
        technique="Especuloscopia, localización de los hilos y retiro del dispositivo con "
                  "tracción suave.",
    ),
    DefaultProcedure(
        "Citología cervicovaginal (Papanicolaou)", NURSING, False, takes_specimen=True,
        technique="Especuloscopia. Toma de muestra de exocérvix y endocérvix, extendido en "
                  "lámina y fijación.",
        instructions="El resultado se entrega en aproximadamente dos semanas.",
    ),
    DefaultProcedure(
        "Electrocardiograma", NURSING, False,
        technique="Electrocardiograma de 12 derivaciones en reposo.",
    ),
    DefaultProcedure(
        "Biopsia de piel", DOCTOR, True, 10, takes_specimen=True,
        technique="Asepsia y antisepsia. Anestesia local. Toma de biopsia con sacabocado. "
                  "Hemostasia y punto de sutura.",
        instructions="Curación diaria. El resultado de patología llega en dos a tres semanas.",
    ),
    DefaultProcedure(
        "Retiro de cuerpo extraño", DOCTOR, False, 3,
        technique="Exploración de la zona. Anestesia local si es necesaria. Extracción del "
                  "cuerpo extraño y lavado.",
        instructions="Volver si hay signos de infección.",
    ),
)
