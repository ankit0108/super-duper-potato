"""Providers against the shapes of real replies, offline: model discovery, retired models, per-model quotas,
unreadable bodies (a retired API answering 200 with a web page) and fields a model rejects."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from pbs.llm.base import LLMError, LLMRequest
from pbs.llm.gemini import GeminiProvider, pick_models
from pbs.llm.openai_compat import OpenAICompatProvider
from pbs.settings import ProviderSpec

GEN = ["generateContent", "countTokens"]
LISTING = [
    {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": GEN},
    {"name": "models/gemini-3.6-flash", "supportedGenerationMethods": GEN},
    {"name": "models/gemini-3.6-flash-001", "supportedGenerationMethods": GEN},
    {"name": "models/gemini-3.8-flash-preview", "supportedGenerationMethods": GEN},
    {"name": "models/gemini-3.5-flash", "supportedGenerationMethods": GEN},
    {"name": "models/gemini-3-flash", "supportedGenerationMethods": GEN},
    {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": GEN},
    {"name": "models/gemini-3.1-flash-lite", "supportedGenerationMethods": GEN},
    {"name": "models/gemini-3.6-flash-image", "supportedGenerationMethods": GEN},
    {"name": "models/gemini-3.5-flash-preview-tts", "supportedGenerationMethods": GEN},
    {"name": "models/gemini-3.1-pro", "supportedGenerationMethods": GEN},
    {"name": "models/gemini-live-3.6-flash", "supportedGenerationMethods": ["bidiGenerateContent"]},
    {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
]


def gemini_reply(text: str, model: str) -> dict[str, Any]:
    return {"candidates": [{"content": {"parts": [{"text": text}], "role": "model"}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 5, "thoughtsTokenCount": 30},
            "modelVersion": model}


DAILY_QUOTA = {"error": {
    "code": 429, "status": "RESOURCE_EXHAUSTED",
    "message": "You exceeded your current quota. Quota exceeded for metric: "
               "generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20",
    "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{
        "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "36s"}]}}
NOT_FOUND = {"error": {"code": 404, "status": "NOT_FOUND",
                       "message": "models/x is not found for API version v1beta, or is not supported for "
                                  "generateContent. Call ListModels to see the list of available models."}}
BAD_KEY = {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "API key not valid. Please pass a valid API key.",
                     "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID",
                                  "domain": "googleapis.com"}]}}
HTML = "<!DOCTYPE html><html><body>This service has been retired.</body></html>"


class FakeGemini:
    """Routes models.list and generateContent; `behaviour[model]` is a reply dict, (status, body) or a callable."""

    def __init__(self, behaviour: dict[str, Any], listing: list[dict[str, Any]] | None = None):
        self.behaviour = behaviour
        self.listing = LISTING if listing is None else listing
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "k"
        path = request.url.path
        if request.method == "GET" and path.endswith("/models"):
            self.calls.append(("list", None))
            return httpx.Response(200, json={"models": self.listing})
        model = path.rsplit("/", 1)[1].split(":")[0]
        body = json.loads(request.content)
        self.calls.append((model, body))
        out = self.behaviour.get(model, (404, NOT_FOUND))
        if callable(out):
            out = out(body)
        status, payload = out if isinstance(out, tuple) else (200, out)
        if isinstance(payload, str):
            return httpx.Response(status, text=payload, headers={"content-type": "text/html; charset=utf-8"})
        return httpx.Response(status, json=payload)

    @property
    def generated(self) -> list[str]:
        return [m for m, _ in self.calls if m != "list"]


def gemini(fake: FakeGemini, model: str = "auto:flash", **kw: Any) -> GeminiProvider:
    spec = ProviderSpec(kind="gemini", model=model, api_key_env="TEST_GEMINI_KEY", quota_per_model=True,
                        output_headroom=kw.pop("output_headroom", 4096), **kw)
    return GeminiProvider("gemini", spec, client=httpx.Client(transport=httpx.MockTransport(fake)))


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setenv("TEST_GEMINI_KEY", "k")
    monkeypatch.setenv("TEST_OPENAI_KEY", "k")


REQ = LLMRequest(task="draft", system="Be brief.", prompt='Reply with {"ok": true}', max_output_tokens=300,
                 temperature=0.8)


def test_discovery_picks_the_newest_stable_models_of_a_family_then_previews():
    assert pick_models(LISTING, "flash", limit=10) == [
        "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3-flash", "gemini-2.5-flash", "gemini-3.8-flash-preview"]
    assert pick_models(LISTING, "flash")[:2] == ["gemini-3.6-flash", "gemini-3.5-flash"]
    assert pick_models(LISTING, "flash-lite") == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]


def test_gemini_moves_to_the_next_model_on_daily_quota_and_retirement():
    fake = FakeGemini({"gemini-3.6-flash": (429, DAILY_QUOTA), "gemini-3.5-flash": (404, NOT_FOUND),
                       "gemini-3-flash": gemini_reply('{"ok": true}', "gemini-3-flash")})
    p = gemini(fake)
    resp = p.generate(REQ)
    assert json.loads(resp.text) == {"ok": True} and resp.model == "gemini-3-flash"
    assert fake.generated == ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3-flash"]
    p.generate(REQ)  # the next call goes straight to the model that works, without listing again
    assert fake.generated[-1] == "gemini-3-flash" and [m for m, _ in fake.calls].count("list") == 1


def test_gemini_quota_on_the_last_model_is_reported_as_quota():
    fake = FakeGemini({}, listing=[{"name": "models/gemini-3.6-flash", "supportedGenerationMethods": GEN}])
    fake.behaviour["gemini-3.6-flash"] = (429, DAILY_QUOTA)
    with pytest.raises(LLMError) as err:
        gemini(fake).generate(REQ)
    assert err.value.quota and err.value.public() == "daily quota reached (HTTP 429 RESOURCE_EXHAUSTED)"


def test_a_pinned_model_that_was_retired_falls_back_to_current_models():
    fake = FakeGemini({"gemini-2.0-flash": (404, NOT_FOUND),
                       "gemini-3.6-flash": gemini_reply('{"ok": true}', "gemini-3.6-flash")})
    resp = gemini(fake, model="gemini-2.0-flash").generate(REQ)
    assert resp.model == "gemini-3.6-flash" and fake.generated == ["gemini-2.0-flash", "gemini-3.6-flash"]


def test_a_web_page_instead_of_json_is_a_provider_error_not_a_crash():
    fake = FakeGemini({"gemini-3.6-flash": (200, HTML)})
    with pytest.raises(LLMError) as err:
        gemini(fake).generate(REQ)
    assert err.value.fatal_for_provider and err.value.code == "bad_body"
    assert err.value.public() == "unreadable response (HTTP 200)" and "text/html" in str(err.value)


def test_an_invalid_key_switches_the_provider_off_with_a_public_code():
    fake = FakeGemini({"gemini-3.6-flash": (400, BAD_KEY)})
    with pytest.raises(LLMError) as err:
        gemini(fake).generate(REQ)
    assert err.value.fatal_for_provider and err.value.public() == "key rejected (HTTP 400 API_KEY_INVALID)"
    assert "valid" not in err.value.public()  # provider messages stay out of public logs


def test_gemini_3_keeps_its_default_temperature_and_thinks_lightly():
    fake = FakeGemini({"gemini-3.6-flash": gemini_reply("{}", "gemini-3.6-flash"),
                       "gemini-2.5-flash": gemini_reply("{}", "gemini-2.5-flash")})
    gemini(fake).generate(REQ)
    gen = fake.calls[-1][1]["generationConfig"]
    assert "temperature" not in gen and gen["thinkingConfig"] == {"thinkingLevel": "LOW"}
    assert gen["maxOutputTokens"] == 300 + 4096 and gen["responseMimeType"] == "application/json"
    gemini(fake, model="gemini-2.5-flash").generate(REQ)
    gen = fake.calls[-1][1]["generationConfig"]
    assert gen["temperature"] == 0.8 and "thinkingConfig" not in gen


def test_gemini_retries_without_thinking_config_when_a_model_rejects_it():
    def reply(body):
        if "thinkingConfig" in body["generationConfig"]:
            return 400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                   "message": 'Invalid JSON payload received. Unknown name "thinkingLevel"'}}
        return gemini_reply("{}", "gemini-3.6-flash")

    fake = FakeGemini({"gemini-3.6-flash": reply})
    p = gemini(fake)
    p.generate(REQ)
    p.generate(REQ)
    assert len(fake.generated) == 3  # one rejected, then without it from then on


# -- OpenAI-compatible (Groq, OpenRouter) -----------------------------------------------------------------


def chat_reply(text: str, model: str) -> dict[str, Any]:
    return {"id": "chatcmpl-1", "model": model, "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": text}}], "usage": {"prompt_tokens": 9, "completion_tokens": 3}}


def openai(handler, **kw: Any) -> OpenAICompatProvider:
    spec = ProviderSpec(kind="openai", base_url="https://api.example.test/openai/v1", api_key_env="TEST_OPENAI_KEY",
                        **{"model": "openai/gpt-oss-120b", **kw})
    return OpenAICompatProvider("groq", spec, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_a_decommissioned_model_hands_over_to_the_fallback_model():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["model"])
        if body["model"] == "llama-3.3-70b-versatile":
            return httpx.Response(400, json={"error": {
                "message": "The model `llama-3.3-70b-versatile` has been decommissioned and is no longer supported.",
                "type": "invalid_request_error", "code": "model_decommissioned"}})
        return httpx.Response(200, json=chat_reply('{"ok": true}', body["model"]))

    p = openai(handler, model="llama-3.3-70b-versatile", fallback_models=["openai/gpt-oss-120b"])
    assert p.generate(REQ).model == "openai/gpt-oss-120b"
    p.generate(REQ)
    assert seen == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-120b"]


def test_optional_fields_a_model_rejects_are_dropped_and_remembered():
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "reasoning_effort" in body:
            return httpx.Response(400, json={"error": {"message": "`reasoning_effort` is not supported with this model",
                                                       "type": "invalid_request_error"}})
        return httpx.Response(200, json=chat_reply("{}", body["model"]))

    p = openai(handler, extra_body={"reasoning_effort": "low"}, output_headroom=1024)
    p.generate(REQ)
    p.generate(REQ)
    assert ["reasoning_effort" in b for b in bodies] == [True, False, False]
    assert bodies[-1]["response_format"] == {"type": "json_object"} and bodies[-1]["max_tokens"] == 300 + 1024


def test_a_web_page_with_http_200_is_an_error_not_a_crash():
    p = openai(lambda r: httpx.Response(200, text=HTML, headers={"content-type": "text/html"}))
    with pytest.raises(LLMError) as err:
        p.generate(REQ)
    assert err.value.code == "bad_body" and err.value.fatal_for_provider


def test_an_error_object_inside_http_200_is_classified():
    p = openai(lambda r: httpx.Response(200, json={"error": {"code": 429, "message":
                                                              "Rate limit exceeded: free-models-per-day"}}))
    with pytest.raises(LLMError) as err:
        p.generate(REQ)
    assert err.value.quota and err.value.status == 429


def test_an_expired_key_is_fatal_for_the_provider():
    p = openai(lambda r: httpx.Response(401, json={"error": {"message": "Invalid API Key",
                                                             "type": "invalid_request_error",
                                                             "code": "invalid_api_key"}}))
    with pytest.raises(LLMError) as err:
        p.generate(REQ)
    assert err.value.fatal_for_provider and err.value.public() == "key rejected (HTTP 401 invalid_api_key)"


def test_a_failed_model_listing_is_retried_rather_than_remembered():
    state = {"n": 0}
    fake = FakeGemini({"gemini-3.6-flash": gemini_reply("{}", "gemini-3.6-flash")})

    def flaky(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and state["n"] == 0:
            state["n"] += 1
            raise httpx.ConnectTimeout("timed out", request=request)
        return fake(request)

    spec = ProviderSpec(kind="gemini", model="auto:flash", api_key_env="TEST_GEMINI_KEY")
    p = GeminiProvider("gemini", spec, client=httpx.Client(transport=httpx.MockTransport(flaky)))
    with pytest.raises(LLMError) as err:
        p.generate(REQ)
    assert err.value.retryable and err.value.public() == "network error"
    assert p.generate(REQ).model == "gemini-3.6-flash"


def test_an_overloaded_newest_model_hands_over_to_the_next_one():
    busy = {"error": {"code": 503, "status": "UNAVAILABLE", "message": "The model is overloaded. Please try again later."}}
    fake = FakeGemini({"gemini-3.6-flash": (503, busy),
                       "gemini-3.5-flash": gemini_reply('{"ok": true}', "gemini-3.5-flash")})
    p = gemini(fake)
    assert p.generate(REQ).model == "gemini-3.5-flash"
    assert p.generate(REQ).model == "gemini-3.5-flash"
    assert fake.generated == ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash"]
