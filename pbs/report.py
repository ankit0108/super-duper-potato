"""Weekly system report (FR-23): how well the machine is working, plus the small fixes it may make itself.

Auto-applied: pausing zero-yield sources, per-scout candidate counts, exploration rate (bounded).
Everything touching pillars, reward weights or guardrails becomes a proposal for Ankit.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections import Counter, defaultdict
from typing import Any

from . import log, playbook, settings, timeutil
from .context import Ctx

PICKED = ("posted", "editing")


def _between(field: str) -> str:
    return f"{field} >= ? AND {field} < ?"


def _median(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 3) if values else None


def build_report(ctx: Ctx, start: dt.datetime, end: dt.datetime) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    s, e = timeutil.iso(start), timeutil.iso(end)
    store = ctx.store
    cards = store.select("cards", _between("delivered_at"), (s, e))
    delivered = [c for c in cards if c.get("delivery_id") or c.get("kind") in ("request", "adapt")]
    posts = store.select("posts", _between("posted_at"), (s, e))
    sections: dict[str, Any] = {}

    # Source yield over the last four weeks (enough items to judge a source).
    since28 = timeutil.iso(end - dt.timedelta(days=28))
    picked_topics = {c["topic_id"] for c in store.select("cards", "delivered_at >= ?", (since28,))
                     if c["status"] in PICKED and c.get("topic_id")}
    items_by_source: Counter[str] = Counter()
    picked_by_source: Counter[str] = Counter()
    for row in store.conn.execute("SELECT source_id, topic_id FROM items WHERE fetched_at >= ? AND origin = 'scout'",
                                  (since28,)):
        items_by_source[row["source_id"]] += 1
        if row["topic_id"] in picked_topics:
            picked_by_source[row["source_id"]] += 1
    yields = []
    for src in store.select("sources"):
        n = items_by_source.get(src["id"], 0)
        k = picked_by_source.get(src["id"], 0)
        yields.append({"source_id": src["id"], "name": src["name"], "scout": src["scout"], "items_28d": n,
                       "picked_items_28d": k, "yield": round(k / n, 3) if n else None, "active": bool(src["active"]),
                       "failing": int(src.get("consecutive_failures") or 0) >= 3})
        store.update("sources", src["id"], yield_stats={"items_28d": n, "picked_28d": k,
                                                        "yield": round(k / n, 3) if n else None})
    yields.sort(key=lambda y: (-(y["yield"] or 0), -y["items_28d"]))
    sections["source_yield"] = yields

    # Scout hit rate.
    topics = {t["id"]: t for t in store.select("topics", "last_seen_at >= ?", (s,))}
    by_scout: dict[str, Counter[str]] = defaultdict(Counter)
    for c in delivered:
        scout = c.get("kind") if c.get("kind") in ("interview", "request", "evergreen") else (
            topics.get(c.get("topic_id") or "", {}).get("scout") or "news")
        by_scout[scout]["delivered"] += 1
        if c["status"] in PICKED:
            by_scout[scout]["picked"] += 1
    sections["scout_hit_rate"] = [{"scout": k, "delivered": v["delivered"], "picked": v["picked"],
                                   "rate": round(v["picked"] / v["delivered"], 3) if v["delivered"] else None}
                                  for k, v in sorted(by_scout.items())]

    # Ranker accuracy: was his pick the top-ranked card?
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for c in delivered:
        if c.get("delivery_id") and c.get("rank"):
            groups[(c["delivery_id"], c["platform"])].append(c)
    with_pick = top1 = 0
    pick_ranks: list[int] = []
    for group in groups.values():
        picks = [c for c in group if c["status"] in PICKED]
        if picks:
            with_pick += 1
            ranks = sorted(int(c["rank"]) for c in picks)
            pick_ranks.extend(ranks)
            top1 += 1 if ranks[0] == 1 else 0
    sections["ranker_accuracy"] = {"deliveries_with_pick": with_pick, "top1": top1,
                                   "accuracy": round(top1 / with_pick, 3) if with_pick else None,
                                   "mean_pick_rank": round(statistics.mean(pick_ranks), 2) if pick_ranks else None}

    # Drafter quality, overall and by prompt/playbook version.
    prev_posts = store.select("posts", _between("posted_at"), (timeutil.iso(start - (end - start)), s))
    by_version: dict[str, list[float]] = defaultdict(list)
    by_playbook: dict[str, list[float]] = defaultdict(list)
    for p in posts:
        v = (p.get("features") or {}).get("versions") or {}
        if p.get("edit_ratio") is not None:
            by_version[v.get("prompt") or "unknown"].append(p["edit_ratio"])
            by_playbook[v.get("playbook") or "unknown"].append(p["edit_ratio"])
    rewrites = sum(1 for c in delivered if int(c.get("rewrite_count") or 0) > 0)
    sections["drafter_quality"] = {
        "edit_ratio_median": {pl: _median([p["edit_ratio"] for p in posts if p["platform"] == pl]) for pl in ("linkedin", "x")},
        "edit_ratio_median_prev": {pl: _median([p["edit_ratio"] for p in prev_posts if p["platform"] == pl])
                                   for pl in ("linkedin", "x")},
        "rewrite_rate": round(rewrites / len(delivered), 3) if delivered else None,
        "by_prompt_version": {k: {"n": len(v), "edit_ratio_median": _median(v)} for k, v in by_version.items()},
        "by_playbook_version": {k: {"n": len(v), "edit_ratio_median": _median(v)} for k, v in by_playbook.items()},
        "editing_minutes_median": _median([(p.get("editing_seconds") or 0) / 60 for p in posts if p.get("editing_seconds")]),
        "time_to_post_minutes_median": _median([p.get("time_to_post_minutes") for p in posts]),
    }

    # Guardrail catches.
    sections["guardrails"] = {
        "blocked": sum(1 for c in cards if (c.get("flags") or {}).get("blocked")),
        "unsourced": sum(1 for c in cards if (c.get("flags") or {}).get("unsourced")),
        "first_person": sum(1 for c in cards if (c.get("flags") or {}).get("first_person")),
        "sensitive": sum(1 for c in cards if (c.get("flags") or {}).get("sensitive")),
        "posted_with_blocked_terms": sum(1 for p in posts if (p.get("guard") or {}).get("blocked")),
    }

    # Run health.
    runs = store.select("runs", _between("started_at"), (s, e))
    llm_by_provider: Counter[str] = Counter()
    for r in runs:
        llm_by_provider.update((r.get("llm") or {}).get("by_provider") or {})
    deliveries = store.select("deliveries", _between("delivered_at") + " AND kind = 'morning'", (s, e))
    late = [d for d in deliveries if timeutil.local_hhmm(timeutil.parse(d["delivered_at"]), ctx.tz) > "06:30"]  # type: ignore[arg-type]
    days = max(1, round((end - start).total_seconds() / 86400))
    exhausted = store.select("quota", "exhausted_at >= ? AND exhausted_at < ?", (s, e))
    sections["run_health"] = {
        "runs": len(runs), "failed": sum(1 for r in runs if r["status"] == "failed"),
        "partial": sum(1 for r in runs if r["status"] == "partial"),
        "deliveries": len(deliveries), "expected_deliveries": days, "late_deliveries": len(late),
        "degraded_deliveries": sum(1 for d in deliveries if d.get("degraded")),
        "llm_calls": sum(llm_by_provider.values()), "llm_by_provider": dict(llm_by_provider),
        "quota_exhausted": [q["provider"] for q in exhausted],
    }

    # Brand metrics.
    brand: dict[str, Any] = {}
    for pl in ("linkedin", "x"):
        pp = [p for p in posts if p["platform"] == pl]
        hit_days = {timeutil.local_date(timeutil.parse(p["posted_at"]), ctx.tz) for p in pp}  # type: ignore[arg-type]
        stats = store.select("account_stats", "platform = ? AND followers IS NOT NULL", (pl,), order="date")
        brand[pl] = {"posts": len(pp), "hit_days": len(hit_days), "reward_median": _median([p.get("reward") for p in pp]),
                     "followers": stats[-1]["followers"] if stats else None,
                     "followers_prev": next((r["followers"] for r in reversed(stats) if r["date"] < s[:10]), None)}
    sections["brand"] = brand
    return sections, plan_actions(ctx, sections)


def plan_actions(ctx: Ctx, sections: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    total_posts_28d = ctx.store.count("posts", "posted_at >= ?",
                                      (timeutil.iso(timeutil.now() - dt.timedelta(days=28)),))
    weeks = ctx.settings.scouting.pause_after_zero_yield_weeks
    if total_posts_28d >= 20:
        for y in sections["source_yield"]:
            src = ctx.store.get("sources", y["source_id"])
            if not src or not src["active"] or y["items_28d"] < 10 or y["picked_items_28d"] > 0:
                continue
            age = timeutil.hours_between(timeutil.parse(src.get("created_at")), timeutil.now()) or 0
            if age >= weeks * 7 * 24:
                actions.append({"type": "pause_source", "source_id": src["id"],
                                "reason": f"No picked cards from {y['items_28d']} items in {weeks} weeks"})
    rates = [r for r in sections["scout_hit_rate"] if r["rate"] is not None and r["delivered"] >= 10
             and r["scout"] in ctx.settings.scouting.candidates_per_scout]
    if rates:
        mean = statistics.mean(r["rate"] for r in rates)
        for r in rates:
            current = ctx.settings.scouting.candidates_per_scout[r["scout"]]
            if mean and r["rate"] > 1.5 * mean:
                new = min(60, int(round(current * 1.2)))
            elif r["rate"] < 0.5 * mean:
                new = max(4, int(round(current * 0.8)))
            else:
                continue
            if new != current:
                actions.append({"type": "candidates_per_scout", "scout": r["scout"], "from": current, "to": new})
    acc = sections["ranker_accuracy"]
    rate = ctx.settings.learning.explore_rate
    if acc["accuracy"] is not None and acc["deliveries_with_pick"] >= 5:
        if acc["accuracy"] < 0.25 and rate < 0.35:
            actions.append({"type": "explore_rate", "from": rate, "to": round(min(0.35, rate + 0.05), 2),
                            "reason": f"Top-ranked card picked only {int(acc['accuracy'] * 100)}% of the time"})
        elif acc["accuracy"] >= 0.5 and rate > 0.2:
            actions.append({"type": "explore_rate", "from": rate, "to": 0.2, "reason": "Ranker accuracy recovered"})
    return actions


def apply_actions(ctx: Ctx, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    applied = []
    for a in actions:
        if a["type"] == "pause_source":
            ctx.store.update("sources", a["source_id"], active=False, paused_reason=a["reason"],
                             updated_at=timeutil.now_iso())
            applied.append(a)
        elif a["type"] in ("candidates_per_scout", "explore_rate"):
            patch = ({"scouting": {"candidates_per_scout": {a["scout"]: a["to"]}}} if a["type"] == "candidates_per_scout"
                     else {"learning": {"explore_rate": a["to"]}})
            current = dict(ctx.store.get_setting("overrides", {}) or {})
            new, error = settings.validate_patch(current, patch)
            if error:
                log.warn(f"report: couldn't apply {a['type']}: {error}")
                continue
            ctx.store.set_setting("overrides", new)
            applied.append(a)
    if applied:
        ctx.reload_settings()
    return applied


def health_proposals(ctx: Ctx, sections: dict[str, Any]) -> list[str]:
    """Flag prompts for review when edit ratio rises, and suggest the strongest free model after 4 flat weeks."""
    ids: list[str] = []
    dq = sections["drafter_quality"]
    for pl in ("linkedin", "x"):
        now_m, prev_m = dq["edit_ratio_median"].get(pl), dq["edit_ratio_median_prev"].get(pl)
        if now_m is not None and prev_m is not None and now_m > prev_m + 0.05:
            ids.append(playbook.create_proposal(
                ctx, kind="prompt_review", title=f"Review {pl} drafting: edit ratio rose from {prev_m} to {now_m}",
                detail="Drafts needed more editing this week than last. Check the latest playbook changes and voice "
                       "rules on the Insights page; revert a change if it made things worse.", payload={},
                confidence="medium", source="report"))
    reports = ctx.store.select("system_reports", order="week DESC", limit=4)
    if len(reports) >= 4:
        medians = [((r.get("sections") or {}).get("drafter_quality") or {}).get("edit_ratio_median", {}) for r in reports]
        for pl in ("linkedin", "x"):
            series = [m.get(pl) for m in reversed(medians) if m.get(pl) is not None]
            routes = ctx.settings.llm.routes.get("draft", [])
            if len(series) >= 4 and series[-1] >= series[0] - 0.02 and routes and routes[0] != "github_strong":
                ids.append(playbook.create_proposal(
                    ctx, kind="model_upgrade", title="Edit ratio is flat after four weeks: try the strongest free model",
                    detail="Put GitHub Models' strongest model first for drafting (still $0). If that doesn't help, the "
                           "one paid upgrade is a stronger drafting model, set in Settings → Models.",
                    payload={"patch": {"llm": {"routes": {"draft": ["github_strong", *[r for r in routes if r != "github_strong"]]}}}},
                    confidence="medium", source="report"))
                break
    return ids
