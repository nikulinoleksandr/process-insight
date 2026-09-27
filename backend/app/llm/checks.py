"""Prüft, ob die KI Zahlen verwendet, die in den Kennzahlen nicht vorkommen."""

import json
import re
from typing import Any

from app.llm.schemas import Explanation

_NUMBER = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?")
SMALL_NUMBERS = 10  # "zwei Schritte", "3 Maßnahmen" usw. sind unkritisch


def _to_float(text: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", text):
        text = text.replace(".", "")  # Tausenderpunkte
    return float(text.replace(",", "."))


def numbers_in(text: str) -> list[str]:
    return _NUMBER.findall(text)


def unverified_numbers(explanation: Explanation, payload: dict[str, Any]) -> list[str]:
    allowed = [_to_float(n) for n in numbers_in(json.dumps(payload, ensure_ascii=False))]
    texts = [explanation.headline, explanation.explanation]
    texts += explanation.possible_causes + explanation.next_steps
    found: list[str] = []
    for raw in numbers_in(" ".join(texts)):
        value = _to_float(raw)
        if value <= SMALL_NUMBERS:
            continue
        # Gerundete Angaben ("27 %" statt "26,6 %") gelten als belegt.
        if any(abs(value - a) <= 0.051 or round(a) == value for a in allowed):
            continue
        if raw not in found:
            found.append(raw)
    return found
