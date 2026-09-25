from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_log_service
from app.api.logs import to_out
from app.api.schemas import DetectorInfo, LogOut
from app.core.insights.registry import DETECTORS
from app.services.log_service import LogService

router = APIRouter(tags=["Allgemein"])


@router.get("/health", summary="Lebenszeichen")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
