# Vision: Process Insight

## Was ist das Tool?
Process Insight macht sichtbar, wie komplizierte Abläufe in einem Unternehmen oder einem Amt (Produktion, Sachbearbeitung, Einkauf, Logistik usw.) wirklich ablaufen, und findet automatisch die Schwachstellen darin. Grundlage sind Event-Logs, also die Spuren, die jeder Arbeitsschritt in IT-Systemen hinterlässt.

## Für wen ist es?
Für Prozessverantwortliche und Analysten in kleinen und mittleren Unternehmen oder Behörden, die wissen wollen, warum ein Prozess langsam oder fehleranfällig ist, aber kein Budget und keine Zeit für große Process-Mining-Plattformen haben.

## Welches Problem löst es?
Prozesse laufen im Alltag oft unordentlich, unstrukturiert und ohne dass jemand den Gesamtablauf kennt. Dadurch sind sie ineffizient: Schritte werden wiederholt, Fälle bleiben liegen, Regeln wie das Vier-Augen-Prinzip werden verletzt.

Ein Prozessgraph allein hilft dabei wenig. Bei echten Daten wird er schnell zu einem unlesbaren "Spaghetti-Modell". Process Insight zeigt deshalb nicht nur den Prozess, sondern weist gezielt auf die Probleme hin und belegt jede Aussage mit den betroffenen Fällen.

## Bestehende Lösungen und Abgrenzung
- **Celonis, SAP Signavio, UiPath:** sehr mächtig, aber teuer und für große Unternehmen gedacht.
- **Disco, Apromore (Community Edition):** gut für die Visualisierung, zeigen aber kaum von selbst, wo die Probleme liegen.
- **Process Insight:** kostenlos und ohne Einarbeitung nutzbar. Der Schwerpunkt liegt auf automatisch gefundenen, nachvollziehbaren Hinweisen statt auf manueller Analyse.

## Features in Version 1
- Event-Logs als XES- oder CSV-Datei hochladen, bei CSV mit Spaltenzuordnung
- Kennzahlen: Fälle, Events, Varianten, Durchlaufzeiten
- Prozessmodell ansehen: Prozesslandkarte mit Detailregler, BPMN und Petri-Netz
- Automatische Schwachstellenanalyse mit fünf Detektoren: Nacharbeit, Engpässe, lange Durchlaufzeiten, Vier-Augen-Prinzip, seltene Varianten
- Jede gefundene Schwachstelle ist nachvollziehbar: verständliche Kennzahlen, Liste der betroffenen Fälle, Hervorhebung im Prozessmodell
- Einstellungen für die Analyse, z.B. eine Frist in Tagen oder die Aktivitätspaare für das Vier-Augen-Prinzip

## Nicht in Version 1
- KI-Erklärungen der Schwachstellen (geplant für Version 2)
- Benutzerkonten und Logins
- Eigene Process-Mining-Algorithmen (dafür nutzen wir PM4Py)
- Direkte Anbindung an Unternehmenssysteme wie SAP
- Echtzeitdaten

## Woran erkenne ich, dass ich fertig bin?
- Ich kann ein echtes Log (z.B. BPI Challenge 2019) hochladen, und das Tool zeigt mindestens drei nachvollziehbare Schwachstellen mit verständlicher Erklärung.
- Die automatischen Tests laufen bei jedem Push erfolgreich durch.
- Das Tool ist online erreichbar und lässt sich mit dem Demo-Log ohne eigene Daten ausprobieren.
