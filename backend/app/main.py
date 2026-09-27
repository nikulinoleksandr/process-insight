"""Einstiegspunkt der Anwendung. Start lokal mit:  uvicorn app.main:app --reload"""

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import analyses, logs, meta
from app.config import Settings, get_settings
from app.llm.explainer import ClaudeExplainer, Explainer
from app.services.analysis_service import AnalysisService
from app.services.cleanup_service import CleanupService
from app.services.errors import (
    BadInputError,
    ConflictError,
    NotFoundError,
    RateLimitedError,
    TooLargeError,
)
from app.services.explanation_service import ExplanationService
from app.services.log_service import LogService
from app.storage.database import Database
from app.storage.files import FileStore

logging.basicConfig(level=logging.INFO)


def build_explainer(settings: Settings) -> Explainer | None:
    """Ohne API-Schlüssel gibt es keine KI; das Tool läuft trotzdem."""
    secret = settings.anthropic_api_key
    key = secret.get_secret_value().strip() if secret else ""
    if not key:
        return None
    return ClaudeExplainer(
        api_key=key,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
    )


def create_app(settings: Settings | None = None, explainer: Explainer | None = None) -> FastAPI:
    """explainer kann für Tests übergeben werden; sonst entscheidet die Konfiguration."""
    settings = settings or get_settings()
    if explainer is None:
        explainer = build_explainer(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.storage_dir / "app.db")
        files = FileStore(settings.storage_dir)
        log_service = LogService(
            db, files, settings.max_upload_mb, settings.max_events, settings.cache_logs
        )
        cleanup = CleanupService(
            db, files, log_service, settings.retention_days, settings.max_storage_mb
        )
        app.state.cleanup_service = cleanup
        log_service.on_new_log = lambda: threading.Thread(target=cleanup.run, daemon=True).start()
        try:
            cleanup.run()
        except Exception:
            logging.getLogger(__name__).exception("Aufräumen beim Start fehlgeschlagen")
        app.state.log_service = log_service
        analysis_service = AnalysisService(db, files, log_service)
        app.state.analysis_service = analysis_service
        app.state.explanation_service = ExplanationService(
            analysis_service, files, explainer, settings.llm_requests_per_hour
        )
        try:
            log_service.ensure_demo(settings.demo_log_path)
        except Exception:
            logging.getLogger(__name__).exception("Demo-Log konnte nicht angelegt werden")
        yield

    app = FastAPI(
        title="Process Insight",
        description="Findet Probleme in Geschäftsprozessen anhand von Event-Logs.",
        version="0.1.0",
        lifespan=lifespan,
    )
    for router in (meta.router, logs.router, analyses.router):
        app.include_router(router, prefix="/api")

    status_codes = {
        NotFoundError: 404,
        ConflictError: 409,
        TooLargeError: 413,
        BadInputError: 422,
        RateLimitedError: 429,
    }
    for exc_type, code in status_codes.items():

        def handler(request: Request, exc: Exception, code: int = code) -> JSONResponse:
            return JSONResponse(status_code=code, content={"detail": str(exc)})

        app.add_exception_handler(exc_type, handler)

    # Die Oberflaeche liegt unter "/", die API bleibt unter "/api".
    # Der Mount kommt zuletzt, damit die Router zuerst greifen.
    static_dir = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


app = create_app()
