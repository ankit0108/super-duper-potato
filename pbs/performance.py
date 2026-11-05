"""What the numbers say: a performance review written from the analytics (FR-44).

The numbers are worked out here, exactly: per post the engagement rate, per platform the medians, the best and
weakest posts, days of the week, hours, formats and topics. The strongest model the keys allow then reads them
with the posts and writes what's working, what isn't and what to try next. Its route starts with Gemini Pro
(the free tier's strongest model, when the key has it) and falls back to Flash, Groq and the rest; the review
records which model wrote it, and the desk shows that.

It's written again whenever an upload brings new numbers, or when he asks ("Analyse again").
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import AllProvidersFailed, BudgetExhausted, LLMError, LLMRequest, why_unavailable

KEY = "performance_review"
DUE_KEY = "performance_due"  # set when a review had to wait for model quota: the next run tries again
MIN_POSTS = 3
MAX_POSTS = 150
ENGAGEMENT_PARTS = ("reactions", "comments", "reposts", "sends", "saves")
NUMBERS = ("impressions", "members_reached", "reactions", "comments", "reposts", "sends", "saves", "engagements",
           "followers_gained", "profile_views", "link_clicks")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class _Finding(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=1)
    detail: str = ""
    evidence: str = ""


class _Review(BaseModel):
    model_config = ConfigDict(extra="ignore")
    headline: str = ""
    findings: list[_Finding] = []
    what_works: list[str] = []
    what_doesnt: list[str] = []
    try_next: list[str] = []
    audience: str = ""
    caveats: list[str] = []

    @field_validator("what_works", "what_doesnt", "try_next", "caveats", mode="before")
    @classmethod
    def _lines(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [v]
        return [textutil.normalize_ws(str(x)) for x in (v or []) if str(x or "").strip()][:6]


def latest(ctx: Ctx) -> dict[str, Any] | None:
    review = ctx.store.get_setting(KEY)
    return {**review, "coverage": coverage(ctx)} if review else None


def coverage(ctx: Ctx) -> dict[str, Any]:
    """Data coverage is computed even when no AI review can run; missing is never a zero result."""
    from .learn import latest_metrics

    latest_by = latest_metrics(ctx)
    result = {}
    for platform in ("linkedin", "x"):
        posts = ctx.store.select("posts", "platform = ?", (platform,))
        measured = [latest_by[p["id"]] for p in posts if p["id"] in latest_by
                    and latest_by[p["id"]].get("impressions") is not None]
        result[platform] = {
            "published": len(posts), "measured": len(measured), "missing": len(posts) - len(measured),
            "needs_review": ctx.store.count("metrics", "platform = ? AND status = 'needs_review'", (platform,)),
            "latest_capture": max((m.get("captured_at") or "" for m in measured), default=None),
        }
    return result


def due(ctx: Ctx) -> bool:
    return bool(ctx.store.get_setting(DUE_KEY))


def _engagement(m: dict[str, Any]) -> int | None:
    if m.get("engagements") is not None:
        return int(m["engagements"])
    parts = [m.get(k) for k in ENGAGEMENT_PARTS if m.get(k) is not None]
    return sum(parts) if parts else None


def _rate(m: dict[str, Any]) -> float | None:
    eng, imp = _engagement(m), m.get("impressions")
    return round(100 * eng / imp, 2) if eng is not None and imp else None


def _post_rows(ctx: Ctx) -> list[dict[str, Any]]:
    """Each post's latest numbers: the posts PBS drafted (confirmed) and the rest from exports (history)."""
    latest_by: dict[str, dict[str, Any]] = {}
    for m in ctx.store.select("metrics", "status IN ('confirmed', 'history')", order="captured_at"):
        raw = m.get("raw") or {}
        key = m.get("post_id") or raw.get("url") or f"{m.get('platform')}:{raw.get('posted_date')}:" \
            f"{textutil.title_key(raw.get('text_snippet') or '')[:40]}"
        # A snapshot is one observation. Combining today's impressions with last week's likes invents a rate.
        latest_by[f"{m.get('platform')}:{key}"] = m
    posts = {p["id"]: p for p in ctx.store.select("posts")}
    rows: list[dict[str, Any]] = []
    for m in latest_by.values():
        raw = m.get("raw") or {}
        post = posts.get(m.get("post_id") or "")
        row: dict[str, Any] = {"platform": m.get("platform") or (post or {}).get("platform"),
                               "source": "pbs" if post else "history"}
        if post:
            when = timeutil.local(timeutil.parse(post["posted_at"]), ctx.tz)  # type: ignore[arg-type]
            text = post.get("final_text") or ""
            fmt = ctx.settings.formats.get(post.get("format") or "")
            pillar = ctx.settings.pillar(post["platform"], post["pillar"]) if post.get("pillar") else None
            row.update(date=when.date().isoformat(), weekday=WEEKDAYS[when.weekday()], hour=when.hour,
                       format=fmt.label if fmt else post.get("format"), topic=pillar.label if pillar else None,
                       opening=textutil.truncate(text, 160), length=len(text),
                       hashtags=len(post.get("hashtags") or []), url=post.get("post_url"))
        else:
            day = raw.get("posted_date")
            parsed = timeutil.parse(day) if day else None
            text = raw.get("text_snippet") or ""
            row.update(date=day, weekday=WEEKDAYS[parsed.weekday()] if parsed else None,
                       opening=textutil.truncate(text, 160) if text and not text.startswith("http") else None,
                       url=raw.get("url"))
        row.update({k: m[k] for k in NUMBERS if m.get(k) is not None})
        row["engagement"] = _engagement(m)
        row["engagement_rate"] = _rate(m)
        row["captured_at"] = m.get("captured_at")
        row["measurement_scope"] = "export_period" if m.get("source") == "file" else "snapshot"
        rows.append({k: v for k, v in row.items() if v is not None})
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    return rows[:MAX_POSTS]


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def _groups(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    by: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r.get(field) is not None:
            by[r[field]].append(r)
    out = [{field: k, "posts": len(v),
            "measured_posts": sum(r.get("impressions") is not None for r in v),
            "evidence": "insufficient" if sum(r.get("impressions") is not None for r in v) < 5 else "observational",
            "median_impressions": _median([r["impressions"] for r in v if r.get("impressions") is not None]),
            "median_rate": _median([r["engagement_rate"] for r in v if r.get("engagement_rate") is not None])}
           for k, v in by.items()]
    return sorted(out, key=lambda g: -(g["median_impressions"] or 0))


def _brief(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in ("date", "weekday", "format", "topic", "opening", "url", "impressions", "engagement",
                              "engagement_rate") if r.get(k) is not None}


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The numbers per platform, worked out exactly so the model only has to read them."""
    out: dict[str, Any] = {}
    for platform in ("linkedin", "x"):
        mine = [r for r in rows if r.get("platform") == platform]
        if not mine:
            continue
        rated = [r for r in mine if r.get("engagement_rate") is not None]
        by_imp = sorted([r for r in mine if r.get("impressions") is not None], key=lambda r: -r["impressions"])
        by_rate = sorted(rated, key=lambda r: -r["engagement_rate"])
        rate_impressions = sum(r["impressions"] for r in rated)
        out[platform] = {
            "posts": len(mine), "drafted_by_pbs": sum(1 for r in mine if r["source"] == "pbs"),
            "first": min((r["date"] for r in mine if r.get("date")), default=None),
            "last": max((r["date"] for r in mine if r.get("date")), default=None),
            "median_impressions": _median([r["impressions"] for r in by_imp]),
            "median_engagement_rate": _median([r["engagement_rate"] for r in rated]),
            "rate_posts": len(rated),
            "weighted_engagement_rate": round(100 * sum(r["engagement"] for r in rated) / rate_impressions, 2)
            if rate_impressions else None,
            "total_impressions": sum(r["impressions"] for r in by_imp),
            "most_seen": [_brief(r) for r in by_imp[:5]],
            "least_seen": [_brief(r) for r in by_imp[-3:]] if len(by_imp) > 5 else [],
            "best_rate": [_brief(r) for r in by_rate[:5]],
            "by_weekday": _groups(mine, "weekday"),
            "by_hour": _groups(mine, "hour"),
            "by_format": _groups(mine, "format"),
            "by_topic": _groups(mine, "topic"),
            "by_posting_window": _groups(mine, "in_posting_window"),
        }
    return out


def _followers(ctx: Ctx) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for platform in ("linkedin", "x"):
        rows = [r for r in ctx.store.select("account_stats", "platform = ?", (platform,), order="date")
                if r.get("followers") is not None]
        if rows:
            out[platform] = {"first": {"date": rows[0]["date"], "followers": rows[0]["followers"]},
                             "latest": {"date": rows[-1]["date"], "followers": rows[-1]["followers"]}}
    return out


def _days(ctx: Ctx) -> dict[str, Any]:
    """The daily series, as weekly sums (the last 26 weeks), so a long export stays short."""
    from .metrics import DAYS_KEY

    out: dict[str, Any] = {}
    for platform, series in (ctx.store.get_setting(DAYS_KEY, {}) or {}).items():
        weeks: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for day, values in series.items():
            parsed = timeutil.parse(day)
            if parsed is None:
                continue
            week = timeutil.iso_week(parsed.date())
            for k, v in values.items():
                weeks[week][k] += int(v)
            weeks[week]["days"] += 1
        out[platform] = [{"week": w, **weeks[w]} for w in sorted(weeks)[-26:]]
    return out


def _audience(rows: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    """Who follows him and who saw his posts, each by category: the top five with their share."""
    out: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for a in rows:
        group = out[a.get("group") or "followers"][a.get("category") or "Other"]
        if len(group) < 5:
            share = a.get("share")
            group.append(f"{a.get('value')} ({share:g}%)" if isinstance(share, (int, float)) else str(a.get("value")))
    return {g: dict(c) for g, c in out.items()}


def _period_start(totals: dict[str, Any]) -> str | None:
    """The first day of the export's own period ("10/7/2026 - 11/3/2026")."""
    from .analytics_files import date

    starts = [d for t in totals.values() if (d := date(str(t.get("period") or "").split(" - ")[0]))]
    return min(starts) if starts else None


def gather(ctx: Ctx) -> dict[str, Any]:
    from .draft import profile_text
    from .metrics import AUDIENCE_KEY, TOTALS_KEY

    rows = _post_rows(ctx)
    totals = ctx.store.get_setting(TOTALS_KEY, {}) or {}
    for r in rows:
        start = _period_start({r["platform"]: totals.get(r["platform"], {})})
        if start and r.get("date") and r["date"] < start:
            r["published_before_period"] = True
    audience = {p: _audience(v.get("rows") or []) for p, v in (ctx.store.get_setting(AUDIENCE_KEY, {}) or {}).items()}
    windows: dict[str, Any] = {}
    for platform in ("linkedin", "x"):
        spec = getattr(ctx.settings.posting, platform)
        if (span := spec.hours()) is None:
            continue
        windows[platform] = spec.window
        for r in rows:
            if r.get("platform") == platform and r.get("hour") is not None:
                r["in_posting_window"] = span[0] <= r["hour"] <= span[1]
    return {"summary": summarise(rows), "posts": rows, "followers": _followers(ctx), "days": _days(ctx),
            "coverage": coverage(ctx),
            "audience": audience, "totals": totals, "posting_window": windows,
            "goals": textutil.truncate(profile_text(ctx.settings.profile), 1200)}


def run(ctx: Ctx) -> dict[str, Any]:
    """Write the review and keep it (setting performance_review). Counts only in the log."""
    data = gather(ctx)
    rows = data["posts"]
    platforms = sorted(data["summary"])
    periods = [t.get("period") for t in data["totals"].values() if t.get("period")]
    base: dict[str, Any] = {"at": timeutil.now_iso(), "posts": len(rows), "platforms": platforms,
                            "period": periods[0] if len(periods) == 1 else _period(rows), "coverage": data["coverage"]}
    if len(rows) < MIN_POSTS and not (data["days"] or data["totals"]):
        review = {**base, "status": "too_little",
                  "headline": f"Only {len(rows)} post{'s' if len(rows) != 1 else ''} with numbers so far: "
                              f"upload an export covering a few weeks for a review."}
        ctx.store.set_setting(KEY, review)
        ctx.store.set_setting(DUE_KEY, False)
        return {"status": "too_little", "posts": len(rows)}
    prompt = prompting.render("performance", display_name=ctx.settings.display_name,
                              today=ctx.local_date_str(), input_json=data)
    req = LLMRequest(task="analysis", prompt=prompt, max_output_tokens=4000,
                     system="You are a data-literate social media analyst. You read every number and never "
                            "invent one.",
                     prompt_version=prompting.version("performance"))
    old = latest(ctx) or {}
    kept = old.get("status") == "ok"  # a good review stays up, with a note, when a new one can't be written
    ctx.store.set_setting(DUE_KEY, False)
    errors_before = len(ctx.llm.usage.errors)
    try:
        out, resp = ctx.llm.call_json(req, _Review)
    except BudgetExhausted as exc:
        ctx.store.set_setting(KEY, {**old, "error": why_unavailable(exc)} if kept
                              else {**base, "status": "waiting", "error": why_unavailable(exc)})
        ctx.store.set_setting(DUE_KEY, True)
        log.info("performance: waiting for model quota")
        return {"status": "waiting", "posts": len(rows)}
    except (AllProvidersFailed, LLMError, ValueError) as exc:
        ctx.store.set_setting(KEY, {**old, "error": "the models couldn't be reached"} if kept
                              else {**base, "status": "failed", "error": "No model could write the review"})
        log.info(f"performance: failed ({type(exc).__name__})")
        return {"status": "failed", "posts": len(rows)}
    passed = _passed_over(ctx.llm.usage.errors[errors_before:], resp.provider)
    review = {**base, "status": "ok", "model": resp.model, "provider": resp.provider, "passed_over": passed,
              **out.model_dump()}
    review["findings"] = review["findings"][:6]
    limits = [f"{p}: no confirmed post impressions; no performance conclusion is available."
              for p, c in data["coverage"].items() if c["published"] and not c["measured"]]
    limits.append("Day, time and topic comparisons are observational; small groups are experiments, not rules.")
    review["caveats"] = list(dict.fromkeys([*limits, *review["caveats"]]))[:6]
    today = ctx.local_date_str()
    if resp.provider not in STRONG and any(p["provider"] in STRONG and p["why"] == "busy" for p in passed) \
            and old.get("retried") != today:
        # A stronger model was only busy: try again on the next run (once a day), keeping this one meanwhile.
        review["retried"] = today
        review["retry"] = True
        ctx.store.set_setting(DUE_KEY, True)
    elif old.get("retried") == today:
        review["retried"] = today
    ctx.store.set_setting(KEY, review)
    log.info(f"performance: review written from {len(rows)} posts ({len(review['findings'])} findings)")
    return {"status": "ok", "posts": len(rows), "findings": len(review["findings"])}


STRONG = ("gemini_pro", "gemini")


def _passed_over(errors: list[str], answered: str) -> list[dict[str, str]]:
    """The models tried before the one that wrote the review, and why each didn't (from the run's error log:
    "analysis/<provider>: <error>")."""
    out: list[dict[str, str]] = []
    for e in errors:
        if not e.startswith("analysis/"):
            continue
        provider, _, text = e.removeprefix("analysis/").partition(": ")
        if provider == answered or any(p["provider"] == provider for p in out):
            continue
        low = text.lower()
        why = "quota" if "quota" in low or "429" in low else \
            "busy" if any(w in low for w in ("503", "overload", "server error", "no answer within", "unavailable")) \
            else "error"
        out.append({"provider": provider, "why": why})
    return out


def _period(rows: list[dict[str, Any]]) -> str | None:
    days = sorted(r["date"] for r in rows if r.get("date"))
    return f"{days[0]} to {days[-1]}" if days else None
