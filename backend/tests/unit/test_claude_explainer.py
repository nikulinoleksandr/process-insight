"""Prüft die Anbindung an die Claude API, ohne echtes Netz: Die HTTP-Antworten kommen
aus einem simulierten Server (MockTransport)."""

import json

import httpx2 as httpx  # das Claude-SDK nutzt httpx2 statt httpx
import pytest

from app.llm.explainer import ClaudeExplainer, ExplainerError

ANSWER = {
    "headline": "Viele Anträge werden doppelt geprüft",
    "explanation": "Ein Drittel der Fälle durchläuft die Prüfung mehrfach.",
    "possible_causes": ["Möglicherweise sind Anträge anfangs unvollständig."],
    "next_steps": ["Eine Pflichtfeld-Prüfung beim Einreichen einführen."],
}


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _message(text: str) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def test_sends_schema_and_parses_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_message(json.dumps(ANSWER)))

    explainer = ClaudeExplainer("test-key", "test-model", http_client=_client(handler))
    result = explainer.explain({"befund": {"titel": "Nacharbeit"}})

    assert result.headline == ANSWER["headline"]
    body = seen["body"]
    assert body["model"] == "test-model"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "<daten>" in body["messages"][0]["content"]
    assert "Nacharbeit" in body["messages"][0]["content"]


def test_api_error_becomes_explainer_error():
    def handler(request: httpx.Request) -> httpx.Response:
        error = {"type": "authentication_error", "message": "invalid x-api-key"}
        return httpx.Response(401, json={"type": "error", "error": error})

    explainer = ClaudeExplainer("wrong", "test-model", http_client=_client(handler))
    with pytest.raises(ExplainerError, match="nicht erreichbar"):
        explainer.explain({"befund": {}})
