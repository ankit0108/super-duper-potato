"""`pbs doctor`: the Phase 0 checks, automated (FR-30). Results appear on the desk's System page."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from . import ids, log, notify, timeutil
from .context import Ctx
from .llm.base import LLMError, LLMRequest
from .scout.fetch import FetchJob, fetch_all
from .scout.sources import fetch_url, sync_seeds


def _check(name: str, status: str, detail: str | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail}


def run_doctor(ctx: Ctx, probe_llm: bool = True, probe_sources: bool = True) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    env = os.environ
    checks.append(_check("Secret: GEMINI_API_KEY", "ok" if env.get("GEMINI_API_KEY") else "warn",
                         None if env.get("GEMINI_API_KEY") else "Not set. Get a free key at aistudio.google.com; "
                         "GitHub Models still works without it."))
    checks.append(_check("GitHub Models token", "ok" if env.get("GITHUB_TOKEN") else "warn",
                         None if env.get("GITHUB_TOKEN") else "GITHUB_TOKEN is missing (it is automatic in Actions "
                         "with 'models: read' permission)."))
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
                router._record(name, tokens_in=resp.tokens_in, tokens_out=resp.tokens_out)
                ms = int((time.monotonic() - started) * 1000)
                checks.append(_check(f"Model: {name} ({spec.model})", "ok", f"answered in {ms} ms"))
            except LLMError as exc:
                status = "warn" if exc.quota or exc.rate_limited else "fail"
                checks.append(_check(f"Model: {name} ({spec.model})", status, str(exc)[:200]))
        grounding = next((n for n, s in ctx.settings.llm.providers.items() if s.grounding
                          and router._providers.get(n) and router._providers[n].available()), None)
        if grounding:
            try:
                resp = router._providers[grounding].generate(LLMRequest(
                    task="doctor", system="", prompt="What is the latest stable Python release? One line.",
                    json_mode=False, grounding=True, max_output_tokens=100))
                router._record(grounding)
                checks.append(_check("Google Search grounding", "ok" if resp.grounding else "warn",
                                     f"{len(resp.grounding)} sources returned" if resp.grounding
                                     else "Answered without search sources; requests use the free search feeds."))
            except LLMError as exc:
                checks.append(_check("Google Search grounding", "warn",
                                     f"Not available on this tier ({str(exc)[:120]}). Requests use the free search feeds."))

    if probe_sources:
        sync_seeds(ctx.store)
        sources = ctx.store.select("sources", "active = 1")
        jobs = [FetchJob(key=s["id"], url=fetch_url(s, ctx.local_date_str())) for s in sources]
        sc = ctx.settings.scouting
        results = asyncio.run(fetch_all(jobs, user_agent=sc.user_agent, timeout=sc.timeout_seconds,
                                        concurrency=sc.concurrency, transport=ctx.transport))
        failed = [r.key for r in results if not r.ok]
        checks.append(_check("Sources reachable", "ok" if not failed else ("warn" if len(failed) < len(results) / 3
                                                                           else "fail"),
                             f"{len(results) - len(failed)}/{len(results)} ok" +
                             (f"; failing: {', '.join(failed[:12])}" if failed else "")))

    summary = {s: sum(1 for c in checks if c["status"] == s) for s in ("ok", "warn", "fail", "skip")}
    row = {"id": ids.new_id("doc"), "created_at": timeutil.now_iso(), "checks": checks, "summary": summary}
    ctx.store.upsert("doctor_reports", row)
    log.info(f"doctor: {summary}")
    return row
