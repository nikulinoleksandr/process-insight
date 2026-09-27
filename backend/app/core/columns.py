"""Namen der Standardspalten. Wir nutzen die PM4Py-Konvention, damit keine Umwandlung nötig ist."""

CASE = "case:concept:name"
ACTIVITY = "concept:name"
TIMESTAMP = "time:timestamp"
RESOURCE = "org:resource"
LIFECYCLE = "lifecycle:transition"

REQUIRED_COLUMNS = (CASE, ACTIVITY, TIMESTAMP)
