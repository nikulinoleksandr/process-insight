# Process Insight

Process Insight liest Event-Logs von Geschäftsprozessen (XES oder CSV) ein, zeigt den tatsächlichen Ablauf als Prozesslandkarte und findet automatisch typische Probleme: Nacharbeit, Engpässe, lange Durchlaufzeiten, Verstöße gegen das Vier-Augen-Prinzip und ungewöhnliche Abläufe.

> Status: Backend in Arbeit (Phase 2–3). Frontend und KI-Erklärungen folgen.

## Was schon funktioniert

- Upload von XES- und CSV-Dateien, bei CSV mit Vorschlag für die Spaltenzuordnung
- Kennzahlen: Fälle, Events, Varianten, Durchlaufzeiten
- Prozesslandkarte (Directly-Follows-Graph) mit Häufigkeiten, Wartezeiten und Detailgrad-Regler
- Insight-Engine mit fünf Detektoren, jeder einzeln konfigurierbar
- Analysen laufen im Hintergrund, Ergebnisse werden gespeichert und wiederverwendet
- REST-API mit automatischer Dokumentation, 37 automatische Tests, CI mit GitHub Actions

## Schnellstart (Windows, PowerShell)

```powershell
.venv\Scripts\Activate.ps1
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Danach im Browser <http://127.0.0.1:8000/docs> öffnen. Beim Start wird ein Demo-Log angelegt; seine ID liefert `GET /api/demo`. Über `POST /api/logs/{id}/analyses` startest du eine Analyse und rufst das Ergebnis mit `GET /api/analyses/{analysis_id}` ab.

Tests: `pytest` · Linting: `ruff check .`

## Aufbau

```
backend/app/
├── api/        HTTP-Schnittstelle (FastAPI)
├── services/   Anwendungsfälle: Upload, Analyse
├── core/       Die eigentliche Logik, ohne Web oder Datenbank
│   ├── importing/   XES und CSV einlesen, normalisieren
│   ├── process/     Kennzahlen, Prozesslandkarte, Varianten
│   └── insights/    Insight-Engine und Detektoren
└── storage/    SQLite für Metadaten, Parquet für Logs
```

Details und Begründungen: [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md)

## Detektoren

| Detektor | Findet | Kategorie |
|---|---|---|
| `rework` | Aktivitäten, die innerhalb eines Falls wiederholt werden | Qualität |
| `bottleneck` | Übergänge mit dem größten Anteil an der Wartezeit | Effizienz |
| `sla` | Fälle über einer Frist oder auffällig langsame Fälle | Effizienz |
| `segregation_of_duties` | Dieselbe Person führt zwei zu trennende Aktivitäten aus | Compliance |
| `rare_variants` | Fälle, die selten genutzte Wege durch den Prozess nehmen | Abweichung |

## Lizenz

Dieses Projekt nutzt [PM4Py](https://github.com/process-intelligence-solutions/pm4py) (AGPL-3.0) und steht deshalb ebenfalls unter der AGPL-3.0.
