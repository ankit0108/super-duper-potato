"""LLM interface shared by all providers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol


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


class LLMError(Exception):
    """Provider failure. `quota` = daily limit reached; `rate_limited` = retry after a pause."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False,
                 quota: bool = False, rate_limited: bool = False, retry_after: float | None = None,
                 fatal_for_provider: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.quota = quota
        self.rate_limited = rate_limited
        self.retry_after = retry_after
        self.fatal_for_provider = fatal_for_provider


class BudgetExhausted(Exception):
    """No provider can take another call right now (daily cap, run cap, or all quotas used)."""


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
