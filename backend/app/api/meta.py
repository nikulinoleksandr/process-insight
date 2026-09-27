from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_explanation_service, get_log_service
from app.api.logs import to_out
from app.api.schemas import DetectorInfo, LogOut
from app.core.insights.registry import DETECTORS
from app.services.explanation_service import ExplanationService
from app.services.log_service import LogService

router = APIRouter(tags=["Allgemein"])


@router.get("/health", summary="Lebenszeichen")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/features", summary="Welche optionalen Funktionen aktiv sind")
def features(
    explanations: Annotated[ExplanationService, Depends(get_explanation_service)],
) -> dict[str, bool | str | None]:
    return {
        "ai_explanations": explanations.enabled,
        "ai_model": explanations.explainer.model if explanations.explainer else None,
    }


@router.get("/storage", summary="Belegter Speicher und Grenzen")
def storage(request: Request) -> dict[str, float | int | None]:
    cleanup = request.app.state.cleanup_service
    logs = cleanup.db.list_logs()
    return {
        "used_mb": round(cleanup.files.total_size() / 1024**2, 1),
        "limit_mb": round(cleanup.max_bytes / 1024**2) if cleanup.max_bytes else None,
        "retention_days": cleanup.retention.days if cleanup.retention else None,
        "logs": len(logs),
    }


@router.get("/demo", response_model=LogOut, summary="Das vorinstallierte Demo-Log")
def demo(logs: Annotated[LogService, Depends(get_log_service)]) -> LogOut:
    return to_out(logs.demo())


@router.get("/detectors", response_model=list[DetectorInfo], summary="Verfügbare Detektoren")
def detectors() -> list[DetectorInfo]:
    return [
        DetectorInfo(
            id=d.id,
            name=d.name,
            category=d.category,
            required_columns=sorted(d.required_columns),
            config_schema=d.config_model.model_json_schema(),
        )
        for d in DETECTORS
    ]
