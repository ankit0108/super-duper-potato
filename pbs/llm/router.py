"""Routes each LLM task through a chain of free providers with quota tracking and fallback.

Order of defences when free tiers run out: the provider's next model (Gemini's free quotas are per model),
the next provider in the route, then the caller degrades (fewer cards, then brief cards with a 'Draft this'
button). A provider that fails in a way retrying can't fix (bad key, retired endpoint, unreadable replies) is
switched off for the rest of the run. Every call is redacted with the blocklist first.
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
from .base import (
    AllProvidersFailed,
    BudgetExhausted,
    LLMError,
    LLMRequest,
    LLMResponse,
    Provider,
    extract_json,
)
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatProvider

T = TypeVar("T")
GROUNDING_OFF = "grounding_off"  # settings key: the day search grounding said no (its quota is separate)


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
    provider_errors: dict[str, str] = field(default_factory=dict)  # public-safe, latest per provider
    models: dict[str, str] = field(default_factory=dict)  # the model that answered, per provider

    @property
    def all_failed(self) -> bool:
        """Model calls were attempted and none succeeded."""
        return self.calls == 0 and self.failures > 0

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
            "provider_errors": dict(self.provider_errors),
            "models": dict(self.models),
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
        self._disabled: dict[str, str] = {}
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
            if req.grounding and (not spec.grounding or self.grounding_off_today()):
                return False
            if spec.max_input_tokens and req.estimated_input_tokens() > spec.max_input_tokens:
                return False
        return True

    def chain(self, task: str, personal: bool = False) -> list[str]:
        specs = self.settings.llm.providers
        chain = [p for p in self.settings.llm.routes.get(task) or self.settings.llm.routes.get("draft") or []
                 if p in specs]
        if personal:
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

    def chain_broken(self, task: str, personal: bool = False) -> bool:
        """Every configured provider for the task failed with an error this run (not just out of quota)."""
        configured = [n for n in self.chain(task, personal) if n in self._providers and self._providers[n].available()]
        return bool(configured) and all(n in self._disabled for n in configured)

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
                except Exception as raw:  # noqa: BLE001 - one broken provider must not stop the chain
                    exc = raw if isinstance(raw, LLMError) else LLMError(
                        f"unexpected {type(raw).__name__}: {str(raw)[:200]}", code=type(raw).__name__,
                        fatal_for_provider=True)
                    if not isinstance(raw, LLMError):
                        log.error(f"llm:{name}", raw)
                    last_error = exc
                    self.usage.failures += 1
                    self.usage.errors.append(f"{req.task}/{name}: {exc}"[:300])
                    self.usage.provider_errors[name] = exc.public()
                    self._record(name, error=str(exc)[:300], count=False)
                    if exc.quota or (req.grounding and exc.rate_limited):
                        if req.grounding:
                            # Search grounding has its own small free quota, separate from the provider's other
                            # calls: once it says no, skip it for the rest of the day instead of retrying.
                            self._grounding_off(name, exc)
                        else:
                            self._mark_exhausted(name, str(exc))
                        break
                    if exc.fatal_for_provider or exc.model_gone:
                        self._disable(name, exc)
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
                    self.usage.models[name] = resp.model
                    self._record(name, tokens_in=resp.tokens_in, tokens_out=resp.tokens_out, model=resp.model)
                    return resp
        if tried == 0:
            if self.chain_broken(req.task, req.personal):
                raise AllProvidersFailed(f"every provider for '{req.task}' was switched off after errors")
            raise BudgetExhausted(f"no usable provider for task '{req.task}'")
        if last_error is not None and last_error.quota:
            raise BudgetExhausted(f"free quotas used up for '{req.task}'")
        raise AllProvidersFailed(f"all providers failed for '{req.task}': {last_error}")

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
                count: bool = True, model: str | None = None) -> None:
        row = self._quota_row(name)
        now = timeutil.now_iso()
        if count:
            row["requests"] = int(row.get("requests") or 0) + 1
            row["last_ok_at"] = now
        row["tokens_in"] = int(row.get("tokens_in") or 0) + tokens_in
        row["tokens_out"] = int(row.get("tokens_out") or 0) + tokens_out
        if model:
            row["model"] = model
        if error:
            row["last_error"] = error
            row["last_error_at"] = now
        row["updated_at"] = now
        self.store.upsert("quota", row)

    def _disable(self, name: str, exc: LLMError) -> None:
        """Switch a provider off for the rest of this run, saying why in the (public) log once."""
        if name not in self._disabled:
            self._disabled[name] = exc.public()
            log.warn(f"llm: {name} switched off for this run: {exc.public()}")

    def grounding_off_today(self) -> bool:
        return (self.store.get_setting(GROUNDING_OFF) or {}).get("day") == self._day()

    def _grounding_off(self, name: str, exc: LLMError) -> None:
        if not self.grounding_off_today():
            self.store.set_setting(GROUNDING_OFF, {"day": self._day(), "provider": name, "reason": exc.public()})
            log.info(f"llm: {name} search grounding unavailable today ({exc.public()}); searches use the free feeds")

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
