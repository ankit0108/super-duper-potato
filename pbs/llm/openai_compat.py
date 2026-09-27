"""OpenAI-compatible chat completions: Groq, OpenRouter, Cerebras, Mistral, and paid APIs."""

from __future__ import annotations

import base64
import os
import time
from typing import Any

import httpx

from ..settings import ProviderSpec
from .base import LLMError, LLMRequest, LLMResponse, ModelCycle, read_json

_GONE_CODES = {"model_not_found", "model_decommissioned", "model_not_available", "invalid_model"}
_GONE_WORDS = ("decommissioned", "does not exist", "no longer supported", "no longer available", "not a valid model",
               "model not found", "no endpoints found", "unknown model")


class OpenAICompatProvider:
    def __init__(self, name: str, spec: ProviderSpec, client: httpx.Client | None = None):
        self.name = name
        self.spec = spec
        self._client = client
        models = list(dict.fromkeys(m for m in [spec.model, *spec.fallback_models] if m))
        self._cycle = ModelCycle(name, models, spec.quota_per_model)
        self._dropped: set[str] = set()  # optional request fields this provider rejected

    def _key(self) -> str:
        return os.environ.get(self.spec.api_key_env, "").strip() if self.spec.api_key_env else ""

    def available(self) -> bool:
        return bool(self._key()) and bool(self.spec.base_url)

    @property
    def models(self) -> list[str]:
        return self._cycle.models

    @property
    def current_model(self) -> str | None:
        return self._cycle.current

    def generate(self, req: LLMRequest) -> LLMResponse:
        return self._cycle.run(req, lambda model: self._generate(model, req))

    def _body(self, model: str, req: LLMRequest) -> dict[str, Any]:
        if req.images:
            content: list[dict] | str = [{"type": "text", "text": req.prompt}]
            for data, mime in req.images:
                b64 = base64.b64encode(data).decode("ascii")
                content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        else:
            content = req.prompt
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": content})
        body: dict[str, Any] = {"model": model, "messages": messages,
                                "max_tokens": req.max_output_tokens + self.spec.output_headroom}
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if req.json_mode:
            body["response_format"] = {"type": "json_object"}
        body.update(self.spec.extra_body)
        for key in self._dropped:
            body.pop(key, None)
        return body

    def _generate(self, model: str, req: LLMRequest) -> LLMResponse:
        headers = {"Authorization": f"Bearer {self._key()}", "Content-Type": "application/json"}
        if "openrouter.ai" in (self.spec.base_url or ""):
            headers["X-Title"] = "PBS"
        url = f"{self.spec.base_url.rstrip('/')}/chat/completions"  # type: ignore[union-attr]
        started = time.monotonic()
        client = self._client or httpx.Client(timeout=120)
        try:
            resp = client.post(url, json=self._body(model, req), headers=headers)
            # Some models reject JSON mode or a provider-specific field: drop it, ask once more, remember.
            optional = ["response_format", *self.spec.extra_body]
            rejected = [k for k in optional if k not in self._dropped and k in resp.text] if resp.status_code == 400 else []
            if rejected:
                self._dropped.update(rejected)
                resp = client.post(url, json=self._body(model, req), headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"network error: {type(exc).__name__}", code="network", retryable=True) from exc
        finally:
            if self._client is None:
                client.close()
        latency = int((time.monotonic() - started) * 1000)
        if resp.status_code != 200:
            raise _classify(resp)
        data = read_json(resp)
        if isinstance(data.get("error"), dict):  # some gateways report upstream failures with HTTP 200
            raise _from_error(200, data["error"], resp)
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("no choices in response", status=200, code="no_choices", retryable=True)
        msg = choices[0].get("message") or {}
        text = msg.get("content") or ""
        if isinstance(text, list):
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        if not text.strip():
            raise LLMError("empty output", status=200, code=str(choices[0].get("finish_reason") or "empty"),
                           retryable=True)
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=str(data.get("model") or model),
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            finish_reason=choices[0].get("finish_reason"),
            latency_ms=latency,
        )


def _classify(resp: httpx.Response) -> LLMError:
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    err = payload.get("error", payload) if isinstance(payload, dict) else None
    if not isinstance(err, dict):
        err = {"message": str(err) if err else resp.text[:300]}
    return _from_error(resp.status_code, err, resp)


def _from_error(status: int, err: dict[str, Any], resp: httpx.Response) -> LLMError:
    message = str(err.get("message") or err.get("code") or resp.text[:300])
    low = message.lower()
    raw_code = err.get("code") if isinstance(err.get("code"), str) else err.get("type")
    code = str(raw_code) if raw_code else None
    if status == 200 and isinstance(err.get("code"), int):
        status = int(err["code"])
    retry_after = None
    ra = resp.headers.get("retry-after")
    if ra:
        try:
            retry_after = float(ra)
        except ValueError:
            retry_after = None
    if status == 429:
        daily_markers = ("86400", "per day", "userbymodelbyday", "rpd", "per-day", "free-models-per-day", "daily",
                         "tokens per day", "(tpd)")
        if any(m in low for m in daily_markers) or (retry_after is not None and retry_after > 3600):
            return LLMError(f"daily quota reached: {message[:200]}", status=status, code=code, quota=True)
        return LLMError(f"rate limited: {message[:200]}", status=status, code=code, rate_limited=True,
                        retryable=True, retry_after=retry_after or 15.0)
    if status in (500, 502, 503, 504, 529):
        return LLMError(f"server error {status}", status=status, code=code, retryable=True, retry_after=retry_after)
    if status == 404 or code in _GONE_CODES or (status == 400 and any(w in low for w in _GONE_WORDS)):
        return LLMError(f"model not available: {message[:200]}", status=status, code=code, model_gone=True)
    if status in (401, 403):
        return LLMError(f"key rejected {status}: {message[:200]}", status=status, code=code, fatal_for_provider=True)
    if 300 <= status < 400 or status == 410:
        return LLMError(f"endpoint moved or gone ({status})", status=status, code=code, fatal_for_provider=True)
    if status == 413 or "too large" in low or "context length" in low or "max_tokens" in low:
        return LLMError(f"request too large: {message[:200]}", status=status, code=code or "too_large")
    return LLMError(f"error {status}: {message[:300]}", status=status, code=code)
