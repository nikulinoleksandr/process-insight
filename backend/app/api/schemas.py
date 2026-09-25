"""Ein- und Ausgabeformate der API. FastAPI erzeugt daraus die Doku unter /docs."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.insights.base import Insight
from app.core.insights.engine import DetectorRun
from app.core.process.stats import LogSummary

LogStatus = Literal["processing", "needs_mapping", "ready", "failed"]
AnalysisStatus = Literal["pending", "running", "done", "failed"]


class CsvPreviewOut(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    suggested_mapping: dict[str, str | None]


class LogOut(BaseModel):
    id: str
    name: str
    source_format: Literal["xes", "csv"]
    status: LogStatus
    uploaded_at: str
    is_demo: bool
    n_events: int | None = None
    n_cases: int | None = None
    n_activities: int | None = None
    has_resource: bool | None = None
    dropped_rows: int | None = None
    csv_preview: CsvPreviewOut | None = None


class MappingIn(BaseModel):
    case: str = Field(description="Spalte mit der Fall-ID")
    activity: str = Field(description="Spalte mit der Aktivität")
    timestamp: str = Field(description="Spalte mit dem Zeitstempel")
    resource: str | None = Field(None, description="Optional: Spalte mit der Ressource")


class AnalysisIn(BaseModel):
    config: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Optionale Einstellungen pro Detektor, z.B. {'sla': {'max_days': 10}}",
    )


class InsightOut(BaseModel):
    """Wie Insight, aber nur mit einer Stichprobe der Fall-IDs (Rest über /cases)."""

    id: str
    detector_id: str
    category: str
    severity: str
    title: str
    summary: str
    severity_rule: str
    metrics: dict[str, float | int | str]
    evidence: dict[str, Any]
    affected_case_count: int
    affected_case_share: float
    sample_case_ids: list[str]

    @classmethod
    def from_insight(cls, insight: Insight, sample: int = 20) -> "InsightOut":
        data = insight.model_dump(exclude={"affected_case_ids"})
        return cls(**data, sample_case_ids=insight.affected_case_ids[:sample])


class AnalysisResultOut(BaseModel):
    log_summary: LogSummary
    insights: list[InsightOut]
    detector_runs: list[DetectorRun]


class AnalysisOut(BaseModel):
    id: str
    log_id: str
    status: AnalysisStatus
    created_at: str
    started_at: str | None
    finished_at: str | None
    error_message: str | None
    config: dict[str, Any]
    result: AnalysisResultOut | None = None


class CaseOut(BaseModel):
    case_id: str
    n_events: int
    start: str
    end: str
    duration_seconds: float


class CasePage(BaseModel):
    total: int
    offset: int
    limit: int
    cases: list[CaseOut]


class DetectorInfo(BaseModel):
    id: str
    name: str
    category: str
    required_columns: list[str]
    config_schema: dict[str, Any]
