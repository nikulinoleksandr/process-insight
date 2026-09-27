# Kalibrierung der Detektoren an echten Logs

> Stand: September 2026. Nachvollziehbar mit `backend/scripts/evaluate_logs.py`.

Bis zu dieser Runde waren die Detektoren nur mit dem kleinen running-example (6 Fälle) und
künstlichen Daten getestet. Hier ist dokumentiert, wie sie auf sieben echte Event-Logs
reagiert haben, welche Befunde fachlich falsch oder nutzlos waren und was geändert wurde.

## Die Logs

| Log | Bereich | Fälle | Events | Besonderheit |
|---|---|---:|---:|---|
| running-example | Lehrbeispiel (Entschädigungsanträge) | 6 | 42 | Referenz aus dem Lehrbuch |
| Sepsis Cases | Krankenhaus, Sepsis-Patienten | 1.050 | 15.214 | fast jeder Fall anders (846 Varianten), Laborwerte werden laufend gemessen |
| Receipt (WABO) | Gemeinde, Eingang von Bauanträgen | 1.434 | 8.577 | meist sekundenschnell, selten sehr lange Pausen |
| BPI Challenge 2012 | Bank, Kreditanträge | 13.087 | 262.200 | pro Schritt „schedule“, „start“ und „complete“ |
| Helpdesk | Ticketsystem eines Softwarehauses | 3.804 | 13.710 | CSV, Aktivitäten nur als Nummern |
| Hospital Billing (Auszug) | Krankenhaus-Abrechnung | 9.999 | 49.950 | CSV, Abrechnung oft Monate später |
| Road Traffic Fines | Italienische Behörde, Bußgelder | 150.370 | 561.470 | gesetzliche Fristen, Ratenzahlungen, 185 MB XES |

Quellen: 4TU.ResearchData (Sepsis, Road Traffic Fines), Testdaten von PM4Py (Receipt,
BPI 2012), Repository „ProcessSequencePrediction“ (Helpdesk), R-Paket „eventdataR“
(Hospital Billing). Die Dateien liegen lokal in `data/` und nicht in Git.

## Was vorher nicht gestimmt hat

1. **Start- und Complete-Events doppelt gezählt (BPI 2012).** Jeder Arbeitsschritt stand
   zwei- bis dreimal im Log. Folge: 7 Befunde mit Schweregrad *hoch*, fast alle falsch,
   z.B. „Nacharbeit bei W_Completeren aanvraag“ in 56 % der Fälle und ein „Engpass“ von
   einem Schritt zu sich selbst (in Wahrheit die Bearbeitungszeit des Schritts).
2. **Geplante Wiederholungen als Nacharbeit gemeldet.** Sepsis: „Nacharbeit bei CRP“
   (66 % der Fälle, bis zu 69-mal) und „Leucocytes“. Das sind Laborwerte, die regelmäßig
   gemessen werden sollen.
3. **Alarm „seltene Varianten“ ohne Standardablauf.** Sepsis: „90 % weichen vom Standard
   ab“, Schweregrad *hoch*. Es gibt dort aber gar keinen Standard; die 10 häufigsten
   Abläufe decken nur 13 % der Fälle ab.
4. **Wiederholungen und Null-Wartezeiten als Engpass.** „Leucocytes → Leucocytes“ (Abstand
   zwischen zwei Messungen) und „CRP → Leucocytes“ mit 0 Sekunden Median.
5. **Irreführende Zahlen bei seltenen langen Pausen.** Receipt: „Wartezeit im Median
   0,0 Tage“ bei Schweregrad *hoch*. Tatsächlich geht es meist sofort weiter, aber jeder
   zehnte Fall wartet über 8 Tage.
6. **Durchlaufzeit-Befund bei jedem Log.** Ohne vorgegebene Frist meldete der Detektor
   immer „die langsamsten 10 %“, oft mit *hoch*. Irgendein Zehntel ist immer das langsamste.
7. **Doppelte Befunde.** BPI 2012: drei getrennte Befunde für „O_SELECTED“, „O_CREATED“ und
   „O_SENT“, die sich in exakt denselben 1.438 Fällen wiederholen (ein neues Angebot).

## Was geändert wurde

| Problem | Lösung |
|---|---|
| 1 | Beim Import bleiben nur „complete“-Events, wenn ein Log mehrere Lifecycle-Stufen hat. Die Oberfläche zeigt, wie viele Events übersprungen wurden. Gilt auch für CSV mit einer Spalte `lifecycle`. |
| 2 | Wiederholt sich ein Schritt in mindestens 50 % der Fälle, in denen er vorkommt (und in mindestens 20 Fällen), gilt er als planmäßig und wird nur als *niedrig* („wiederholt sich fast immer“) gemeldet. Zusätzlich kann man Schritte als planmäßig markieren. |
| 3 | Decken die 10 häufigsten Abläufe weniger als 50 % der Fälle ab, gibt es statt des Alarms einen Hinweis *niedrig*: „Kein einheitlicher Standardablauf erkennbar“. |
| 4 | Übergänge eines Schritts zu sich selbst werden nie als Engpass gemeldet, ebenso Übergänge, bei denen 90 % der Fälle unter einer Stunde warten, und solche mit weniger als 5 % Anteil an der gesamten Wartezeit. |
| 5 | Der Text nennt Median *und* den Wert, den jeder zehnte Fall überschreitet, und beschreibt „meist schnell, manchmal sehr lange“ ausdrücklich. Zeitangaben wählen die passende Einheit (Minuten, Stunden, Tage). |
| 6 | Ohne Frist wird nur gemeldet, wenn die langsamen Fälle mindestens 1,5-mal so lange dauern wie ein typischer Fall, und höchstens mit *mittel*. *Hoch* gibt es nur mit einer festen Frist in Tagen. |
| 7 | Schritte, die sich in genau denselben Fällen wiederholen, werden zu einem Befund zusammengefasst. |

