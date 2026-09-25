# Process Insight
Ein Web-Tool, das Event-Logs analysiert und Prozessprobleme automatisch findet und erklärt.
Details: siehe docs/VISION.md und docs/ARCHITEKTUR.md

## Technik
- Windows, PowerShell, Python 3.14 in .venv
- Backend: Python, FastAPI, PM4Py, pytest
- Frontend: React mit TypeScript (kommt später)

## Arbeitsweise
- Ich bin Student und will lernen. Erkläre jede Änderung kurz auf Deutsch in einfachen Worten.
- Kleine Schritte: pro Aufgabe nur die betroffenen Dateien ändern.
- Keine neue Funktion ohne Tests.
- Keine neuen Pakete installieren, ohne vorher zu fragen.
- Bei den Insight-Detektoren: gib mir nur Hinweise, außer ich bitte ausdrücklich um Code.

## Projektstruktur und Befehle
- Backend liegt in `backend/`, Aufbau siehe docs/ARCHITEKTUR.md (api → services → core).
- `core/` darf nichts von FastAPI, Datenbank oder KI wissen.
- Neue Detektoren: Klasse in `backend/app/core/insights/detectors/`, Eintrag in `registry.py`, Tests in `backend/tests/unit/test_detectors.py`.
- Alle Befehle im Ordner `backend/` ausführen:
  - Server starten: `uvicorn app.main:app --reload` (API-Doku unter http://127.0.0.1:8000/docs)
  - Tests: `pytest`
  - Linting und Formatierung: `ruff check .` und `ruff format .`
