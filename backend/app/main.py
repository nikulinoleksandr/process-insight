"""Einstiegspunkt der Anwendung. Start lokal mit:  uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import analyses, logs, meta
from app.config import Settings, get_settings
from app.services.analysis_service import AnalysisService
from app.services.errors import BadInputError, ConflictError, NotFoundError, TooLargeError
from app.services.log_service import LogService
from app.storage.database import Database
from app.storage.files import FileStore

logging.basicConfig(level=logging.INFO)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.storage_dir / "app.db")
        files = FileStore(settings.storage_dir)
        log_service = LogService(db, files, settings.max_upload_mb, settings.max_events)
        app.state.log_service = log_service
        app.state.analysis_service = AnalysisService(db, files, log_service)
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
