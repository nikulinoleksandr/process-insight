"""Datenformate rund um die KI-Erklärungen."""

from typing import Literal

from pydantic import BaseModel, Field


class Explanation(BaseModel):
    """Das, was das Sprachmodell liefern muss. Die API erzwingt genau dieses JSON-Format."""

    headline: str = Field(
        description="Eine kurze Überschrift in Alltagssprache, höchstens 12 Wörter"
    )
    explanation: str = Field(
        description=(
            "2 bis 4 Sätze: Was bedeutet der Befund für das Unternehmen und warum ist er wichtig?"
        )
    )
    possible_causes: list[str] = Field(
        description="2 bis 4 mögliche Ursachen, jeweils ein Satz, klar als Vermutung formuliert"
    )
    next_steps: list[str] = Field(
        description="2 bis 4 konkrete Lösungsvorschläge oder nächste Schritte, jeweils ein Satz"
    )


class ExplanationOut(BaseModel):
    """Was die API an die Oberfläche zurückgibt."""

    source: Literal["ai", "fallback"] = Field(
        description="ai = vom Sprachmodell, fallback = feste Zusammenfassung ohne KI"
    )
    headline: str
    explanation: str
    possible_causes: list[str]
    next_steps: list[str]
    model: str | None = None
    cached: bool = False
    note: str | None = Field(None, description="Hinweis, z.B. warum keine KI verwendet wurde")
    unverified_numbers: list[str] = Field(
        default_factory=list,
        description="Zahlen im KI-Text, die nicht in den gemessenen Kennzahlen vorkommen",
    )
