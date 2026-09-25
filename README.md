# Process Insight

Process Insight liest Event-Logs von Geschäftsprozessen (XES oder CSV) ein, zeigt den tatsächlichen Ablauf als Prozesslandkarte und findet automatisch typische Probleme: Nacharbeit, Engpässe, lange Durchlaufzeiten, Verstöße gegen das Vier-Augen-Prinzip und ungewöhnliche Abläufe.

> Status: Backend in Arbeit (Phase 2–3). Eine einfache Oberfläche liegt bei; das
> React-Frontend und die KI-Erklärungen folgen.

## Was schon funktioniert

- Upload von XES- und CSV-Dateien, bei CSV mit Vorschlag für die Spaltenzuordnung
- Kennzahlen: Fälle, Events, Varianten, Durchlaufzeiten
- Tabelle aller Aktivitäten mit Häufigkeit und Anzahl betroffener Fälle
- Drei Ansichten des Prozesses: interaktive Prozesslandkarte (Directly-Follows-Graph mit
  Häufigkeiten, Wartezeiten und Detailgrad-Regler), BPMN und Petri-Netz
- Insight-Engine mit fünf Detektoren; Frist, Anzahl der Engpässe, Schwelle für seltene
  Varianten und Aktivitätspaare fürs Vier-Augen-Prinzip lassen sich in der Oberfläche einstellen
- Jedes Insight ist nachvollziehbar: lesbare Kennzahlen, Liste der betroffenen Fälle mit
  ihrem Ablauf und Hervorhebung der Stelle in der Prozesslandkarte
- Analysen laufen im Hintergrund, Ergebnisse werden gespeichert und wiederverwendet
- REST-API mit automatischer Dokumentation, 48 automatische Tests, CI mit GitHub Actions

## Server starten (Windows, PowerShell)

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Dann im Browser **<http://127.0.0.1:8000>** öffnen. Die Adresse ist immer dieselbe und
steht beim Start auch im Terminal. Beenden mit `Strg + C`.

Wer die virtuelle Umgebung lieber aktiviert, nimmt stattdessen:

```powershell
.\.venv\Scripts\Activate.ps1
cd backend
uvicorn app.main:app --reload
```

Auf der Startseite führen drei Schritte durch das Tool: Log laden (oder Demo-Log
öffnen), Überblick ansehen, Analyse starten. Die technische API-Dokumentation liegt
weiterhin unter </docs>.

### Einmalig einrichten

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements-dev.txt
```

Für die BPMN- und Petri-Netz-Ansicht muss zusätzlich [Graphviz](https://graphviz.org/download/)
installiert und `dot` über den PATH erreichbar sein.

### Weitere Befehle

Alle im Ordner `backend/`:

| Zweck | Befehl |
|---|---|
| Tests | `pytest` |
| Linting | `ruff check .` |
| Formatierung | `ruff format .` |

## Aufbau

```
backend/app/
├── api/        HTTP-Schnittstelle (FastAPI)
├── services/   Anwendungsfälle: Upload, Analyse
├── core/       Die eigentliche Logik, ohne Web oder Datenbank
│   ├── importing/   XES und CSV einlesen, normalisieren
│   ├── process/     Kennzahlen, Prozesslandkarte, BPMN/Petri-Netz, Varianten
│   └── insights/    Insight-Engine und Detektoren
├── storage/    SQLite für Metadaten, Parquet für Logs
└── static/     Einfache Oberfläche (eine HTML-Datei, kein Build-Schritt)
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

Dieses Projekt nutzt [PM4Py](https://github.com/process-intelligence-solutions/pm4py) (AGPL-3.0) und steht deshalb ebenfalls unter der AGPL-3.0, siehe [LICENSE](LICENSE).
