"""Analytics → numbers matched to posts (FR-20). Low-confidence matches wait for review.

Two kinds of upload: exports (LinkedIn's .xlsx, X's .csv), read exactly by pbs/analytics_files.py with no model
involved, and screenshots, read by the vision model. Exported posts that PBS didn't draft are kept as history:
they count in the performance review (pbs/performance.py) but not in the learner's rewards.
"""

from __future__ import annotations

import difflib
import shutil
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import analytics_files, ids, log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import BudgetExhausted, LLMRequest, why_unavailable

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
SUFFIXES = (*MIME, *analytics_files.FILE_SUFFIXES)
FIELDS = ("impressions", "reactions", "comments", "reposts", "sends", "followers_gained", "profile_views", "link_clicks")
FILE_FIELDS = (*FIELDS, "engagements", "saves", "members_reached")
DAYS_KEY = "analytics_days"
AUDIENCE_KEY = "analytics_audience"
TOTALS_KEY = "analytics_totals"
KEEP_DAYS = 400


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().lower().replace(",", "")
    mult = 1
    if s.endswith("k"):
        mult, s = 1000, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


class _PostMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text_snippet: str = ""
    posted_date: str | None = None
    impressions: int | None = None
    reactions: int | None = None
    comments: int | None = None
    reposts: int | None = None
    sends: int | None = None
    followers_gained: int | None = None
    profile_views: int | None = None
    link_clicks: int | None = None
    confidence: float = 0.7

    @field_validator(*FIELDS, mode="before")
    @classmethod
    def _num(cls, v: Any) -> int | None:
        return _to_int(v)


class _Account(BaseModel):
    model_config = ConfigDict(extra="ignore")
    followers: int | None = None
    profile_views: int | None = None

    @field_validator("followers", "profile_views", mode="before")
    @classmethod
    def _num(cls, v: Any) -> int | None:
        return _to_int(v)


class _VisionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    platform: str | None = None
    kind: str | None = None
    posts: list[_PostMetrics] = Field(default_factory=list)
    account: _Account | None = None


def match_post(ctx: Ctx, platform: str | None, snippet: str, date: str | None) -> tuple[str | None, float]:
    """Best matching post by opening text, platform and date proximity."""
    rows = ctx.store.select("posts", "platform = ?" if platform in ("linkedin", "x") else "1 = 1",
                            (platform,) if platform in ("linkedin", "x") else (), order="posted_at DESC", limit=60)
    snip = textutil.normalize_ws(snippet).casefold()[:160]
    best: tuple[str | None, float] = (None, 0.0)
    second = 0.0
    target = timeutil.parse(date) if date else None
    for post in rows:
        text = textutil.normalize_ws(post["final_text"]).casefold()
        if not snip:
            sim = 0.0
        else:
            window = text[: max(len(snip) + 40, 80)]
            sim = difflib.SequenceMatcher(a=snip, b=window, autojunk=False).ratio()
            if snip in text:
                sim = max(sim, 0.95)
        if target is not None:
            gap = abs((timeutil.parse(post["posted_at"]) - target).total_seconds()) / 86400  # type: ignore[operator]
            sim *= 1.0 if gap <= 2 else 0.85
        if sim > best[1]:
            second = best[1]
            best = (post["id"], sim)
        elif sim > second:
            second = sim
    confidence = best[1] if best[1] - second >= 0.1 else best[1] * 0.8
    return best[0], round(confidence, 3)


def process_uploads(ctx: Ctx) -> dict[str, int]:
    stats = {"uploads": 0, "metrics": 0, "needs_review": 0, "failed": 0}
    for upload in ctx.store.select("metric_uploads", "status = 'pending'", order="created_at"):
        stats["uploads"] += 1
        results: list[dict[str, Any]] = []
        error = None
        for rel in upload.get("paths") or []:
            path = ctx.data_root / rel
            if not path.is_file():
                error = f"missing file {rel}"
                continue
            try:
                if path.suffix.lower() in analytics_files.FILE_SUFFIXES:
                    res = import_file(ctx, path, upload)
                else:
                    res = _extract(ctx, path.read_bytes(), MIME.get(path.suffix.lower(), "image/jpeg"), upload)
                results.append({"path": rel, **res})
                stats["metrics"] += res["metrics"]
                stats["needs_review"] += res["needs_review"]
            except BudgetExhausted as exc:
                error = f"Waiting: {why_unavailable(exc)}; will retry on the next run"
                break
            except Exception as exc:  # noqa: BLE001
                log.error(f"metrics:{upload['id']}", exc)
                results.append({"path": rel, "error": type(exc).__name__})
                stats["failed"] += 1
        if error and error.startswith("Waiting"):
            ctx.store.update("metric_uploads", upload["id"], error=error)
            break
        week = upload.get("week") or timeutil.iso_week(ctx.local_date())
        for rel in upload.get("paths") or []:
            src = ctx.data_root / rel
            if src.is_file():
                dest = ctx.data_root / "media" / "metrics" / week / src.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
        ctx.store.update("metric_uploads", upload["id"], status="processed" if results else "failed",
                         processed_at=timeutil.now_iso(), results={"files": results}, error=error)
    if stats["uploads"]:
        log.info(f"metrics: {stats['metrics']} numbers extracted, {stats['needs_review']} need review")
    if stats["metrics"]:
        ctx.hints.add("analysis")  # new numbers: the performance review is written again
    return stats


