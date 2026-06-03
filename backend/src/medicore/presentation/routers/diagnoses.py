"""Diagnosis catalog router — tenant-scoped autocomplete for the live consultation."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.use_cases.diagnoses import GetDiagnosisConfig, SearchDiagnoses
from medicore.presentation.dependencies import Actor, UoWFactory
from medicore.presentation.schemas.diagnoses import DiagnosisConfigResponse, DiagnosisSuggestion

router = APIRouter(prefix="/diagnoses", tags=["diagnoses"])


@router.get("/config", response_model=DiagnosisConfigResponse)
def diagnosis_config(actor: Actor, factory: UoWFactory):
    return DiagnosisConfigResponse(version=GetDiagnosisConfig(factory).execute(actor))


@router.get("/search", response_model=list[DiagnosisSuggestion])
def search_diagnoses(
    actor: Actor,
    factory: UoWFactory,
    q: str = Query("", min_length=0),
    limit: int = Query(20, ge=1, le=50),
):
    results = SearchDiagnoses(factory).execute(actor, q, limit)
    return [
        DiagnosisSuggestion(
            version=r.version, code=r.code, label=r.label, billable=r.billable, chapter=r.chapter
        )
        for r in results
    ]
