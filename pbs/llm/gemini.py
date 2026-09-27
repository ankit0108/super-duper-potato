"""Google Gemini (AI Studio API key) over REST. No SDK needed.

Gemini model names change every few months and the free tier's quotas are per model. So a model of
`auto:flash` or `auto:flash-lite` resolves, once per run, to the newest stable models of that family the
key can call (previews last). When a model is retired, or reaches its daily quota, the next one takes over.
"""

from __future__ import annotations

import base64
import os
import re
import time
from typing import Any

import httpx

from .. import log
from ..settings import ProviderSpec
from .base import LLMError, LLMRequest, LLMResponse, read_json, rotates

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
MAX_AUTO_MODELS = 4
_NAME_RE = re.compile(r"^gemini-(?P<ver>\d+(?:\.\d+)*)-(?P<family>flash-lite|flash|pro)(?P<suffix>-.*)?$")
_PLAIN_SUFFIX = re.compile(r"^(-\d{3}|-latest|-preview(-[\d-]+)?)?$")  # not -image, -tts, -live, -exp ...
_LATEST_ALIAS = {"flash": "gemini-flash-latest", "flash-lite": "gemini-flash-lite-latest"}


def family_of(model: str) -> str:
    if model.startswith("auto:"):
        return model.split(":", 1)[1]
    return "flash-lite" if "flash-lite" in model else "flash"


def major_version(model: str) -> int | None:
    m = _NAME_RE.match(model)
    return int(m["ver"].split(".")[0]) if m else None


def pick_models(listing: list[dict[str, Any]], family: str, limit: int = MAX_AUTO_MODELS) -> list[str]:
    """Stable models of a family, newest first, then previews, from a models.list response."""
    ranked: list[tuple[bool, tuple[int, ...], int, str]] = []
    for m in listing:
        name = str(m.get("name") or "").removeprefix("models/")
        if "generateContent" not in (m.get("supportedGenerationMethods") or []):
            continue
        match = _NAME_RE.match(name)
        if not match or match["family"] != family or not _PLAIN_SUFFIX.match(match["suffix"] or ""):
            continue
        ver = tuple(int(x) for x in match["ver"].split("."))
        ver = (ver + (0, 0, 0))[:3]
        suffix = match["suffix"] or ""
        ranked.append(("preview" in suffix, tuple(-v for v in ver), len(suffix), name))
    ranked.sort()
    out: list[str] = []
    seen: set[tuple[bool, tuple[int, ...]]] = set()
    for preview, ver, _, name in ranked:
        if (preview, ver) in seen:  # gemini-x-flash and gemini-x-flash-001 are the same model
            continue
        seen.add((preview, ver))
        out.append(name)
    return out[:limit]


