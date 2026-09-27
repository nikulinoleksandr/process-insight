"""Prüft die Detektoren an echten Logs: Laufzeiten und alle Befunde auf einen Blick.

Aufruf im Ordner backend (Dateien z.B. im Projektordner data/):

    python scripts/evaluate_logs.py ../data/sepsis.xes ../data/bpic2012.xes.gz
    python scripts/evaluate_logs.py "../data/helpdesk.csv:CaseID,ActivityID,CompleteTimestamp"

Bei CSV-Dateien stehen hinter dem Doppelpunkt die Spalten für Fall, Aktivität,
Zeitstempel und optional Ressource.
"""

import logging
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.importing.csv import read_csv  # noqa: E402
from app.core.importing.normalize import ColumnMapping  # noqa: E402
from app.core.importing.xes import read_xes  # noqa: E402
from app.core.insights.engine import run_analysis  # noqa: E402

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)


def load(spec: str):
    if ".csv:" in spec:
        path, columns = spec.split(":", 1)
        names = columns.split(",")
        mapping = ColumnMapping(*names[:3], resource=names[3] if len(names) > 3 else None)
        return Path(path).name, read_csv(Path(path), mapping)
    return Path(spec).name, read_xes(Path(spec))


def main(specs: list[str]) -> None:
    for spec in specs:
        start = time.perf_counter()
        name, normalized = load(spec)
        imported = time.perf_counter() - start
        start = time.perf_counter()
        result = run_analysis(normalized.events)
        analysed = time.perf_counter() - start
        s = result.log_summary
        print(f"\n=== {name}: {s.n_cases} Fälle, {s.n_events} Events, {s.n_variants} Varianten")
        print(f"    Import {imported:.1f} s, Analyse {analysed:.2f} s", end="")
        skipped = normalized.ignored_lifecycle_events
        if skipped:
            print(f", {skipped} Start-/Plan-Events übersprungen", end="")
        print()
        for run in result.detector_runs:
            if run.status != "ok":
                print(f"    ({run.detector_id}: {run.status} – {run.message})")
        for i in result.insights:
            share = i.affected_case_share * 100
            print(f"    [{i.severity:6}] {i.title} ({share:.1f} % der Fälle)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1:])
