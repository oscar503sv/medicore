"""Reports router: the rows behind the metrics, on screen or as a CSV download."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import Response

from medicore.application.use_cases.reports import (
    ExportReport,
    GetReport,
    Report,
    ReportQuery,
    ReportTable,
)
from medicore.domain.shared.identifiers import UserId
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.report_csv import render_csv
from medicore.presentation.schemas.reports import ReportResponse

router = APIRouter(prefix="/reports", tags=["reports"])


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _table(table: ReportTable) -> dict:
    return {
        "columns": [{"key": c.key, "kind": c.kind} for c in table.columns],
        "rows": [[_json(v) for v in row] for row in table.rows],
    }


def _report(report: Report) -> dict:
    return {
        "kind": report.kind, "start": report.start, "end": report.end,
        "scope": report.scope, "doctor_id": report.doctor_id, "money": report.money,
        "tier": report.tier, "summary": _table(report.summary),
        "detail": _table(report.detail),
    }


def _query(kind: str, start: date, end: date, doctor_id: str | None) -> ReportQuery:
    return ReportQuery(kind=kind, start=start, end=end,
                       doctor_id=UserId.parse(doctor_id) if doctor_id else None)


@router.get("/{kind}", response_model=ReportResponse)
def get_report(
    kind: str, start: date, end: date, actor: Actor, uow: UoW, clock: Clock,
    doctor_id: str | None = None,
):
    return _report(GetReport(uow, clock).execute(actor, _query(kind, start, end, doctor_id)))


@router.get("/{kind}/csv")
def export_report(
    kind: str, start: date, end: date, actor: Actor, uow: UoW, clock: Clock,
    doctor_id: str | None = None,
    part: str = Query(default="detail", pattern="^(detail|summary)$"),
    lang: str = Query(default="es", pattern="^(es|en)$"),
):
    report = ExportReport(uow, clock).execute(
        actor, _query(kind, start, end, doctor_id), part
    )
    table = report.detail if part == "detail" else report.summary
    suffix = "" if part == "detail" else "-resumen" if lang == "es" else "-summary"
    filename = f"medicore-{kind}{suffix}-{start.isoformat()}-{end.isoformat()}.csv"
    return Response(
        content=render_csv(table, lang),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "Cache-Control": "no-store"},
    )
