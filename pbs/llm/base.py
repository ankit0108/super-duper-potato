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


def rotates(exc: LLMError, quota_per_model: bool) -> bool:
    """Whether a provider's next model should answer instead: the model is gone, or (when quotas and capacity
    are per model) it is out of quota, rate limited or overloaded, which says nothing about the next one."""
    if exc.model_gone:
        return True
    return quota_per_model and (exc.quota or exc.rate_limited or (exc.status or 0) >= 500)


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
