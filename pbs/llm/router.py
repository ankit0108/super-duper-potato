"""Routes each LLM task through a chain of free providers with quota tracking and fallback.

Order of defences when free tiers run out: next provider in the route, then the caller degrades
(fewer cards, then brief cards with a 'Draft this' button). Every call is redacted with the blocklist first.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .. import log, timeutil
from ..guardrails import redact
from ..settings import ProviderSpec, Settings
from ..store import Store
from .base import BudgetExhausted, LLMError, LLMRequest, LLMResponse, Provider, extract_json
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatProvider

T = TypeVar("T")


def build_provider(name: str, spec: ProviderSpec) -> Provider:
    if spec.kind == "gemini":
        return GeminiProvider(name, spec)
    if spec.kind == "openai":
        return OpenAICompatProvider(name, spec)
    if spec.kind == "fake":
        from .fake import FakeProvider

        return FakeProvider(name)
    raise ValueError(f"unknown provider kind {spec.kind}")


@dataclass
class RunUsage:
    calls: int = 0
    failures: int = 0
    fallbacks: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    by_provider: dict[str, int] = field(default_factory=dict)
    by_task: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "failures": self.failures,
            "fallbacks": self.fallbacks,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "by_provider": dict(self.by_provider),
            "by_task": dict(self.by_task),
            "errors": self.errors[-20:],
        }


class Router:
    def __init__(self, settings: Settings, store: Store, blocklist: list[str] | None = None,
                 providers: dict[str, Provider] | None = None, sleep: Callable[[float], None] = time.sleep):
        self.settings = settings
        self.store = store
        self.blocklist = blocklist or []
        self.sleep = sleep
        self.usage = RunUsage()
        self._providers: dict[str, Provider] = providers or {}
        self._disabled: set[str] = set()
        self._last_call: dict[str, float] = {}
        for name, spec in settings.llm.providers.items():
            if name not in self._providers:
                try:
                    self._providers[name] = build_provider(name, spec)
                except ValueError:
                    continue

    # -- budget -----------------------------------------------------------------------------------
    @staticmethod
    def _day() -> str:
        return timeutil.now().strftime("%Y-%m-%d")

    def _quota_row(self, provider: str) -> dict[str, Any]:
        qid = f"{provider}:{self._day()}"
        row = self.store.get("quota", qid)
        if row is None:
            row = {"id": qid, "provider": provider, "day": self._day(), "requests": 0, "tokens_in": 0,
                   "tokens_out": 0}
        return row

    def used_today(self) -> int:
        return int(self.store.scalar("SELECT COALESCE(SUM(requests), 0) FROM quota WHERE day = ?", (self._day(),)))

    def provider_usable(self, name: str, req: LLMRequest | None = None) -> bool:
        provider = self._providers.get(name)
        spec = self.settings.llm.providers.get(name)
        if provider is None or spec is None or name in self._disabled or not provider.available():
            return False
        row = self._quota_row(name)
        if row.get("exhausted_at") or int(row.get("requests") or 0) >= spec.daily_limit:
            return False
        if req is not None:
            if req.images and not spec.vision:
                return False
            if req.grounding and not spec.grounding:
                return False
            if spec.max_input_tokens and req.estimated_input_tokens() > spec.max_input_tokens:
                return False
        return True

    def chain(self, task: str, personal: bool = False) -> list[str]:
        chain = list(self.settings.llm.routes.get(task) or self.settings.llm.routes.get("draft") or [])
        if personal:
            specs = self.settings.llm.providers
            private = [p for p in chain if not specs[p].trains_on_inputs]
            others = [p for p in chain if specs[p].trains_on_inputs]
            chain = private + (others if self.settings.llm.personal_allow_training_fallback else [])
        return chain

    def remaining(self, task: str, personal: bool = False) -> int:
        """Rough number of calls still available for a task today (for degradation planning)."""
        caps = [
            self.settings.llm.daily_cap - self.used_today(),
            self.settings.llm.max_calls_per_run - self.usage.calls,
        ]
        per_provider = 0
        for name in self.chain(task, personal):
            if self.provider_usable(name):
                spec = self.settings.llm.providers[name]
                per_provider += max(0, spec.daily_limit - int(self._quota_row(name).get("requests") or 0))
        return max(0, min([*caps, per_provider]))

    def any_available(self, task: str = "draft") -> bool:
        return self.remaining(task) > 0

    # -- calls ------------------------------------------------------------------------------------
    def call(self, req: LLMRequest) -> LLMResponse:
        if self.usage.calls >= self.settings.llm.max_calls_per_run:
            raise BudgetExhausted("per-run LLM call cap reached")
        if self.used_today() >= self.settings.llm.daily_cap:
            raise BudgetExhausted("daily LLM call cap reached")
        if req.temperature is None:
            req.temperature = self.settings.llm.temperature.get(req.task)
        req.system = redact(req.system, self.blocklist)
        req.prompt = redact(req.prompt, self.blocklist)

        tried = 0
        last_error: Exception | None = None
        for name in self.chain(req.task, req.personal):
            if not self.provider_usable(name, req):
                continue
            if tried:
                self.usage.fallbacks += 1
            tried += 1
            provider = self._providers[name]
            for attempt in range(3):
                self._pace(name)
                try:
                    resp = provider.generate(req)
                except LLMError as exc:
                    last_error = exc
                    self.usage.failures += 1
                    self.usage.errors.append(f"{req.task}/{name}: {exc}"[:300])
                    self._record(name, error=str(exc)[:300], count=False)
                    if exc.quota:
                        self._mark_exhausted(name, str(exc))
                        break
                    if exc.fatal_for_provider:
                        self._disabled.add(name)
                        break
                    if exc.retryable and attempt < 2:
                        wait = min(exc.retry_after or (2.0 * (3**attempt)), 45.0)
                        self.sleep(wait)
                        continue
                    break
                else:
                    self.usage.calls += 1
                    self.usage.tokens_in += resp.tokens_in
                    self.usage.tokens_out += resp.tokens_out
                    self.usage.by_provider[name] = self.usage.by_provider.get(name, 0) + 1
                    self.usage.by_task[req.task] = self.usage.by_task.get(req.task, 0) + 1
                    self._record(name, tokens_in=resp.tokens_in, tokens_out=resp.tokens_out)
                    return resp
        if tried == 0:
            raise BudgetExhausted(f"no usable provider for task '{req.task}'")
        raise BudgetExhausted(f"all providers failed for '{req.task}': {last_error}")

    def call_json(self, req: LLMRequest, schema: type[BaseModel] | Callable[[Any], T] | None = None,
                  repair: bool = True) -> tuple[Any, LLMResponse]:
        """Call and parse JSON, validating with a pydantic model or callable. One repair attempt."""
        resp = self.call(req)
        try:
            return _validate(extract_json(resp.text), schema), resp
        except (ValueError, ValidationError) as exc:
            if not repair:
                raise
            log.info(f"llm: repairing invalid JSON for task={req.task}")
            fix = LLMRequest(
                task=req.task,
                system=req.system,
                prompt=(req.prompt + "\n\nYour previous reply could not be used because: "
                        + _short_error(exc) + "\nPrevious reply (truncated):\n" + resp.text[:3000]
                        + "\n\nReply again with valid JSON only, following the required format exactly."),
                images=req.images,
                json_mode=True,
                max_output_tokens=req.max_output_tokens,
                temperature=0.2,
                personal=req.personal,
                prompt_version=req.prompt_version,
            )
            resp2 = self.call(fix)
            return _validate(extract_json(resp2.text), schema), resp2

    # -- bookkeeping ------------------------------------------------------------------------------
    def _pace(self, name: str) -> None:
        spec = self.settings.llm.providers[name]
        min_interval = 60.0 / max(1, spec.rpm)
        last = self._last_call.get(name)
        now = time.monotonic()
        if last is not None and now - last < min_interval:
            self.sleep(min_interval - (now - last))
        self._last_call[name] = time.monotonic()

    def _record(self, name: str, tokens_in: int = 0, tokens_out: int = 0, error: str | None = None,
                count: bool = True) -> None:
        row = self._quota_row(name)
        if count:
            row["requests"] = int(row.get("requests") or 0) + 1
        row["tokens_in"] = int(row.get("tokens_in") or 0) + tokens_in
        row["tokens_out"] = int(row.get("tokens_out") or 0) + tokens_out
        if error:
            row["last_error"] = error
        row["updated_at"] = timeutil.now_iso()
        self.store.upsert("quota", row)

    def _mark_exhausted(self, name: str, error: str) -> None:
        row = self._quota_row(name)
        row["exhausted_at"] = timeutil.now_iso()
        row["last_error"] = error[:300]
        self.store.upsert("quota", row)
        log.warn(f"llm: provider {name} reached its daily quota")


def _validate(data: Any, schema: type[BaseModel] | Callable[[Any], Any] | None) -> Any:
    if schema is None:
        return data
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema.model_validate(data)
    return schema(data)


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        errs = exc.errors()[:3]
        return "; ".join(f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg')}" for e in errs)
    return str(exc)[:300]
