from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, UploadFile

from app.api.deps import get_log_service
from app.api.schemas import CsvPreviewOut, LogOut, MappingIn
from app.core.importing.normalize import ColumnMapping
from app.core.process.models import ModelKind, render_model
from app.core.process.process_map import ProcessMap, build_process_map
from app.core.process.stats import LogSummary, summarize
from app.core.process.variants import Variant, top_variants
from app.services.log_service import LogService

router = APIRouter(prefix="/logs", tags=["Logs"])
Logs = Annotated[LogService, Depends(get_log_service)]


def to_out(record: dict, preview=None) -> LogOut:
    data = dict(record)
    data["is_demo"] = bool(data["is_demo"])
    if data.get("has_resource") is not None:
        data["has_resource"] = bool(data["has_resource"])
    if preview is not None:
        data["csv_preview"] = CsvPreviewOut(
            columns=preview.columns, rows=preview.rows, suggested_mapping=preview.suggested
        )
    return LogOut(**data)


@router.post("", response_model=LogOut, status_code=201, summary="Event-Log hochladen")
def upload_log(file: UploadFile, logs: Logs) -> LogOut:
    record, preview = logs.create(file.filename or "upload", file.file)
    return to_out(record, preview)


@router.post("/{log_id}/mapping", response_model=LogOut, summary="Spalten einer CSV zuordnen")
def set_mapping(log_id: str, body: MappingIn, logs: Logs) -> LogOut:
    mapping = ColumnMapping(
        case=body.case, activity=body.activity, timestamp=body.timestamp, resource=body.resource
    )
    return to_out(logs.apply_mapping(log_id, mapping))


@router.get("/{log_id}", response_model=LogOut, summary="Metadaten eines Logs")
def get_log(log_id: str, logs: Logs) -> LogOut:
    return to_out(logs.get(log_id))


@router.get("/{log_id}/summary", response_model=LogSummary, summary="Kennzahlen eines Logs")
def get_summary(log_id: str, logs: Logs) -> LogSummary:
    return summarize(logs.events(log_id))


@router.get("/{log_id}/process-map", response_model=ProcessMap, summary="Prozesslandkarte")
def get_process_map(
    log_id: str,
    logs: Logs,
    detail: Annotated[float, Query(ge=0, le=1, description="1 = alle Pfade")] = 1.0,
) -> ProcessMap:
    return build_process_map(logs.events(log_id), detail)


@router.get(
    "/{log_id}/model/{kind}",
    summary="Prozessmodell als SVG-Bild (bpmn oder petri)",
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {}}, "description": "Das Modell als SVG"}},
)
def get_model(log_id: str, kind: ModelKind, logs: Logs) -> Response:
    svg = render_model(logs.events(log_id), kind)
    # Das Bild ändert sich für ein Log nie, darf der Browser also zwischenspeichern.
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/{log_id}/variants", response_model=list[Variant], summary="Häufigste Varianten")
def get_variants(
    log_id: str, logs: Logs, limit: Annotated[int, Query(ge=1, le=200)] = 20
) -> list[Variant]:
    return top_variants(logs.events(log_id), limit)
