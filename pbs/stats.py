"""Numbers for the desk's Insights page, including progress toward the rollout gates."""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict
from typing import Any

from . import feedback, timeutil
from .context import Ctx

PICKED = ("posted", "editing")


def _median(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.median(vals), 3) if vals else None


def compute(ctx: Ctx) -> dict[str, Any]:
    tz = ctx.tz
    today = ctx.local_date()
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=12 * 7 + 1))
    cards = ctx.store.select("cards", "delivered_at >= ?", (since,))
    posts = ctx.store.select("posts", "posted_at >= ?", (since,))

    def lday(ts: str | None) -> dt.date | None:
        t = timeutil.parse(ts)
        return timeutil.local_date(t, tz) if t else None

    # Weekly series (ISO weeks, local time).
    weeks: dict[str, dict[str, Any]] = {}
    for i in range(11, -1, -1):
        d = today - dt.timedelta(weeks=i)
        weeks[timeutil.iso_week(d)] = {"week": timeutil.iso_week(d)}
    for platform in ("linkedin", "x"):
        buckets: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
        for c in cards:
            if c["platform"] != platform or not c.get("delivery_id"):
                continue
            wk = timeutil.iso_week(lday(c["delivered_at"]))  # type: ignore[arg-type]
            b = buckets[wk]
            b["delivered"].append(1)
            b["picked"].append(1 if c["status"] in PICKED else 0)
            b["skipped"].append(1 if c["status"] == "skipped" else 0)
            b["expired"].append(1 if c["status"] == "expired" else 0)
            b["rewritten"].append(1 if int(c.get("rewrite_count") or 0) > 0 else 0)
            if c["status"] in PICKED and c.get("rank"):
                b["pick_ranks"].append(int(c["rank"]))
        for p in posts:
            if p["platform"] != platform:
                continue
            day = lday(p["posted_at"])
            wk = timeutil.iso_week(day)  # type: ignore[arg-type]
            b = buckets[wk]
            b["posts"].append(1)
            b["days"].append(day)
            b["edit_ratio"].append(p.get("edit_ratio"))
            b["reward"].append(p.get("reward"))
            b["ttp"].append(p.get("time_to_post_minutes"))
            if p.get("editing_seconds"):
                b["editing"].append(p["editing_seconds"] / 60)
        for wk, row in weeks.items():
            b = buckets.get(wk, {})
            delivered = sum(b.get("delivered", []))
            rank1 = [r for r in b.get("pick_ranks", [])]
            row[platform] = {
                "posts": sum(b.get("posts", [])),
                "hit_days": len(set(b.get("days", []))),
                "delivered": delivered,
                "picked": sum(b.get("picked", [])),
                "skipped": sum(b.get("skipped", [])),
                "expired": sum(b.get("expired", [])),
                "rewrite_rate": round(sum(b.get("rewritten", [])) / delivered, 3) if delivered else None,
                "rank1_rate": round(sum(1 for r in rank1 if r == 1) / len(rank1), 3) if rank1 else None,
                "edit_ratio_median": _median(b.get("edit_ratio", [])),
                "reward_median": _median(b.get("reward", [])),
                "time_to_post_median": _median(b.get("ttp", [])),
                "editing_minutes_median": _median(b.get("editing", [])),
            }

    # Daily (last 28 days).
    daily = []
    posts_by_day: dict[tuple[dt.date, str], int] = defaultdict(int)
    for p in posts:
        posts_by_day[(lday(p["posted_at"]), p["platform"])] += 1  # type: ignore[index]
    delivered_days = {r["local_date"]: r for r in ctx.store.select("deliveries", "kind = 'morning'")}
    for i in range(27, -1, -1):
        d = today - dt.timedelta(days=i)
        dl = delivered_days.get(d.isoformat())
        daily.append({"date": d.isoformat(), "linkedin": posts_by_day.get((d, "linkedin"), 0),
                      "x": posts_by_day.get((d, "x"), 0), "delivered": bool(dl),
                      "delivered_local": timeutil.local_hhmm(timeutil.parse(dl["delivered_at"]), tz) if dl else None})  # type: ignore[arg-type]

    # Pillar mix over 28 days vs weights.
    since28 = timeutil.iso(timeutil.now() - dt.timedelta(days=28))
    mix: dict[str, dict[str, Any]] = {}
    for platform in ("linkedin", "x"):
        weights = ctx.settings.normalized_weights(platform)
        rows = {k: {"label": ctx.settings.pillar(platform, k).label, "weight": round(w, 3),  # type: ignore[union-attr]
                    "delivered": 0, "picked": 0, "posted": 0} for k, w in weights.items()}
        for c in cards:
            if c["platform"] != platform or (c.get("delivered_at") or "") < since28 or c["pillar"] not in rows:
                continue
            rows[c["pillar"]]["delivered"] += 1
            rows[c["pillar"]]["picked"] += 1 if c["status"] in PICKED else 0
            rows[c["pillar"]]["posted"] += 1 if c["status"] == "posted" else 0
        mix[platform] = rows

    followers = {pl: [{"date": r["date"], "followers": r["followers"]} for r in
                      ctx.store.select("account_stats", "platform = ? AND followers IS NOT NULL", (pl,), order="date")]
                 for pl in ("linkedin", "x")}
    return {"weekly": list(weeks.values()), "daily": daily, "pillar_mix": mix, "followers": followers,
            "streak": _streak(daily), "gates": _gates(ctx, daily, weeks),
            # What the ranking learns from tomorrow (Insights shows it, so he can see his reasons being used).
            "feedback": feedback.recent_feedback(ctx, days=30, limit=15),
            "crossposts": _crossposts(ctx)}