class GeminiProvider:
    def __init__(self, name: str, spec: ProviderSpec, client: httpx.Client | None = None):
        self.name = name
        self.spec = spec
        self._client = client
        self._models: list[str] | None = None
        self._idx = 0
        self._discovered: set[str] = set()
        self._no_thinking_config = False

    # -- plumbing ---------------------------------------------------------------------------------
    def _key(self) -> str:
        return os.environ.get(self.spec.api_key_env or "GEMINI_API_KEY", "").strip()

    def available(self) -> bool:
        return bool(self._key())

    @property
    def _base(self) -> str:
        return (self.spec.base_url or API_BASE).rstrip("/")

    def _send(self, method: str, url: str, **kw: Any) -> httpx.Response:
        client = self._client or httpx.Client(timeout=120)
        try:
            return client.request(method, url, headers={"x-goog-api-key": self._key()}, **kw)
        except httpx.HTTPError as exc:
            raise LLMError(f"network error: {type(exc).__name__}", code="network", retryable=True) from exc
        finally:
            if self._client is None:
                client.close()

    # -- model resolution -------------------------------------------------------------------------
    @property
    def current_model(self) -> str | None:
        models = self._models or []
        return models[self._idx] if self._idx < len(models) else None

    def resolve(self) -> list[str]:
        """The models this run will try, in order (discovers `auto:` entries on first use)."""
        if self._models is None:
            models: list[str] = []
            for entry in [self.spec.model, *self.spec.fallback_models]:
                for m in (self._discover(family_of(entry)) if entry.startswith("auto:") else [entry]):
                    if m not in models:
                        models.append(m)
            self._models = models
        return self._models

    def _discover(self, family: str) -> list[str]:
        if family in self._discovered:
            return []
        listing: list[dict[str, Any]] = []
        params: dict[str, Any] = {"pageSize": 1000}
        for _ in range(5):
            resp = self._send("GET", f"{self._base}/models", params=params)
            if resp.status_code != 200:
                raise _classify(resp)
            data = read_json(resp)
            listing.extend(m for m in data.get("models") or [] if isinstance(m, dict))
            if not data.get("nextPageToken"):
                break
            params["pageToken"] = data["nextPageToken"]
        self._discovered.add(family)  # only after a listing worked: a network blip is retried, not remembered
        found = pick_models(listing, family)
        log.info(f"llm: {self.name} found {len(found)} {family} model(s): {', '.join(found) or 'none'}")
        return found or [_LATEST_ALIAS.get(family, "gemini-flash-latest")]

    def _advance(self, model: str, exc: LLMError) -> bool:
        """Move to the next model after `exc`; False when there is none."""
        models = self.resolve()
        if self._idx + 1 >= len(models) and exc.model_gone:
            # A pinned model was retired: look for current models of the same family, once per run.
            for m in self._discover(family_of(models[self._idx] if models else self.spec.model)):
                if m not in models:
                    models.append(m)
        if self._idx + 1 >= len(models):
            return False
        self._idx += 1
        log.info(f"llm: {self.name} {model}: {exc.public()}; switching to {models[self._idx]}")
        return True

    # -- generation -------------------------------------------------------------------------------
    def generate(self, req: LLMRequest) -> LLMResponse:
        self.resolve()
        while True:
            model = self.current_model
            if model is None:
                raise LLMError("no Gemini model left to try", code="no_model", fatal_for_provider=True,
                               model_gone=True)
            try:
                return self._generate(model, req)
            except LLMError as exc:
                if not (rotates(exc, self.spec.quota_per_model) and self._advance(model, exc)):
                    raise

    def _body(self, model: str, req: LLMRequest) -> dict[str, Any]:
        parts: list[dict] = [{"text": req.prompt}]
        for data, mime in req.images:
            parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode("ascii")}})
        gen: dict[str, Any] = {"maxOutputTokens": req.max_output_tokens + self.spec.output_headroom}
        major = major_version(model)
        if major is not None and major >= 3:
            # Gemini 3 is tuned for its default temperature (lower values can loop), and "low" thinking
            # keeps drafts fast; older models take the task's temperature.
            if not self._no_thinking_config:
                gen["thinkingConfig"] = {"thinkingLevel": "LOW"}
        elif req.temperature is not None:
            gen["temperature"] = req.temperature
        body: dict[str, Any] = {"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}
        if req.system:
            body["systemInstruction"] = {"parts": [{"text": req.system}]}
        if req.grounding:
            body["tools"] = [{"googleSearch": {}}]
        elif req.json_mode:
            gen["responseMimeType"] = "application/json"
        return body

    def _generate(self, model: str, req: LLMRequest) -> LLMResponse:
        url = f"{self._base}/models/{model}:generateContent"
        started = time.monotonic()
        resp = self._send("POST", url, json=self._body(model, req))
        if (resp.status_code == 400 and not self._no_thinking_config and "thinking" in resp.text.lower()
                and (major_version(model) or 0) >= 3):
            self._no_thinking_config = True  # this model doesn't take thinkingLevel; ask once more without it
            resp = self._send("POST", url, json=self._body(model, req))
        latency = int((time.monotonic() - started) * 1000)
        if resp.status_code != 200:
            raise _classify(resp)
        data = read_json(resp)
        cands = data.get("candidates") or []
        if not cands:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            raise LLMError(f"no candidates (blocked: {block})", status=200, code=str(block or "no_candidates"))
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
            raise LLMError(f"empty output (finish={finish})", status=200, code=str(finish or "empty"),
                           retryable=finish not in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"))
        return LLMResponse(
            text=text,
            provider=self.name,
            model=str(data.get("modelVersion") or model),
            tokens_in=int(usage.get("promptTokenCount") or 0),
            tokens_out=int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0),
            grounding=grounding,
            finish_reason=finish,
            latency_ms=latency,
        )


def _classify(resp: httpx.Response) -> LLMError:
    status = resp.status_code
    try:
        payload = resp.json()
        err = payload.get("error", {}) if isinstance(payload, dict) else {}
    except ValueError:
        err = {}
    if not isinstance(err, dict):
        err = {}
    message = str(err.get("message") or resp.text[:300])
    low = message.lower()
    details = err.get("details") or []
    code = str(err.get("status") or "") or None
    retry_after = None
    daily = False
    for d in details if isinstance(details, list) else []:
        if not isinstance(d, dict):
            continue
        typ = str(d.get("@type", ""))
        if typ.endswith("ErrorInfo") and d.get("reason"):
            code = str(d["reason"])
        if typ.endswith("RetryInfo"):
            m = re.match(r"([\d.]+)s", str(d.get("retryDelay", "")))
            if m:
                retry_after = float(m.group(1))
        if typ.endswith("QuotaFailure"):
            for v in d.get("violations", []) or []:
                qid = str(v.get("quotaId", "")) + str(v.get("quotaMetric", ""))
                if "PerDay" in qid or "per_day" in qid.lower():
                    daily = True
    if status == 429:
        # "limit: 0" means this model has no free quota at all: as good as a daily limit.
        if daily or "per day" in low or "limit: 0" in low:
            return LLMError(f"daily quota reached: {message[:200]}", status=status, code=code, quota=True)
        return LLMError(f"rate limited: {message[:200]}", status=status, code=code, rate_limited=True,
                        retryable=True, retry_after=retry_after or 20.0)
    if status in (500, 502, 503, 504):
        return LLMError(f"server error {status}", status=status, code=code, retryable=True, retry_after=retry_after)
    if status == 404 or (status == 400 and ("is not found" in low or "not supported for generatecontent" in low)):
        return LLMError(f"model not available: {message[:200]}", status=status, code=code, model_gone=True)
    if status in (401, 403) or code in ("API_KEY_INVALID", "API_KEY_SERVICE_BLOCKED"):
        return LLMError(f"key rejected {status}: {message[:200]}", status=status, code=code, fatal_for_provider=True)
    if 300 <= status < 400 or status == 410:
        return LLMError(f"endpoint moved or gone ({status})", status=status, code=code, fatal_for_provider=True)
    return LLMError(f"error {status}: {message[:300]}", status=status, code=code)
