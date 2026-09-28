"""Baut aus einem Insight die Daten, die das Sprachmodell sehen darf.

Grundsatz: Das Modell bekommt nur zusammengefasste Kennzahlen, niemals Rohdaten,
Fall-IDs oder Personennamen. Alle Zahlen stammen aus den Detektoren.
"""

from typing import Any

from app.core.insights.base import Insight, duration
from app.core.process.stats import LogSummary

CATEGORIES = {
    "efficiency": "Effizienz (Zeit und Wartezeiten)",
    "quality": "Qualität (Nacharbeit, Wiederholungen)",
    "compliance": "Compliance (Regeln und Kontrollen)",
    "deviation": "Abweichung vom Standardablauf",
}
SEVERITIES = {"high": "hoch", "medium": "mittel", "low": "niedrig"}


def _days(seconds: float) -> str:
    return f"{seconds / 86400:.1f} Tage".replace(".", ",")


def _pct(share: float) -> str:
    return f"{share * 100:.1f} %".replace(".", ",")


def _count(n: float) -> str:
    return f"{int(n):,}".replace(",", ".")


# Kennzahl -> (lesbarer Name, Formatierung). Gleiche Namen wie in der Oberfläche.
METRICS = {
    "affected_cases": ("Betroffene Fälle", _count),
    "extra_executions": ("Zusätzliche Ausführungen", _count),
    "max_executions_per_case": ("Höchstens in einem Fall", lambda n: f"{int(n)}-mal"),
    "median_wait_seconds": ("Wartezeit (Median)", duration),
    "total_wait_share": ("Anteil an der gesamten Wartezeit", _pct),
    "transition_count": ("Anzahl dieser Übergänge", _count),
    "threshold_seconds": ("Schwelle", _days),
    "median_seconds": ("Durchlaufzeit aller Fälle (Median)", duration),
    "max_seconds": ("Längster Fall", _days),
    "involved_resources": ("Beteiligte Personen", _count),
    "rare_variant_count": ("Seltene Varianten", _count),
    "total_variant_count": ("Varianten insgesamt", _count),
    "p90_wait_seconds": ("Wartezeit bei jedem zehnten Fall mindestens", duration),
    "repeat_rate": ("Anteil der Fälle mit Wiederholung", _pct),
    "mean_executions": (
        "Ausführungen je Fall (Durchschnitt)",
        lambda n: f"{n:.1f}".replace(".", ","),
    ),
    "standard_coverage": ("Anteil der 10 häufigsten Abläufe", _pct),
}

MAX_ACTIVITIES = 25


def _quotes(value: Any) -> Any:
    """Deutsche Anführungszeichen „…“ durch »…« ersetzen. Das Modell übernimmt sonst „…"
    mit geradem Schlusszeichen, und das beendet im JSON-Format mitten im Satz den Text."""
    if isinstance(value, str):
        return value.replace("„", "»").replace("“", "«")
    if isinstance(value, dict):
        return {k: _quotes(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_quotes(v) for v in value]
    return value


def build_payload(insight: Insight, summary: LogSummary) -> dict[str, Any]:
    return _quotes(_build(insight, summary))


def _build(insight: Insight, summary: LogSummary) -> dict[str, Any]:
    metrics = {}
    for key, value in insight.metrics.items():
        label, fmt = METRICS.get(key, (key, str))
        metrics[label] = fmt(value) if isinstance(value, int | float) else str(value)

    activities = list(summary.activity_counts)[:MAX_ACTIVITIES]
    return {
        "befund": {
            "titel": insight.title,
            "kategorie": CATEGORIES.get(insight.category, insight.category),
            "schweregrad": SEVERITIES.get(insight.severity, insight.severity),
            "zusammenfassung": insight.summary,
            "betroffene_faelle": _count(insight.affected_case_count),
            "anteil_betroffener_faelle": _pct(insight.affected_case_share),
            "kennzahlen": metrics,
            # Evidenz enthält nur Aktivitätsnamen und Einstellungen, keine Personen.
            "betroffene_stelle": {k: v for k, v in insight.evidence.items() if k != "resources"},
        },
        "prozess": {
            "faelle_insgesamt": _count(summary.n_cases),
            "ereignisse_insgesamt": _count(summary.n_events),
            "anzahl_aktivitaeten": summary.n_activities,
            "durchlaufzeit_median": duration(summary.case_duration.median),
            "aktivitaeten_nach_haeufigkeit": activities,
        },
    }
