"""The call to Gemini: request shape, error mapping and the model fallback order.

No request leaves the machine: extract._client is replaced by a stub whose
post() returns canned responses.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

import extract
from extract import ExtractionError, load_image
from helpers import PAGE_1, load_report
from test_extract import photo

FIRST, SECOND = "model-a", "model-b"


def ok(report=None, finish="STOP", text=None) -> httpx.Response:
    text = text if text is not None else (report or load_report(PAGE_1)).model_dump_json()
    return httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
        "usageMetadata": {"promptTokenCount": 3698, "candidatesTokenCount": 2497},
        "modelVersion": "served-model",
    })


def error(status: int, message: str) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": status, "message": message}})


class StubClient:
    """Answers post() from a queue; an exception in the queue is raised."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls: list[dict] = []

    async def post(self, url, headers=None, json=None):
        self.calls.append({"model": url.split("/models/")[1].split(":")[0], "headers": headers, "body": json})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(extract, "MODELS", [FIRST, SECOND])

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(extract.asyncio, "sleep", no_wait)

    def install(*answers) -> StubClient:
        stub = StubClient(answers)
        monkeypatch.setattr(extract, "_client", lambda: stub)
        return stub

    return install


def read(**kwargs):
    return asyncio.run(extract.extract_report(load_image(photo((1119, 1599))), **kwargs))


def models_called(stub: StubClient) -> list[str]:
    return [c["model"] for c in stub.calls]


def test_request_carries_the_page_schema_and_key(gemini):
    stub = gemini(ok())
    result = read()
    assert result.report == load_report(PAGE_1)
    assert result.model == "served-model"
    assert result.usage == {"inputTokens": 3698, "outputTokens": 2497, "thinkingTokens": None}

    call = stub.calls[0]
    assert call["model"] == FIRST
    assert call["headers"] == {"x-goog-api-key": "test-key"}
    parts = call["body"]["contents"][0]["parts"]
    assert [("inlineData" in p) for p in parts] == [True, True, True, False]
    assert all(p["inlineData"]["mimeType"] == "image/jpeg" for p in parts[:3])
    config = call["body"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert "Daily System Report" in call["body"]["systemInstruction"]["parts"][0]["text"]


def test_schema_is_in_the_dialect_gemini_accepts():
    schema = extract._SCHEMA
    flat = json.dumps(schema)
    assert "$ref" not in flat and "$defs" not in flat
    assert schema["type"] == "OBJECT"
    # Cells come back in page order, starting with the two header fields.
    assert schema["propertyOrdering"][:2] == ["is_daily_system_report", "report_date"]
    assert schema["propertyOrdering"] == list(schema["properties"])
    assert set(schema["required"]) == set(schema["properties"])
    gen = schema["properties"]["r04_gen"]
    assert gen["type"] == "OBJECT" and gen["propertyOrdering"] == ["unit1", "unit2", "station"]
    assert "S.No 4" in gen["description"]
    assert schema["properties"]["unclear_cells"]["items"] == {"type": "STRING"}


def test_recheck_hints_are_put_in_the_prompt(gemini):
    stub = gemini(ok())
    read(recheck=["Generation: 3.43 + 3.68 = 7.11, page shows 7.16"])
    prompt = stub.calls[0]["body"]["contents"][0]["parts"][-1]["text"]
    assert "did not add up" in prompt and "3.43 + 3.68 = 7.11" in prompt


def test_overloaded_model_is_retried_then_the_next_model_is_used(gemini):
    stub = gemini(error(503, "high demand"), error(503, "high demand"), ok())
    assert read().report.report_date == "4/11/26"
    assert models_called(stub) == [FIRST, FIRST, SECOND]


@pytest.mark.parametrize("failure", [
    error(429, "You exceeded your current quota"),
    error(404, "models/model-a is not found"),
    httpx.ReadTimeout("timed out"),
])
def test_quota_missing_model_or_timeout_moves_straight_to_the_next_model(gemini, failure):
    stub = gemini(failure, ok())
    read()
    assert models_called(stub) == [FIRST, SECOND]


@pytest.mark.parametrize("bad", [
    ok(text="{not json"),
    ok(text='{"is_daily_system_report": true}'),
    ok(finish="MAX_TOKENS"),
    ok(text=""),
])
def test_unusable_answer_is_retried(gemini, bad):
    stub = gemini(bad, ok())
    read()
    assert models_called(stub) == [FIRST, FIRST]


def test_every_model_failing_reports_the_last_reason(gemini):
    stub = gemini(error(503, "high demand"), error(503, "high demand"), error(429, "quota"))
    with pytest.raises(ExtractionError) as err:
        read()
    assert err.value.status == 502
    assert "model-b" in str(err.value) and "quota" in str(err.value)
    assert models_called(stub) == [FIRST, FIRST, SECOND]


def test_rejected_key_fails_at_once(gemini):
    stub = gemini(error(400, "API key not valid. Please pass a valid API key."))
    with pytest.raises(ExtractionError) as err:
        read()
    assert err.value.status == 503 and "GEMINI_API_KEY" in str(err.value)
    assert len(stub.calls) == 1


def test_blocked_image_is_not_retried(gemini):
    stub = gemini(httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(ExtractionError) as err:
        read()
    assert err.value.status == 422
    assert len(stub.calls) == 1


def test_an_explicit_model_is_the_only_one_tried(gemini):
    stub = gemini(error(429, "quota"))
    with pytest.raises(ExtractionError):
        read(model="model-x")
    assert models_called(stub) == ["model-x"]
