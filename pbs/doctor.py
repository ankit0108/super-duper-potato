"""`pbs doctor`: the Phase 0 checks, automated (FR-30). Results appear on the desk's System page."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from . import ids, log, notify, timeutil
from .context import Ctx
from .llm.base import LLMError, LLMRequest
from .scout.fetch import FetchJob, fetch_all, no_sleep
from .scout.sources import fetch_url, sync_seeds


def _check(name: str, status: str, detail: str | None = None, private: str | None = None) -> dict[str, Any]:
    """`detail` must be safe for public logs (counts, IDs, error codes); `private` goes only to the desk."""
    out: dict[str, Any] = {"name": name, "status": status, "detail": detail}
    if private and private != detail:
        out["detail"] = f"{detail} · {private}" if detail else private
        out["_public"] = detail
    return out


def _model_label(provider: Any, spec: Any) -> str:
    current = getattr(provider, "current_model", None)
    return current or spec.model


def run_doctor(ctx: Ctx, probe_llm: bool = True, probe_sources: bool = True) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    env = os.environ
    checks.append(_check("Secret: GEMINI_API_KEY",
                         "ok" if env.get("GEMINI_API_KEY") else ("warn" if env.get("GROQ_API_KEY") else "fail"),
                         None if env.get("GEMINI_API_KEY") else "Not set. Get a free key at aistudio.google.com: "
                         "Gemini is the main drafting model."))
    checks.append(_check("Secret: GROQ_API_KEY", "ok" if env.get("GROQ_API_KEY") else "warn",
                         None if env.get("GROQ_API_KEY") else "Not set. Recommended: a free key from console.groq.com "
                         "is the fallback when Gemini's free quota runs out, and it doesn't train on your inputs."))
    checks.append(_check("Secret: PBS_BLOCKLIST", "ok" if ctx.blocklist else "warn",
                         f"{len(ctx.blocklist)} terms" if ctx.blocklist else "Empty: the employer/client check can't run."))
    chans = notify.configured()
    checks.append(_check("Notifications", "ok" if chans else "skip",
                         ", ".join(chans) if chans else "Optional: set PBS_NTFY_TOPIC or Telegram secrets."))
    for w in ctx.settings_warnings:
        checks.append(_check("Settings", "warn", w))

    if probe_llm:
        router = ctx.llm
        for name, spec in ctx.settings.llm.providers.items():
            provider = router._providers.get(name)
            if provider is None or not provider.available():
                checks.append(_check(f"Model: {name} ({spec.model})", "skip", f"No {spec.api_key_env or 'key'} set"))
                continue
            started = time.monotonic()
            try:
                resp = provider.generate(LLMRequest(task="doctor", system="Reply with JSON only.",
                                                    prompt='Reply with {"ok": true}', max_output_tokens=50,
                                                    temperature=0))
                router._record(name, tokens_in=resp.tokens_in, tokens_out=resp.tokens_out, model=resp.model)
                ms = int((time.monotonic() - started) * 1000)
                checks.append(_check(f"Model: {name} ({_model_label(provider, spec)})", "ok", f"answered in {ms} ms"))
            except Exception as raw:  # noqa: BLE001 - report every provider, whatever breaks
                exc = raw if isinstance(raw, LLMError) else LLMError(f"unexpected {type(raw).__name__}",
                                                                       code=type(raw).__name__)
                router._record(name, error=str(exc)[:300], count=False)
                status = "warn" if exc.quota or exc.rate_limited else "fail"
                checks.append(_check(f"Model: {name} ({_model_label(provider, spec)})", status, exc.public(),
                                     private=str(exc)[:200]))
        grounding = next((n for n, s in ctx.settings.llm.providers.items() if s.grounding
                          and router._providers.get(n) and router._providers[n].available()), None)
        if grounding:
            try:
                resp = router._providers[grounding].generate(LLMRequest(
                    task="doctor", system="", prompt="What is the latest stable Python release? One line.",
                    json_mode=False, grounding=True, max_output_tokens=100))
                router._record(grounding, model=resp.model)
                checks.append(_check("Google Search grounding", "ok" if resp.grounding else "warn",
                                     f"{len(resp.grounding)} sources returned" if resp.grounding
                                     else "Answered without search sources; requests use the free search feeds."))
            except Exception as raw:  # noqa: BLE001
                public = raw.public() if isinstance(raw, LLMError) else type(raw).__name__
                checks.append(_check("Google Search grounding", "warn",
                                     f"Not available ({public}). Requests use the free search feeds."))

    if probe_sources:
        sync_seeds(ctx.store)
        sources = ctx.store.select("sources", "active = 1")
        jobs = [FetchJob(key=s["id"], url=fetch_url(s, ctx.local_date_str())) for s in sources]
        sc = ctx.settings.scouting
        results = asyncio.run(fetch_all(jobs, user_agent=sc.user_agent, timeout=sc.timeout_seconds,
                                        concurrency=sc.concurrency, transport=ctx.transport,
                                        **({"sleep": no_sleep} if ctx.transport is not None else {})))
        failed = [r.key for r in results if not r.ok]
        checks.append(_check("Sources reachable", "ok" if not failed else ("warn" if len(failed) < len(results) / 3
                                                                           else "fail"),
                             f"{len(results) - len(failed)}/{len(results)} ok" +
                             (f"; failing: {', '.join(failed[:12])}" if failed else "")))

    for c in checks:
        public = c.pop("_public", c["detail"])
        log.info(f"doctor: {c['status']:<4} {c['name']}" + (f": {public}" if public else ""))
    summary = {s: sum(1 for c in checks if c["status"] == s) for s in ("ok", "warn", "fail", "skip")}
    row = {"id": ids.new_id("doc"), "created_at": timeutil.now_iso(), "checks": checks, "summary": summary}
    ctx.store.upsert("doctor_reports", row)
    log.info(f"doctor: {summary}")
    return row