def import_file(ctx: Ctx, path: Any, upload: dict[str, Any]) -> dict[str, Any]:
    """An analytics export: every post's numbers (matched to PBS's posts, or kept as history), the daily series,
    the audience and the follower count. Importing the same export again the same day changes nothing."""
    parsed = analytics_files.parse(path)
    res: dict[str, Any] = {"kind": "file", "platform": parsed.platform, "metrics": 0, "needs_review": 0,
                           "matched": 0, "history": 0, **{k: v for k, v in parsed.summary().items()
                                                         if k in ("days", "audience", "followers")}}
    if parsed.empty:
        res["error"] = "No analytics found in this file"
        return res
    today = ctx.local_date_str()
    now = timeutil.now_iso()
    matcher = _Matcher(ctx)
    for row in parsed.posts:
        platform = row.platform or parsed.platform
        values = {k: v for k, v in row.values.items() if k in FILE_FIELDS}
        if not values or platform not in ("linkedin", "x"):
            continue
        post_id, confidence, nearby = matcher.find(platform, row, parsed)
        if post_id and confidence >= 0.75:
            status, note = "confirmed", None
        elif post_id or nearby:
            status = "needs_review"
            note = "Low-confidence match: please confirm" if post_id else "Couldn't tell which post this is"
        else:
            status, note = "history", None
        mid = ids.stable_id("met", platform, row.key, today)
        old = ctx.store.get("metrics", mid)
        if old and old.get("status") in ("confirmed", "rejected") and old.get("status") != status:
            status, post_id, note = old["status"], old.get("post_id"), old.get("notes")  # his review stands
        ctx.store.upsert("metrics", {
            "id": mid, "post_id": post_id, "platform": platform, "captured_at": now, **values, "source": "file",
            "upload_id": upload["id"], "extraction_confidence": 1.0, "match_confidence": round(confidence, 3),
            "status": status, "notes": note, "created_at": (old or {}).get("created_at") or now,
            "raw": {"url": row.url, "posted_date": row.date, "text_snippet": textutil.truncate(row.text or "", 200)
                    or row.url or "", "file": path.suffix.lower().lstrip(".")},
        })
        res["metrics"] += 1
        res["matched"] += 1 if status == "confirmed" and post_id else 0
        res["needs_review"] += 1 if status == "needs_review" else 0
        res["history"] += 1 if status == "history" else 0
    platform = parsed.platform or "linkedin"
    if parsed.followers:
        day = parsed.followers[0] or today
        old = ctx.store.get("account_stats", f"acs_{platform}_{day}") or {}
        ctx.store.upsert("account_stats", {"id": f"acs_{platform}_{day}", "date": day, "platform": platform,
                                           "followers": parsed.followers[1], "profile_views": old.get("profile_views"),
                                           "source": "file", "created_at": now})
    if parsed.days:
        _merge_days(ctx, platform, parsed.days)
    if parsed.audience:
        audience = ctx.store.get_setting(AUDIENCE_KEY, {}) or {}
        audience[platform] = {"at": today, "rows": parsed.audience[:60]}
        ctx.store.set_setting(AUDIENCE_KEY, audience)
    if parsed.totals:
        totals = ctx.store.get_setting(TOTALS_KEY, {}) or {}
        totals[platform] = {"at": today, "period": parsed.period, **parsed.totals}
        ctx.store.set_setting(TOTALS_KEY, totals)
    if parsed.days or parsed.audience or parsed.totals or parsed.followers:
        res["metrics"] = res["metrics"] or 1  # numbers worth a fresh review even without posts
    return res


def _merge_days(ctx: Ctx, platform: str, days: dict[str, dict[str, int]]) -> None:
    stored = ctx.store.get_setting(DAYS_KEY, {}) or {}
    series = dict(stored.get(platform) or {})
    for day, values in days.items():
        series[day] = {**series.get(day, {}), **values}
    keep = sorted(series)[-KEEP_DAYS:]
    stored[platform] = {d: series[d] for d in keep}
    ctx.store.set_setting(DAYS_KEY, stored)


