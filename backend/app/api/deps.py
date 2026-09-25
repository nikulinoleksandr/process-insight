"""Zugriff auf die Services aus den Routen (über den App-Zustand)."""

from fastapi import Request

from app.services.analysis_service import AnalysisService
from app.services.log_service import LogService


def get_log_service(request: Request) -> LogService:
    return request.app.state.log_service


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service
