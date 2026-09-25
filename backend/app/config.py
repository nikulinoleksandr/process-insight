"""Zentrale Einstellungen. Werte kommen aus Umgebungsvariablen oder einer .env-Datei.

Beispiel: PI_STORAGE_DIR=./storage setzt den Speicherordner.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PI_", env_file=".env", extra="ignore")

    storage_dir: Path = Path("storage")
    max_upload_mb: int = 200
    max_events: int = 2_000_000
    demo_log_path: Path | None = Path("tests/fixtures/running-example.xes")


@lru_cache
def get_settings() -> Settings:
    return Settings()
