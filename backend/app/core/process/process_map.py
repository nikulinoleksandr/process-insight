"""Prozesslandkarte (Directly-Follows-Graph) als Knoten und Kanten für das Frontend."""

import pandas as pd
from pydantic import BaseModel

from app.core.columns import ACTIVITY, CASE
from app.core.process.transitions import transitions

START = "__start__"
END = "__end__"


class Node(BaseModel):
    id: str
    label: str
    count: int
    kind: str  # "activity", "start" oder "end"


class Edge(BaseModel):
    source: str
    target: str
    count: int
    median_wait_seconds: float | None


class ProcessMap(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
    detail: float
    total_edges: int


def build_process_map(log: pd.DataFrame, detail: float = 1.0) -> ProcessMap:
    """Baut die Prozesslandkarte.

    detail zwischen 0 und 1: Anteil aller Übergänge, den die gezeigten Kanten abdecken sollen.
    1.0 zeigt alles, kleinere Werte blenden seltene Pfade aus, damit das Bild lesbar bleibt.
    """
    detail = min(max(detail, 0.0), 1.0)
    edges = _all_edges(log)
    kept = _filter_edges(edges, detail)

    activity_counts = log[ACTIVITY].value_counts()
    ids = set(kept["source"]) | set(kept["target"])
    nodes = [
        Node(id=a, label=a, count=int(activity_counts[a]), kind="activity")
        for a in activity_counts.index
        if a in ids
    ]
    n_cases = int(log[CASE].nunique())
    nodes.insert(0, Node(id=START, label="Start", count=n_cases, kind="start"))
    nodes.append(Node(id=END, label="Ende", count=n_cases, kind="end"))

    return ProcessMap(
        nodes=nodes,
        edges=[
            Edge(
                source=r.source,
                target=r.target,
                count=int(r.count),
                median_wait_seconds=None if pd.isna(r.median_wait) else float(r.median_wait),
            )
            for r in kept.itertuples(index=False)
        ],
        detail=detail,
        total_edges=len(edges),
    )


def _all_edges(log: pd.DataFrame) -> pd.DataFrame:
    tr = transitions(log)
    inner = (
        tr.assign(wait_s=tr["wait"].dt.total_seconds())
        .groupby(["source", "target"], sort=False)
        .agg(count=("case", "size"), median_wait=("wait_s", "median"))
        .reset_index()
    )
    firsts = log.groupby(CASE, sort=False)[ACTIVITY].first().value_counts()
    lasts = log.groupby(CASE, sort=False)[ACTIVITY].last().value_counts()
    start = pd.DataFrame({"source": START, "target": firsts.index, "count": firsts.values})
    end = pd.DataFrame({"source": lasts.index, "target": END, "count": lasts.values})
    all_edges = pd.concat([start, inner, end], ignore_index=True)
    return all_edges.sort_values("count", ascending=False, kind="stable").reset_index(drop=True)


def _filter_edges(edges: pd.DataFrame, detail: float) -> pd.DataFrame:
    if detail >= 1.0 or edges.empty:
        return edges
    share = edges["count"].cumsum() / edges["count"].sum()
    keep = share.shift(fill_value=0) < detail  # immer mindestens die stärkste Kante
    kept_nodes = set(edges.loc[keep, "source"]) | set(edges.loc[keep, "target"])
    # Damit kein Knoten in der Luft hängt: stärkste ein- und ausgehende Kante behalten.
    for node in kept_nodes:
        for col in ("source", "target"):
            idx = edges.index[edges[col] == node]
            if len(idx):
                keep.loc[idx[0]] = True
    return edges[keep].reset_index(drop=True)
