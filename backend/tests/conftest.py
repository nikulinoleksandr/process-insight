from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.columns import ACTIVITY, CASE, RESOURCE, TIMESTAMP
from app.core.importing.normalize import normalize
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
RUNNING_EXAMPLE = FIXTURES / "running-example.xes"


def make_log(rows: list[tuple]) -> pd.DataFrame:
    """Baut ein kleines Test-Log aus Zeilen (Fall, Aktivität, Tag[, Ressource]).

    Der Tag ist eine Zahl: 0 = 1. Januar 2024, 1.5 = 2. Januar 12 Uhr usw.
    """
    start = pd.Timestamp("2024-01-01", tz="UTC")
    data = {
        CASE: [r[0] for r in rows],
        ACTIVITY: [r[1] for r in rows],
        TIMESTAMP: [start + pd.Timedelta(days=r[2]) for r in rows],
    }
    if all(len(r) > 3 for r in rows):
        data[RESOURCE] = [r[3] for r in rows]
    return normalize(pd.DataFrame(data)).events


@pytest.fixture
def client(tmp_path):
    settings = Settings(storage_dir=tmp_path / "storage", demo_log_path=RUNNING_EXAMPLE)
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def small_upload_client(tmp_path):
    settings = Settings(storage_dir=tmp_path / "storage", demo_log_path=None, max_upload_mb=0)
    with TestClient(create_app(settings)) as c:
        yield c
