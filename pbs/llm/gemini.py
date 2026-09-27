"""Google Gemini (AI Studio API key) over REST. No SDK needed."""

from __future__ import annotations

import base64
import os
import re
import time

import httpx

from ..settings import ProviderSpec
from .base import LLMError, LLMRequest, LLMResponse

API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    def __init__(self, name: str, spec: ProviderSpec, client: httpx.Client | None = None):
        self.name = name
        self.spec = spec
        self._client = client

    def _key(self) -> str:
        return os.environ.get(self.spec.api_key_env or "GEMINI_API_KEY", "").strip()

    def available(self) -> bool:
        return bool(self._key())

    def generate(self, req: LLMRequest) -> LLMResponse:
        parts: list[dict] = [{"text": req.prompt}]
        for data, mime in req.images:
            parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode("ascii")}})
        gen: dict = {"maxOutputTokens": req.max_output_tokens}
        if req.temperature is not None:
            gen["temperature"] = req.temperature
        body: dict = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": gen,
        }
        if req.system:
            body["systemInstruction"] = {"parts": [{"text": req.system}]}
        if req.grounding:
            body["tools"] = [{"googleSearch": {}}]
        elif req.json_mode:
            gen["responseMimeType"] = "application/json"

        base = (self.spec.base_url or API_BASE).rstrip("/")
        url = f"{base}/models/{self.spec.model}:generateContent"
        started = time.monotonic()
        client = self._client or httpx.Client(timeout=120)
        try:
            resp = client.post(url, json=body, headers={"x-goog-api-key": self._key()})
        except httpx.HTTPError as exc:
            raise LLMError(f"network error: {type(exc).__name__}", retryable=True) from exc
        finally:
            if self._client is None:
                client.close()
        latency = int((time.monotonic() - started) * 1000)
        if resp.status_code != 200:
            raise _classify(resp)
        data = resp.json()
        cands = data.get("candidates") or []
        if not cands:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            raise LLMError(f"no candidates (blocked: {block})", status=200)
        cand = cands[0]
        text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
        usage = data.get("usageMetadata") or {}
        grounding = []
        for chunk in (cand.get("groundingMetadata") or {}).get("groundingChunks", []) or []:
            web = chunk.get("web") or {}
            if web.get("uri"):
                grounding.append({"url": web["uri"], "title": web.get("title", "")})
        finish = cand.get("finishReason")
        if not text.strip():
            raise LLMError(f"empty output (finish={finish})", status=200, retryable=finish != "SAFETY")
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.spec.model,
            tokens_in=int(usage.get("promptTokenCount") or 0),
            tokens_out=int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0),
            grounding=grounding,
            finish_reason=finish,
            latency_ms=latency,
        )


def _classify(resp: httpx.Response) -> LLMError:
    status = resp.status_code
    try:
        err = resp.json().get("error", {})
    except ValueError:
        err = {}
    message = str(err.get("message") or resp.text[:300])
    details = err.get("details") or []
    retry_after = None
    daily = False
    for d in details:
        typ = d.get("@type", "")
        if typ.endswith("RetryInfo"):
            m = re.match(r"([\d.]+)s", str(d.get("retryDelay", "")))
            if m:
                retry_after = float(m.group(1))
        if typ.endswith("QuotaFailure"):
            for v in d.get("violations", []):
                qid = str(v.get("quotaId", "")) + str(v.get("quotaMetric", ""))
                if "PerDay" in qid or "per_day" in qid.lower():
                    daily = True
    if status == 429:
        if daily or "per day" in message.lower():
            return LLMError(f"daily quota reached: {message[:200]}", status=status, quota=True)
        return LLMError(f"rate limited: {message[:200]}", status=status, rate_limited=True, retryable=True,
                        retry_after=retry_after or 20.0)
    if status in (500, 502, 503, 504):
        return LLMError(f"server error {status}", status=status, retryable=True, retry_after=retry_after)
    if status in (401, 403):
        return LLMError(f"auth error {status}: {message[:200]}", status=status, fatal_for_provider=True)
    if status == 404:
        return LLMError(f"model not found: {message[:200]}", status=status, fatal_for_provider=True)
    return LLMError(f"error {status}: {message[:300]}", status=status)