def _crossposts(ctx: Ctx) -> dict[str, Any]:
    """Versions made for the other platform in the last 30 days, and how many went out."""
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=30))
    out: dict[str, Any] = {"linkedin_to_x": 0, "x_to_linkedin": 0, "both": 0, "switch": 0, "made": 0, "posted": 0}
    for i in ctx.store.select("interactions", "type = 'crosspost' AND at >= ?", (since,)):
        data = i.get("data") or {}
        out["x_to_linkedin" if data.get("to") == "linkedin" else "linkedin_to_x"] += 1
        out["switch" if data.get("mode") == "switch" else "both"] += 1
    for c in ctx.store.select("cards", "crosspost_of IS NOT NULL AND created_at >= ?", (since,)):
        out["made"] += 1
        out["posted"] += 1 if c["status"] == "posted" else 0
    return out


def _streak(daily: list[dict[str, Any]]) -> dict[str, int]:
    out = {}
    for platform in ("linkedin", "x", "both"):
        n = 0
        for row in reversed(daily):
            ok = (row["linkedin"] > 0 and row["x"] > 0) if platform == "both" else row[platform] > 0
            if ok:
                n += 1
            elif row is daily[-1]:
                continue  # today isn't over yet
            else:
                break
        out[platform] = n
    return out


def _gates(ctx: Ctx, daily: list[dict[str, Any]], weeks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    last7 = daily[-7:]
    on_time = sum(1 for d in last7 if d["delivered"] and (d["delivered_local"] or "99") <= "06:15")
    last14 = daily[-14:]
    both14 = sum(1 for d in last14 if d["linkedin"] > 0 and d["x"] > 0)
    week_rows = list(weeks.values())[-5:]
    editing = [w[pl]["editing_minutes_median"] for w in week_rows[-2:] for pl in ("linkedin", "x")
               if w[pl]["editing_minutes_median"] is not None]
    falling = 0
    for pl in ("linkedin", "x"):
        series = [w[pl]["edit_ratio_median"] for w in week_rows if w[pl]["edit_ratio_median"] is not None]
        falling = max(falling, sum(1 for a, b in zip(series, series[1:], strict=False) if b < a))
    both30 = _streak(daily)["both"]
    return [
        {"gate": 1, "name": "Shadow week", "target": "On-time delivery on 6 of 7 days", "value": f"{on_time}/7",
         "met": on_time >= 6},
        {"gate": 2, "name": "Daily posting", "target": "Posted on both platforms on 12 of 14 days, editing ≤ 15 min",
         "value": f"{both14}/14 days" + (f", {round(statistics.median(editing), 1)} min" if editing else ""),
         "met": both14 >= 12 and (not editing or statistics.median(editing) <= 15)},
        {"gate": 3, "name": "Learning on", "target": "Edit ratio falling in 3 of 4 weeks", "value": f"{falling}/4",
         "met": falling >= 3},
        {"gate": 4, "name": "v1", "target": "30 consecutive days posting on both platforms", "value": f"{both30}/30",
         "met": both30 >= 30},
    ]
