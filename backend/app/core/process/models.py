"""Prozessmodelle als SVG: BPMN und Petri-Netz.

Beide werden mit dem Inductive Miner aus dem Log entdeckt und von Graphviz
gezeichnet. Anders als die Prozesslandkarte (process_map.py) sind das fertige
Bilder: Sie zeigen auch Entscheidungs- und Parallelitaets-Knoten, lassen sich
dafuer aber nicht im Browser filtern.

Damit alle drei Ansichten gleich aussehen, wird die Vorgabe von pm4py vor dem
Zeichnen auf dieselben Farben und Formen umgestellt wie die Prozesslandkarte.
Die Werte entsprechen den hellen CSS-Variablen in static/index.html; fuer den
Dunkelmodus rechnet die Seite sie um.
"""

import re
from typing import Literal

import pandas as pd
import pm4py
from graphviz import Digraph
from pm4py.visualization.bpmn import visualizer as bpmn_visualizer
from pm4py.visualization.petri_net import visualizer as petri_visualizer

ModelKind = Literal["bpmn", "petri"]

FONT = "Segoe UI,Helvetica,Arial,sans-serif"
NODE_FILL = "#eef2ff"  # Aktivitaeten
NODE_LINE = "#c7d2fe"
CARD = "#ffffff"  # Stellen und Verzweigungen
TEXT = "#1a1d21"
MUTED = "#6b7280"
EDGE = "#94a3b8"
SILENT = "#4b5563"  # unsichtbare Transitionen im Petri-Netz


def render_model(log: pd.DataFrame, kind: ModelKind) -> str:
    """Entdeckt ein Prozessmodell und gibt es als SVG-Text zurueck.

    Graphviz laeuft dabei als eigener Prozess; ohne installiertes Graphviz
    schlaegt der Aufruf fehl.
    """
    if kind == "bpmn":
        graph = bpmn_visualizer.apply(pm4py.discover_bpmn_inductive(log))
    else:
        net, initial, final = pm4py.discover_petri_net_inductive(log)
        graph = petri_visualizer.apply(net, initial, final)
    _restyle(graph)
    return graph.pipe(format="svg").decode("utf-8")


def _set(line: str, **attrs: str) -> str:
    """Setzt Graphviz-Attribute in einer DOT-Zeile, ohne das Label anzufassen."""
    for key, value in attrs.items():
        pattern = re.compile(rf'(?<![\w:]){key}=("[^"]*"|<[^>]*>|[^\s\]]+)')
        if pattern.search(line):
            line = pattern.sub(f'{key}="{value}"', line, count=1)
        else:
            line = line.rstrip().removesuffix("]") + f' {key}="{value}"]'
    return line


def _style_node(line: str) -> str:
    # Schriftgröße der Prozesslandkarte; die großen Marken im Petri-Netz
    # (Token und Endmarkierung) behalten ihre eigene Größe.
    line = line.replace("fontsize=12", "fontsize=13")
    # Reihenfolge zaehlt: Die Farbvorgaben von pm4py sind eindeutiger als die Form.
    if "fillcolor=black" in line:  # unsichtbarer Schritt im Petri-Netz
        return _set(line, fillcolor=SILENT, color=SILENT, style="filled")
    if "fillcolor=green" in line or "fillcolor=orange" in line:
        # Start und Ende: gestrichelt und gedämpft, genau wie in der Prozesslandkarte
        return _set(line, fillcolor=CARD, color=MUTED, style="filled,dashed")
    if "shape=circle" in line or "shape=doublecircle" in line:  # Stelle
        return _set(line, fillcolor=CARD, color=NODE_LINE, style="filled", fontcolor=TEXT)
    if "shape=diamond" in line:  # BPMN-Verzweigung
        return _set(line, fillcolor=CARD, color=NODE_LINE, style="filled", fontcolor=TEXT)
    # Alles Uebrige ist eine Aktivitaet: im BPMN shape=box, im Petri-Netz die
    # sichtbaren Transitionen, die ihre Form aus der node-Vorgabe beziehen.
    return _set(line, fillcolor=NODE_FILL, color=NODE_LINE, style="filled,rounded")


def _restyle(graph: Digraph) -> None:
    """Ersetzt die Vorgabe-Optik von pm4py durch die der Prozesslandkarte."""
    body = [
        # Links nach rechts wie die Prozesslandkarte: Prozesse sind lang und schmal,
        # so passen sie ohne Scrollen auf den Bildschirm.
        "\tgraph [bgcolor=transparent rankdir=LR ranksep=0.4 nodesep=0.26]",
        f'\tnode [fontname="{FONT}" fontsize=13 fontcolor="{TEXT}" penwidth=1.4]',
        f'\tedge [color="{EDGE}" penwidth=1.5 arrowsize=0.7 '
        f'fontname="{FONT}" fontsize=11 fontcolor="{MUTED}"]',
    ]
    for line in graph.body:
        stripped = line.strip()
        if stripped.startswith("graph ["):
            continue  # Hintergrund und Richtung setzen wir selbst
        if stripped.startswith(("node [", "edge [")):
            body.append(line)  # Vorgaben von pm4py behalten, z.B. shape=box im Petri-Netz
            continue
        body.append(_style_node(line) if "->" not in stripped and "[" in stripped else line)
    graph.body = body
