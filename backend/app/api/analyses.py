import json
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.api.deps import get_analysis_service, get_log_service
from app.api.schemas import (
    AnalysisIn,
    AnalysisOut,
    AnalysisResultOut,
    CaseOut,
    CasePage,
    InsightOut,
)
from app.core.columns import ACTIVITY, CASE, TIMESTAMP
from app.services.analysis_service import AnalysisService
from app.services.errors import ConflictError, NotFoundError
from app.services.log_service import LogService

router = APIRouter(tags=["Analysen"])
Analyses = Annotated[AnalysisService, Depends(get_analysis_service)]
Logs = Annotated[LogService, Depends(get_log_service)]


def to_out(record: dict, service: AnalysisService) -> AnalysisOut:
    result = service.result(record["id"])
    return AnalysisOut(
        id=record["id"],
        log_id=record["log_id"],
        status=record["status"],
        created_at=record["created_at"],
        started_at=record["started_at"],
        finished_at=record["finished_at"],
        error_message=record["error_message"],
        config=json.loads(record["config_json"]),
        result=AnalysisResultOut(
            log_summary=result.log_summary,
            insights=[InsightOut.from_insight(i) for i in result.insights],
            detector_runs=result.detector_runs,
        )
        if result
        else None,
    )


@router.post(
    "/logs/{log_id}/analyses",
    response_model=AnalysisOut,
    status_code=202,
    summary="Analyse starten (läuft im Hintergrund)",
)
def start_analysis(
    log_id: str, analyses: Analyses, background: BackgroundTasks, body: AnalysisIn | None = None
) -> AnalysisOut:
    record, needs_run = analyses.start(log_id, body.config if body else None)
    if needs_run:
        background.add_task(analyses.run, record["id"])
    return to_out(record, analyses)


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut, summary="Status und Ergebnis")
def get_analysis(analysis_id: str, analyses: Analyses) -> AnalysisOut:
    return to_out(analyses.get(analysis_id), analyses)


@router.get(
    "/analyses/{analysis_id}/insights/{insight_id}/cases",
    response_model=CasePage,
    summary="Betroffene Fälle eines Insights, seitenweise",
)
def get_insight_cases(
    analysis_id: str,
    insight_id: str,
    analyses: Analyses,
    logs: Logs,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> CasePage:
    result = analyses.result(analysis_id)
    if result is None:
        raise ConflictError("Analyse ist noch nicht fertig.")
    insight = next((i for i in result.insights if i.id == insight_id), None)
    if insight is None:
        raise NotFoundError(f"Insight {insight_id} nicht gefunden.")

    page_ids = insight.affected_case_ids[offset : offset + limit]
    events = logs.events(analyses.get(analysis_id)["log_id"])
    subset = events[events[CASE].isin(page_ids)]
    grouped = subset.groupby(CASE)[TIMESTAMP].agg(["min", "max", "size"])
    # Das Log ist nach Fall und Zeit sortiert, die Reihenfolge stimmt also schon.
    traces = subset.groupby(CASE)[ACTIVITY].agg(list)
    cases = [
        CaseOut(
            case_id=cid,
            n_events=int(grouped.at[cid, "size"]),
            start=grouped.at[cid, "min"].isoformat(),
            end=grouped.at[cid, "max"].isoformat(),
            duration_seconds=(grouped.at[cid, "max"] - grouped.at[cid, "min"]).total_seconds(),
            trace=[str(a) for a in traces[cid]],
        )
        for cid in page_ids
        if cid in grouped.index
    ]
    return CasePage(total=insight.affected_case_count, offset=offset, limit=limit, cases=cases)
