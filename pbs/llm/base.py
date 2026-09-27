"""LLM interface shared by all providers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


@dataclass
class LLMRequest:
    task: str
    system: str
    prompt: str
    images: list[tuple[bytes, str]] = field(default_factory=list)
    json_mode: bool = True
    max_output_tokens: int = 4096
    temperature: float | None = None
    grounding: bool = False
    personal: bool = False
    prompt_version: str | None = None

    def estimated_input_tokens(self) -> int:
        chars = len(self.system) + len(self.prompt)
        return int(chars / 3) + 300 * len(self.images)


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    grounding: list[dict[str, str]] = field(default_factory=list)
    finish_reason: str | None = None
    latency_ms: int = 0


_CODE_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,48}$")


class LLMError(Exception):
    """Provider failure.

    `quota`: daily limit reached. `rate_limited`: retry after a pause. `model_gone`: the model was retired or
    renamed, so the provider's next model should be tried. `code` is the provider's own error code
    (NOT_FOUND, invalid_api_key, ...): an identifier, never request content, so it is safe for public logs.
    """

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None,
                 retryable: bool = False, quota: bool = False, rate_limited: bool = False,
                 retry_after: float | None = None, fatal_for_provider: bool = False, model_gone: bool = False):
        super().__init__(message)
        self.status = status
        self.code = code if code and _CODE_RE.match(code) else None
        self.retryable = retryable
        self.quota = quota
        self.rate_limited = rate_limited
        self.retry_after = retry_after
        self.fatal_for_provider = fatal_for_provider
        self.model_gone = model_gone

    @property
    def kind(self) -> str:
        if self.quota:
            return "daily quota reached"
        if self.rate_limited:
            return "rate limited"
        if self.model_gone:
            return "model not available"
        if self.code == "bad_body":
            return "unreadable response"
        if self.code == "network":
            return "network error"
        if self.status in (401, 403) or "key" in (self.code or "").lower():
            return "key rejected"
        if self.status is not None and self.status >= 500:
            return "server error"
        return "request failed"

    def public(self) -> str:
        """Content-free summary for public logs: kind, HTTP status and the provider's error code."""
        detail = " ".join(p for p in (f"HTTP {self.status}" if self.status is not None else "",
                                      self.code if self.code not in (None, "bad_body", "network") else "") if p)
        return f"{self.kind} ({detail})" if detail else self.kind


class ModelCycle:
    """The models one provider can answer with, in order of preference, and what this run learned about them.

    A call tries each usable model at most once, starting from the one that last answered and wrapping around.
    A retired model is dropped; with per-model quotas (Gemini, Groq), a model out of its daily quota is skipped
    for the rest of the run and an overloaded or rate-limited one hands the call to the next. Grounded (search)
    calls hand over the same way but change nothing for later calls: a search quota says nothing about drafting.
    """

    def __init__(self, provider: str, models: list[str], quota_per_model: bool):
        self.provider = provider
        self.models = list(models)
        self.quota_per_model = quota_per_model
        self.idx = 0
        self.dead: set[str] = set()
        self.spent: set[str] = set()

    @property
    def current(self) -> str | None:
        return self.models[self.idx] if self.idx < len(self.models) else None

    def usable(self) -> list[str]:
        n = len(self.models)
        order = [self.models[(self.idx + k) % n] for k in range(n)]
        return [m for m in order if m not in self.dead and m not in self.spent]

    def run(self, req: LLMRequest, attempt: Any, rediscover: Any = None) -> LLMResponse:
        from .. import log

        tried: set[str] = set()
        transient: LLMError | None = None
        last: LLMError | None = None
        while True:
            pending = [m for m in self.usable() if m not in tried]
            if not pending and self.dead and rediscover is not None:
                self.models.extend(m for m in rediscover() if m not in self.models)
                pending = [m for m in self.usable() if m not in tried]
            if not pending:
                break
            model = pending[0]
            tried.add(model)
            try:
                resp = attempt(model)
            except LLMError as exc:
                last = exc
                if exc.model_gone:
                    self.dead.add(model)
                elif not self.quota_per_model:
                    raise
                elif exc.quota and not req.grounding:
                    self.spent.add(model)
                elif exc.quota or exc.rate_limited or (exc.status or 0) >= 500:
                    transient = exc
                else:
                    raise
                log.info(f"llm: {self.provider} {model}: {exc.public()}; trying the next model")
                continue
            if not req.grounding:
                self.idx = self.models.index(model)
            return resp
        if transient is not None:
            raise transient
        if last is not None:
            raise last
        raise LLMError("no model left to try", code="no_model", fatal_for_provider=True, model_gone=True)


class BudgetExhausted(Exception):
    """No provider can take another call right now (daily cap, run cap, or all quotas used)."""


class AllProvidersFailed(BudgetExhausted):
    """Every provider in the route was tried and failed with an error (not just out of quota)."""


def why_unavailable(exc: BudgetExhausted) -> str:
    """For notes Ankit reads: quota versus broken providers need different reactions."""
    if isinstance(exc, AllProvidersFailed):
        return "the model providers returned errors (System shows which)"
    return "the free model quota ran out"


def read_json(resp: httpx.Response) -> dict[str, Any]:
    """The JSON object in a provider's reply, or an LLMError that says what came back instead."""
    try:
        data = resp.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        ctype = (resp.headers.get("content-type") or "no content type").split(";")[0].strip()[:40]
        raise LLMError(f"unreadable response body (HTTP {resp.status_code}, {ctype}, {len(resp.content)} bytes)",
                       status=resp.status_code, code="bad_body", fatal_for_provider=True)
    return data


class Provider(Protocol):
    name: str

    def available(self) -> bool: ...

    def generate(self, req: LLMRequest) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# Tolerant JSON extraction
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def json_rows(data: Any, key: str) -> list[dict[str, Any]]:
    """The list of objects a reply carries under `key`. Models asked for {"items": [...]} sometimes answer with
    the bare list, so both shapes are accepted; anything that isn't an object is dropped."""
    rows = data.get(key) if isinstance(data, dict) else data
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply that may include fences, prose or trailing commas."""
    if not text or not text.strip():
        raise ValueError("empty model output")
    candidates: list[str] = []
    fenced = _FENCE_RE.findall(text)
    candidates.extend(fenced)
    candidates.append(text)
    for cand in candidates:
        cand = cand.strip()
        for attempt in (cand, _TRAILING_COMMA_RE.sub(r"\1", cand)):
            try:
                return json.loads(attempt)
            except json.JSONDecodeError:
                pass
        # Find the outermost object or array.
        for opener, closer in (("{", "}"), ("[", "]")):
            start = cand.find(opener)
            end = cand.rfind(closer)
            if start != -1 and end > start:
                chunk = cand[start : end + 1]
                for attempt in (chunk, _TRAILING_COMMA_RE.sub(r"\1", chunk)):
                    try:
                        return json.loads(attempt)
                    except json.JSONDecodeError:
                        continue
    raise ValueError("could not parse JSON from model output")
