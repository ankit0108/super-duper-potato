"""Export desk/desk.json: everything the desk renders, validated against the contract before writing."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from . import __version__, platform, stats, timeutil
from .context import Ctx
from .contracts import DESK_SCHEMA_VERSION, DeskState

ACTIVE = ("drafting", "suggested", "needs_input", "editing", "blocked", "failed")


def _latest_metrics(ctx: Ctx) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in ctx.store.select("metrics", "status = 'confirmed' AND post_id IS NOT NULL", order="captured_at"):
        out[m["post_id"]] = m
    return out


def warnings(ctx: Ctx) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    now = timeutil.now_iso()
    llm = ctx.llm
    if not any(llm.provider_usable(p, allow_overloaded=True) for p in ctx.settings.llm.providers):
        out.append({"level": "error", "code": "no_llm", "at": now,
                    "message": "No model provider is usable. Add the GEMINI_API_KEY secret (free), and GROQ_API_KEY "
                               "as a fallback, then run the doctor from System."})
    today_rows = ctx.store.select("quota", "day = ?", (timeutil.now().strftime("%Y-%m-%d"),))
    failing = [q for q in today_rows if q.get("last_error_at") and not q.get("exhausted_at")
               and (not q.get("last_ok_at") or q["last_error_at"] > q["last_ok_at"])]
    if failing and not any(int(q.get("requests") or 0) for q in today_rows):
        detail = "; ".join(f"{q['provider']}: {str(q.get('last_error') or '')[:120]}" for q in failing)
        out.append({"level": "error", "code": "llm_failing", "at": max(q["last_error_at"] for q in failing),
                    "message": f"No model has answered today, so new cards arrive as briefs. {detail}. "
                               "Run the doctor from System for details."})
    if os.environ.get("PBS_DATA_PUBLIC") == "1":
        out.append({"level": "error", "code": "data_public", "at": now,
                    "message": "Your data repo is public, so anyone can read your drafts, answers, stances and "
                               "profile. Make it private: the repo's Settings → General → Change visibility."})
    if not ctx.blocklist:
        out.append({"level": "warn", "code": "no_blocklist", "at": now,
                    "message": "The PBS_BLOCKLIST secret is empty, so the employer and client check can't run. Add "
                               "one term per line."})
    for w in ctx.settings_warnings:
        out.append({"level": "warn", "code": "settings", "message": w, "at": now})
    exhausted = ctx.store.select("quota", "day = ? AND exhausted_at IS NOT NULL", (timeutil.now().strftime("%Y-%m-%d"),))
    for q in exhausted:
        out.append({"level": "info", "code": "quota", "at": q["exhausted_at"],
                    "message": f"{q['provider']} reached its free daily quota; other providers are used until it resets."})
    failing = ctx.store.count("sources", "active = 1 AND consecutive_failures >= 3")
    if failing:
        out.append({"level": "info", "code": "sources_failing", "at": now,
                    "message": f"{failing} source(s) have failed three or more runs in a row. See Sources."})
    paused = ctx.store.count("sources", "active = 0 AND paused_reason IS NOT NULL")
    if paused:
        out.append({"level": "info", "code": "sources_paused", "at": now,
                    "message": f"{paused} source(s) were paused automatically. See Sources."})
    review = ctx.store.count("metrics", "status = 'needs_review'")
    if review:
        out.append({"level": "info", "code": "metrics_review", "at": now,
                    "message": f"{review} extracted number(s) need a quick check on the Metrics page."})
    local = ctx.local_now()
    if (not ctx.store.get("deliveries", f"dly_{local.date().isoformat()}")
            and local.strftime("%H:%M") > "07:00" and local.strftime("%H:%M") <= ctx.settings.delivery.latest_local_time):
        out.append({"level": "warn", "code": "no_delivery_today", "at": now,
                    "message": "Today's drafts haven't been delivered yet. Use System → Run morning delivery."})
    pending_props = ctx.store.count("proposals", "status = 'pending'")
    if pending_props:
        out.append({"level": "info", "code": "proposals", "at": now,
                    "message": f"{pending_props} proposal(s) are waiting for your decision on the Insights page."})
    return out


def build(ctx: Ctx) -> dict[str, Any]:
    store = ctx.store
    now = timeutil.now()
    since_cards = timeutil.iso(now - dt.timedelta(days=8))
    since_posts = timeutil.iso(now - dt.timedelta(days=120))
    cards = {c["id"]: c for c in store.select("cards", f"status IN ({','.join('?' for _ in ACTIVE)})", ACTIVE)}
    for c in store.select("cards", "updated_at >= ? OR created_at >= ?", (since_cards, since_cards)):
        cards.setdefault(c["id"], c)
    posts = store.select("posts", "posted_at >= ?", (since_posts,), order="posted_at DESC")
    lm = _latest_metrics(ctx)
    post_card_ids = {p["card_id"] for p in posts[:60]}
    for cid in post_card_ids - set(cards):
        row = store.get("cards", cid)
        if row:
            cards[cid] = row
    titles = {c["id"]: c.get("title") for c in cards.values()}
    post_rows = []
    for p in posts:
        row = dict(p)
        row["title"] = titles.get(p["card_id"]) or (store.get("cards", p["card_id"]) or {}).get("title")
        row["latest_metrics"] = lm.get(p["id"])
        post_rows.append(row)
    sources = []
    for s in store.select("sources", order="scout, name"):
        sources.append({**s, "health": {k: s.get(k) for k in ("last_fetch_at", "last_success_at", "consecutive_failures",
                                                               "last_error", "items_last_run", "items_total")}})
    active_pb = store.select("playbook_versions", "status = 'active'", order="version DESC", limit=1)
    reports = store.select("system_reports", order="week DESC", limit=12)
    voice = store.select("voice_profiles", order="version DESC", limit=1)
    runs = store.select("runs", order="started_at DESC", limit=30)
    run_rows = [{k: v for k, v in r.items() if k != "journal"} for r in runs]
    today = now.strftime("%Y-%m-%d")
    quota = []
    for q in store.select("quota", "day = ?", (today,)):
        spec = ctx.settings.llm.providers.get(q["provider"])
        quota.append({**q, "daily_limit": spec.daily_limit if spec else None})
    delivery = store.select("deliveries", "kind = 'morning'", order="local_date DESC", limit=1)
    since_events = timeutil.iso(now - dt.timedelta(days=14))
    rejected = store.select("processed_events", "status = 'rejected' AND at >= ?", (since_events,), order="at DESC",
                            limit=50)
    processed = [r["id"] for r in store.select("processed_events", "at >= ?",
                                               (timeutil.iso(now - dt.timedelta(days=7)),))]
    doctor = store.select("doctor_reports", order="created_at DESC", limit=1)
    months = sorted({p.stem for p in (ctx.data_root / "db" / "cards").glob("*.jsonl")}, reverse=True) \
        if (ctx.data_root / "db" / "cards").is_dir() else []
    next_local = _next_delivery_local(ctx)
    settings_dict = ctx.settings.model_dump(mode="json")
    state = {
        "meta": {"schema_version": DESK_SCHEMA_VERSION, "generated_at": timeutil.iso(now), "run_id": ctx.run.id,
                 "app_version": __version__, "timezone": ctx.tz, "display_name": ctx.settings.display_name,
                 "next_delivery_local": next_local},
        "settings": settings_dict,
        "settings_overrides": store.get_setting("overrides", {}) or {},
        "delivery": delivery[0] if delivery else None,
        "cards": sorted(cards.values(), key=lambda c: (c.get("created_at") or "", c["id"]), reverse=True),
        "posts": post_rows,
        "metrics": store.select("metrics", "status = 'needs_review' OR created_at >= ?", (since_posts,),
                                order="created_at DESC", limit=400),
        "uploads": store.select("metric_uploads", order="created_at DESC", limit=20),
        "account_stats": store.select("account_stats", order="date DESC", limit=200),
        "stances": store.select("stances", order="tier, issue"),
        "requests": store.select("requests", "created_at >= ? OR status IN ('queued','running')",
                                 (timeutil.iso(now - dt.timedelta(days=30)),), order="created_at DESC"),
        "sources": sources,
        "proposals": store.select("proposals", "status = 'pending' OR created_at >= ?",
                                  (timeutil.iso(now - dt.timedelta(days=60)),), order="created_at DESC"),
        "playbook": active_pb[0] if active_pb else None,
        "playbook_history": store.select("playbook_versions", order="version DESC", limit=10),
        "experiments": store.select("experiments", order="created_at DESC", limit=20),
        "report": reports[0] if reports else None,
        "reports_index": [{"id": r["id"], "week": r["week"], "created_at": r["created_at"]} for r in reports],
        "voice": voice[0] if voice else None,
        "arms": store.select("bandit_arms"),
        "runs": run_rows,
        "quota": quota,
        "warnings": warnings(ctx),
        "stats": stats.compute(ctx),
        "rejected_events": rejected,
        "processed_event_ids": processed,
        "doctor": doctor[0] if doctor else None,
        "archive_months": months,
        "platform_guide": {"reviewed": platform.base_guide().get("reviewed"), "rules": platform.current_rules(ctx),
                           "research": store.get_setting("platform_research_summary")},
    }
    validated = DeskState.model_validate(_drop_nones(state))
    return validated.model_dump(mode="json", exclude_none=True)


def _drop_nones(value: Any) -> Any:
    """Store rows carry explicit nulls; dropping them lets the contract's defaults apply."""
    if isinstance(value, dict):
        return {k: _drop_nones(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_nones(v) for v in value]
    return value


def _next_delivery_local(ctx: Ctx) -> str:
    from .deliver import next_delivery_at

    local = ctx.local_now()
    if ctx.store.get("deliveries", f"dly_{local.date().isoformat()}") or local.strftime("%H:%M") > \
            ctx.settings.delivery.latest_local_time:
        nxt = next_delivery_at(ctx, local.date())
    else:
        nxt = timeutil.at_local_time(local.date(), ctx.settings.delivery.earliest_local_time, ctx.tz)
    return timeutil.local(nxt, ctx.tz).isoformat(timespec="minutes")


def write(ctx: Ctx) -> Path:
    data = build(ctx)
    path = ctx.data_root / "desk" / "desk.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)
    return path
