"""OpenAI-compatible chat completions: GitHub Models, Groq, OpenRouter, Cerebras, Mistral, and paid APIs."""

from __future__ import annotations

import base64
import os
import time

import httpx

from ..settings import ProviderSpec
from .base import LLMError, LLMRequest, LLMResponse


class OpenAICompatProvider:
    def __init__(self, name: str, spec: ProviderSpec, client: httpx.Client | None = None):
        self.name = name
        self.spec = spec
        self._client = client
        self._json_mode_ok = True

    def _key(self) -> str:
        return os.environ.get(self.spec.api_key_env, "").strip() if self.spec.api_key_env else ""

    def available(self) -> bool:
        return bool(self._key()) and bool(self.spec.base_url)

    def generate(self, req: LLMRequest) -> LLMResponse:
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
        body: dict = {"model": self.spec.model, "messages": messages, "max_tokens": req.max_output_tokens}
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if req.json_mode and self._json_mode_ok:
            body["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self._key()}", "Content-Type": "application/json"}
        if "models.github.ai" in (self.spec.base_url or ""):
            headers["Accept"] = "application/vnd.github+json"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        if "openrouter.ai" in (self.spec.base_url or ""):
            headers["X-Title"] = "PBS"

        url = f"{self.spec.base_url.rstrip('/')}/chat/completions"  # type: ignore[union-attr]
        started = time.monotonic()
        client = self._client or httpx.Client(timeout=120)
        try:
            resp = client.post(url, json=body, headers=headers)
            if resp.status_code == 400 and "response_format" in resp.text and self._json_mode_ok:
                # Some models reject JSON mode; retry once without it and remember.
                self._json_mode_ok = False
                body.pop("response_format", None)
                resp = client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"network error: {type(exc).__name__}", retryable=True) from exc
        finally:
            if self._client is None:
                client.close()
        latency = int((time.monotonic() - started) * 1000)
        if resp.status_code != 200:
            raise _classify(resp)
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("no choices in response", status=200, retryable=True)
        msg = choices[0].get("message") or {}
        text = msg.get("content") or ""
        if isinstance(text, list):
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        if not text.strip():
            raise LLMError("empty output", status=200, retryable=True)
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=str(data.get("model") or self.spec.model),
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            finish_reason=choices[0].get("finish_reason"),
            latency_ms=latency,
        )


def _classify(resp: httpx.Response) -> LLMError:
    status = resp.status_code
    try:
        payload = resp.json()
        err = payload.get("error", payload) if isinstance(payload, dict) else {}
        message = str(err.get("message") or err.get("code") or resp.text[:300]) if isinstance(err, dict) else str(err)
    except ValueError:
        message = resp.text[:300]
    low = message.lower()
    retry_after = None
    ra = resp.headers.get("retry-after")
    if ra:
        try:
            retry_after = float(ra)
        except ValueError:
            retry_after = None
    if status == 429:
        daily_markers = ("86400", "per day", "userbymodelbyday", "rpd", "per-day", "free-models-per-day", "daily")
        if any(m in low for m in daily_markers) or (retry_after is not None and retry_after > 3600):
            return LLMError(f"daily quota reached: {message[:200]}", status=status, quota=True)
        return LLMError(f"rate limited: {message[:200]}", status=status, rate_limited=True, retryable=True,
                        retry_after=retry_after or 15.0)
    if status in (500, 502, 503, 504, 529):
        return LLMError(f"server error {status}", status=status, retryable=True, retry_after=retry_after)
    if status in (401, 403):
        return LLMError(f"auth error {status}: {message[:200]}", status=status, fatal_for_provider=True)
    if status == 404:
        return LLMError(f"model not found: {message[:200]}", status=status, fatal_for_provider=True)
    if status == 413 or "too large" in low or "context length" in low or "max_tokens" in low:
        return LLMError(f"request too large: {message[:200]}", status=status)
    return LLMError(f"error {status}: {message[:300]}", status=status)
