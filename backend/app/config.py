"""Zentrale Einstellungen. Werte kommen aus Umgebungsvariablen oder einer .env-Datei.

Beispiel: PI_STORAGE_DIR=./storage setzt den Speicherordner.
Der API-Schlüssel für die KI-Erklärungen steht in PI_ANTHROPIC_API_KEY oder ANTHROPIC_API_KEY.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PI_", env_file=".env", extra="ignore", populate_by_name=True
    )

    storage_dir: Path = Path("storage")
    max_upload_mb: int = 200
    max_events: int = 2_000_000
    demo_log_path: Path | None = Path("tests/fixtures/running-example.xes")

    # Speicher: unbenutzte Logs werden nach retention_days gelöscht (0 = nie), und der
    # Speicherordner wird auf max_storage_mb begrenzt (0 = keine Grenze).
    retention_days: float = 7
    max_storage_mb: int = 2000
    cache_logs: int = 2  # so viele Logs bleiben für schnelle Abfragen im Arbeitsspeicher

    # KI-Erklärungen. Ohne Schlüssel läuft das Tool trotzdem, nur ohne KI.
    anthropic_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("PI_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    )
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_max_tokens: int = 1200
    llm_requests_per_hour: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