class _Matcher:
    """Which PBS post an exported row is: by the post's own id in its link, then by its text, then (with only a
    date) by being the one post on that platform that day."""

    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.posts = ctx.store.select("posts", order="posted_at DESC", limit=2000)
        self.by_key = {k: p["id"] for p in self.posts if (k := analytics_files.post_key(p.get("post_url")))}

    def _near(self, platform: str, day: str | None, gap: int) -> list[dict[str, Any]]:
        """PBS's posts on that platform within `gap` days of the date (his local dates, as the exports use)."""
        target = timeutil.parse(day) if day else None
        if target is None:
            return []
        out = []
        for p in self.posts:
            when = timeutil.parse(p.get("posted_at"))
            if p["platform"] == platform and when is not None:
                local = timeutil.local(when, self.ctx.tz).date()
                if abs((local - target.date()).days) <= gap:
                    out.append(p)
        return out

    def find(self, platform: str, row: analytics_files.PostRow,
             parsed: analytics_files.Parsed) -> tuple[str | None, float, bool]:
        """(post id, confidence, whether any PBS post is near enough in time to be it)."""
        key = analytics_files.post_key(row.url)
        if key and key in self.by_key:
            return self.by_key[key], 1.0, True
        # PBS's posts that day that could be this one: not those whose own link names a different post.
        same_day = [p for p in self._near(platform, row.date, 0)
                    if not (key and analytics_files.post_key(p.get("post_url")))]
        nearby = bool(same_day)
        if row.text:
            post_id, conf = match_post(self.ctx, platform, row.text, row.date)
            if post_id and conf >= 0.5 and not (key and analytics_files.post_key(
                    (self.ctx.store.get("posts", post_id) or {}).get("post_url"))):
                return post_id, conf, True
        if len(same_day) == 1:
            others = sum(1 for p in parsed.posts if p.date == row.date and (p.platform or parsed.platform) == platform)
            return same_day[0]["id"], 0.8 if others == 1 else 0.5, True
        return None, 0.0, nearby


def _extract(ctx: Ctx, data: bytes, mime: str, upload: dict[str, Any]) -> dict[str, Any]:
    recent = [{"id": p["id"], "platform": p["platform"], "posted": p["posted_at"][:10],
               "opening": textutil.truncate(p["final_text"], 120)}
              for p in ctx.store.select("posts", order="posted_at DESC", limit=25)]
    prompt = prompting.render("metrics_vision", input_json={"recent_posts": recent, "note": upload.get("note")})
    req = LLMRequest(task="vision", system="You read analytics screenshots exactly. Never guess numbers.",
                     prompt=prompt, images=[(data, mime)], max_output_tokens=2000, personal=True,
                     prompt_version=prompting.version("metrics_vision"))
    out, _ = ctx.llm.call_json(req, _VisionOut)
    platform = out.platform if out.platform in ("linkedin", "x") else None
    n = review = 0
    for pm in out.posts:
        values = {f: getattr(pm, f) for f in FIELDS if getattr(pm, f) is not None}
        if not values:
            continue
        post_id, match_conf = match_post(ctx, platform, pm.text_snippet, pm.posted_date)
        extraction = max(0.0, min(1.0, float(pm.confidence)))
        confident = post_id is not None and match_conf >= 0.75 and extraction >= 0.6
        post = ctx.store.get("posts", post_id) if post_id else None
        ctx.store.insert("metrics", {
            "id": ids.new_id("met"), "post_id": post_id, "platform": (post or {}).get("platform") or platform,
            "captured_at": timeutil.now_iso(), **values, "source": "screenshot", "upload_id": upload["id"],
            "extraction_confidence": round(extraction, 3), "match_confidence": match_conf,
            "status": "confirmed" if confident else "needs_review",
            "raw": pm.model_dump(), "created_at": timeutil.now_iso(),
            "notes": None if confident else ("Couldn't tell which post this is" if not post_id else
                                             "Low-confidence match: please confirm"),
        })
        n += 1
        review += 0 if confident else 1
    if out.account and platform and (out.account.followers is not None or out.account.profile_views is not None):
        date = ctx.local_date_str()
        ctx.store.upsert("account_stats", {"id": f"acs_{platform}_{date}", "date": date, "platform": platform,
                                           "followers": out.account.followers,
                                           "profile_views": out.account.profile_views, "source": "screenshot",
                                           "created_at": timeutil.now_iso()})
    return {"metrics": n, "needs_review": review, "platform": platform}
