"""The tick: every run does whatever is due, so no work depends on one particular run firing (FR-28).

Order: ingest desk events → doctor if asked → expire → work Ankit is waiting on (answers, rewrites,
'draft this') → requests → metrics → morning delivery if due → Saturday batch if due → reflection if due →
learning → prune → export.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import (
    bandit,
    deliver,
    doctor,
    draft,
    export,
    inbox,
    learn,
    log,
    metrics,
    notify,
    playbook,
    reflect,
    requests,
    stances,
    voice,
)
from .context import Ctx
from .scout.scouting import run_scouts
from .scout.sources import sync_seeds
from .topics import build_topics

TASKS = {"morning", "weekly_batch", "reflection", "doctor", "report", "scout", "work", "requests", "metrics",
         "stances", "rewards"}


def run(data_root: str | Path, *, trigger: str = "manual", hints: set[str] | None = None, force: bool = False,
        transport: Any = None, llm_providers: dict[str, Any] | None = None, sleep: Any = None,
        send_notifications: bool = True,
        morning: Callable[[Ctx], dict[str, Any] | None] | None = None) -> dict[str, Any]:
    """One run. `morning` replaces the morning delivery step (the demo builder uses it to replay past days)."""
    ctx = Ctx.create(data_root, task="tick", trigger=trigger, hints=hints, force=force, transport=transport,
                     llm_providers=llm_providers, sleep=sleep)
    summary: dict[str, Any] = {"run_id": ctx.run.id}
    log.info(f"tick: start trigger={trigger} hints={sorted(ctx.hints)}")

    with ctx.run.step("setup"):
        sync_seeds(ctx.store)
        stances.ensure_seeded(ctx)
        playbook.ensure_seed(ctx)
    with ctx.run.step("inbox") as s:
        s["stats"] = inbox.ingest(ctx)
    if "doctor" in ctx.hints:
        # Early (after the inbox, which can ask for it), so its checks are logged before the day's work.
        with ctx.run.step("doctor") as s:
            s["summary"] = doctor.run_doctor(ctx, probe_llm=transport is None or llm_providers is not None,
                                             probe_sources=True)["summary"]
    with ctx.run.step("expire") as s:
        s["expired"] = learn.expire_cards(ctx)
    with ctx.run.step("work") as s:
        s["stats"] = draft.process_work(ctx)
    with ctx.run.step("requests") as s:
        s["stats"] = requests.handle_requests(ctx)
        done = s["stats"]["done"]
        if done and send_notifications and ctx.settings.notify.on_request_done:
            notify.send(ctx, "Request drafted", f"{done} request(s) drafted and waiting on your desk.", tags="mag")
    if "metrics" in ctx.hints or ctx.store.count("metric_uploads", "status = 'pending'"):
        with ctx.run.step("metrics") as s:
            s["stats"] = metrics.process_uploads(ctx)
    if "stances" in ctx.hints:
        with ctx.run.step("stances") as s:
            s["added"] = stances.propose(ctx, int(ctx.store.get_setting("stance_proposals_wanted", 3) or 3))

    morning_wanted = "morning" in ctx.hints and ctx.force
    if deliver.delivery_due(ctx) or morning_wanted:
        with ctx.run.step("morning") as s:
            if morning_wanted and ctx.store.get("deliveries", deliver.delivery_id(ctx.local_date_str())):
                s["result"] = _extra_delivery(ctx)
            else:
                s["result"] = morning(ctx) if morning else deliver.morning_delivery(ctx)
            res = s["result"]
            if res and send_notifications and ctx.settings.notify.on_delivery:
                title, msg = notify.delivery_message(res["counts"], res["needs_input"], ctx.run.degraded)
                notify.send(ctx, title, msg)
            summary["delivery"] = res and {k: res[k] for k in ("id", "counts", "needs_input")}
    elif "scout" in ctx.hints:
        with ctx.run.step("scout"):
            run_scouts(ctx)
        with ctx.run.step("topics"):
            build_topics(ctx)
    batch_done = ctx.store.get("deliveries", deliver.weekly_batch_key(ctx)) is not None
    if deliver.weekly_batch_due(ctx) or ("weekly_batch" in ctx.hints and (ctx.force or not batch_done)):
        with ctx.run.step("weekly_batch") as s:
            s["result"] = deliver.weekly_batch(ctx)
    if reflect.reflection_due(ctx) or {"reflection", "report"} & ctx.hints:
        with ctx.run.step("reflection") as s:
            s["result"] = reflect.weekly_reflection(ctx)
    with ctx.run.step("learn"):
        learn.update_rewards(ctx)
        voice.update_voice(ctx, weekly=False)
        bandit.snapshot(ctx.store, bandit.compute_arms(ctx.store, ctx.settings))
    with ctx.run.step("prune") as s:
        s["pruned"] = learn.prune(ctx)

    record = ctx.run.finish(ctx.llm.usage.as_dict() if ctx._router else {})
    try:
        export.write(ctx)
    except Exception as exc:  # noqa: BLE001
        log.error("export", exc)
        record["status"] = "partial" if record["status"] == "ok" else record["status"]
        ctx.store.upsert("runs", record)
    changed = ctx.store.save()
    inbox.cleanup(ctx)
    llm = record.get("llm") or {}
    summary.update(status=record["status"], changed_files=len(changed), llm_calls=llm.get("calls", 0),
                   llm_failures=llm.get("failures", 0), degraded=ctx.run.degraded)
    if send_notifications and ctx.settings.notify.on_failure:
        if record["status"] == "failed":
            notify.send(ctx, "PBS run failed", "A run failed. Open System on the desk for details.", tags="warning")
        elif summary.get("delivery") and llm.get("failures") and not llm.get("calls"):
            notify.send(ctx, "PBS: drafts need attention", "No model answered, so today's cards are briefs. "
                        "Open System on the desk for details.", tags="warning")
    log.info(f"tick: done status={record['status']} llm_calls={summary['llm_calls']} "
             f"llm_failures={summary['llm_failures']} degraded={ctx.run.degraded} files={len(changed)}")
    return summary


def _extra_delivery(ctx: Ctx) -> dict[str, Any] | None:
    """'Get more cards': a second set for today under a suffixed delivery id."""
    base = deliver.delivery_id(ctx.local_date_str())
    n = 2
    while ctx.store.get("deliveries", f"{base}_{n}"):
        n += 1
    return deliver.morning_delivery(ctx, scout=True, dlv_id=f"{base}_{n}")
