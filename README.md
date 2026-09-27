# Process Insight

Process Insight liest Event-Logs von Geschäftsprozessen (XES oder CSV) ein, zeigt den tatsächlichen Ablauf als Prozesslandkarte und findet automatisch typische Probleme: Nacharbeit, Engpässe, lange Durchlaufzeiten, Verstöße gegen das Vier-Augen-Prinzip und ungewöhnliche Abläufe.

> Status: Version 1 funktioniert lokal – Analyse, Oberfläche und KI-Erklärungen.
> Als Nächstes: Test mit großen echten Logs und Veröffentlichung als Online-Demo.

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
- KI-Assistent auf Knopfdruck: erklärt jeden Befund in Alltagssprache, nennt mögliche
  Ursachen und schlägt Lösungen vor (Claude API, optional)
- Analysen laufen im Hintergrund, Ergebnisse werden gespeichert und wiederverwendet
- REST-API mit automatischer Dokumentation, 85 automatische Tests, CI mit GitHub Actions

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

### KI-Erklärungen einrichten (optional)

Ohne Einrichtung funktioniert alles, der Knopf „Erklären und Lösungen vorschlagen“ zeigt
dann nur die feste Zusammenfassung. Für echte KI-Erklärungen:

1. Unter <https://platform.claude.com> einen API-Schlüssel erstellen.
2. `backend\.env.example` nach `backend\.env` kopieren und den Schlüssel bei
   `PI_ANTHROPIC_API_KEY=` eintragen. Die `.env` ist in der `.gitignore` und landet nie auf GitHub.
3. Server neu starten.

So arbeitet der Assistent:

- Er bekommt **nur die Kennzahlen eines Befunds** und die Namen der Aktivitäten, nie die
  Rohdaten, Fall-IDs oder Namen von Personen.
- Er **rechnet nicht selbst**. Alle Zahlen kommen aus den Detektoren. Nennt die KI trotzdem
  eine Zahl, die nicht in den Kennzahlen steht, zeigt die Oberfläche eine Warnung.
- Die Antwort hat ein festes Format (Überschrift, Erklärung, mögliche Ursachen,
  Lösungsvorschläge), das die API per JSON-Schema erzwingt.
- Antworten werden zwischengespeichert; höchstens 30 neue Anfragen pro Stunde
  (einstellbar mit `PI_LLM_REQUESTS_PER_HOUR`), damit die Kosten überschaubar bleiben.
- Ist die KI nicht erreichbar, erscheint die feste Zusammenfassung statt eines Fehlers.

### Speicher

Hochgeladene Logs werden nach dem Einlesen nur noch als komprimierte Parquet-Datei
gespeichert (bei den Bußgeldern 3 MB statt 189 MB). Gleiche Dateien werden nur einmal
abgelegt, Logs werden nach 7 Tagen ohne Nutzung gelöscht, und der Speicherordner ist auf
2.000 MB begrenzt. Einstellbar in `backend\.env` mit `PI_RETENTION_DAYS` und
`PI_MAX_STORAGE_MB`; den aktuellen Stand zeigt <http://127.0.0.1:8000/api/storage>.

### Detektoren an echten Logs prüfen

```powershell
python scripts\evaluate_logs.py ..\data\sepsis.xes ..\data\bpic2012.xes.gz
```

Wie die Detektoren an sieben echten Logs kalibriert wurden: [docs/KALIBRIERUNG.md](docs/KALIBRIERUNG.md)

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
├── llm/        KI-Erklärungen: Prompt, erlaubte Daten, Anbindung an die Claude API
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