Zusätzlich gibt es an jedem Befund die Knöpfe **„Ist planmäßig, nicht mehr melden“**
(Nacharbeit) und **„Wartezeit ist gewollt“** (Engpass, z.B. gesetzliche Fristen). Damit
gibt man dem Tool Fachwissen zurück, das es aus den Daten allein nicht haben kann. Gewollte
Wartezeiten zählen dann auch nicht mehr zur Gesamtwartezeit. Bei Sepsis werden danach die
eigentlichen Wartezeiten im Krankenhaus sichtbar, die vorher von der Wiederkehr der
Patienten (im Median 47 Tage) verdeckt waren.

## Ergebnis

Befunde nach Schweregrad (hoch / mittel / niedrig):

| Log | vorher | nachher |
|---|---|---|
| running-example | 3 / 5 / 0 | 2 / 3 / 1 |
| Sepsis | 6 / 1 / 2 | 2 / 2 / 3 |
| Receipt | 2 / 2 / 3 | 1 / 3 / 3 |
| BPI 2012 | 7 / 7 / 0 | 0 / 7 / 5 |
| Helpdesk | 3 / 5 / 1 | 2 / 6 / 1 |
| Hospital Billing | 1 / 6 / 3 | 1 / 5 / 4 |
| Road Traffic Fines | 2 / 2 / 2 | 1 / 3 / 2 |
| **Summe** | **24 / 28 / 11** | **9 / 29 / 19** |

Die Zahl der *hoch*-Befunde ist von 24 auf 9 gesunken. Die weggefallenen waren fast alle
fachlich falsch (Punkte 1–3 und 6). Die verbliebenen sind nachvollziehbar, z.B. die
Wartezeit vor dem Inkasso bei den Bußgeldern (59 % der gesamten Wartezeit).

## Bekannte Grenzen

- **Fachlich gewollte Wartezeiten** (Fristen) kann das Tool nicht selbst erkennen; dafür
  gibt es den Knopf „Wartezeit ist gewollt“. Beispiel Bußgelder: „Insert Fine Notification
  → Add penalty“ dauert fast immer genau 60 Tage, das ist die gesetzliche Zahlungsfrist.
- **Ratenzahlungen** (Bußgelder: „Payment“ mehrfach in 5 % der Fälle) sehen aus wie
  Nacharbeit. Sie liegen unter der 50-%-Schwelle für Routine und müssen bei Bedarf als
  planmäßig markiert werden.
- **Ressourcen in `org:group`** (Sepsis) werden nicht als Personen erkannt, das
  Vier-Augen-Prinzip ist dort nicht prüfbar. Das ist Absicht: Eine Abteilung ist keine Person.

## Performance (Road Traffic Fines, 561.470 Events)

| Schritt | vorher | nachher | Maßnahme |
|---|---:|---:|---|
| XES einlesen | 39,4 s | 6,6 s | schnellerer Parser `rustxes`, Standard-Parser als Rückfall |
| Kennzahlen | 4,7 s | 0,01 s | beim Import einmal berechnet und gespeichert |
| Varianten | 4,4 s | 0,3 s | Aktivitätsfolgen als Zahlenfolgen statt Texte vergleichen |
| Analyse (alle Detektoren) | 9,3 s | 1,4 s | vor allem durch die schnelleren Varianten |
| Prozesslandkarte bei Reglerbewegung | 0,4 s + Laden | 0,04 s | Log und Kanten bleiben im Arbeitsspeicher |

## Speicher

| | vorher | nachher |
|---|---:|---:|
| Road Traffic Fines, einmal hochgeladen | 189 MB | 3 MB |
| dieselbe Datei dreimal hochgeladen | 567 MB | 3 MB |

- Die Originaldatei wird nach dem Einlesen gelöscht, gespeichert bleibt das komprimierte
  Parquet-Log.
- Gleiche Dateien werden am Fingerabdruck (SHA-256) erkannt und nur einmal gespeichert.
- Logs, die 7 Tage nicht benutzt wurden, werden gelöscht (`PI_RETENTION_DAYS`, 0 = nie).
- Der Speicherordner ist auf 2.000 MB begrenzt (`PI_MAX_STORAGE_MB`); darüber werden die am
  längsten unbenutzten Logs entfernt. Das Demo-Log bleibt immer.
- Beim Start werden Duplikate und Originaldateien aus älteren Versionen automatisch
  aufgeräumt.
