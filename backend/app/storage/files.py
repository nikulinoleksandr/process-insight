"""Ablage von Dateien: normalisierte Logs (Parquet), Kennzahlen und Analyseergebnisse (JSON).

Die hochgeladene Originaldatei wird nur so lange behalten, bis sie eingelesen ist. Ein
Parquet-Log ist typischerweise 20- bis 50-mal kleiner als die XES-Datei.
"""

import shutil
from pathlib import Path

import pandas as pd

from app.core.columns import ACTIVITY, CASE, RESOURCE, TIMESTAMP


class FileStore:
    def __init__(self, root: Path):
        self.root = root
        (root / "logs").mkdir(parents=True, exist_ok=True)
        (root / "analyses").mkdir(parents=True, exist_ok=True)
        (root / "explanations").mkdir(parents=True, exist_ok=True)

    def log_dir(self, log_id: str) -> Path:
        path = self.root / "logs" / log_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def original_path(self, log_id: str, suffix: str) -> Path:
        return self.log_dir(log_id) / f"original{suffix}"

    def find_original(self, log_id: str) -> Path | None:
        matches = sorted(self.log_dir(log_id).glob("original*"))
        return matches[0] if matches else None

    def events_path(self, log_id: str) -> Path:
        return self.log_dir(log_id) / "events.parquet"

    def save_events(self, log_id: str, events: pd.DataFrame) -> None:
        # Zusatzspalten aus XES/CSV können gemischte Typen enthalten; als Text sind sie sicher.
        standard = {CASE, ACTIVITY, TIMESTAMP, RESOURCE}
        df = events.copy()
        for col in df.columns:
            if col not in standard and df[col].dtype == object:
                df[col] = df[col].astype("string")
        df.to_parquet(self.events_path(log_id), index=False, compression="zstd")

    def load_events(self, log_id: str) -> pd.DataFrame:
        return pd.read_parquet(self.events_path(log_id))

    def summary_path(self, log_id: str) -> Path:
        return self.log_dir(log_id) / "summary.json"

    def delete_original(self, log_id: str) -> None:
        for path in self.log_dir(log_id).glob("original*"):
            path.unlink(missing_ok=True)

    def delete_log(self, log_id: str) -> None:
        shutil.rmtree(self.root / "logs" / log_id, ignore_errors=True)

    def existing_log_ids(self) -> set[str]:
        return {p.name for p in (self.root / "logs").iterdir() if p.is_dir()}

    def result_path(self, analysis_id: str) -> Path:
        return self.root / "analyses" / f"{analysis_id}.json"

    def existing_result_ids(self) -> set[str]:
        return {p.stem for p in (self.root / "analyses").glob("*.json")}

    def explanations_dir(self) -> Path:
        return self.root / "explanations"

    def log_mtime(self, log_id: str) -> float:
        path = self.root / "logs" / log_id
        return path.stat().st_mtime if path.exists() else 0.0

    def log_size(self, log_id: str) -> int:
        return _size(self.root / "logs" / log_id)

    def total_size(self) -> int:
        return _size(self.root)


def _size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
