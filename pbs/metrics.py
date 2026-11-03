"""Analytics → numbers matched to posts (FR-20). Low-confidence matches wait for review.

Two kinds of upload: exports (LinkedIn's .xlsx, X's .csv), read exactly by pbs/analytics_files.py with no model
involved, and screenshots, read by the vision model. Exported posts that PBS didn't draft are kept as history:
they count in the performance review (pbs/performance.py) but not in the learner's rewards.
"""

from __future__ import annotations

import difflib
import re
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
WEEK = re.compile(r"^\d{4}-W\d{2}$")
# Bumped when matching improves: exports already uploaded are matched again on the next run (and the review rewritten).
MATCHER_VERSION = 2
MATCHER_KEY = "analytics_matcher_version"
CERTAIN = 0.9  # a match by the post's own link: certain enough to correct an earlier guess
YOURS = 0.85  # a match he confirmed himself: above any guess, below the post's own link


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
        week = upload.get("week") if WEEK.match(upload.get("week") or "") else timeutil.iso_week(ctx.local_date())
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


class _Row:
    """An exported post on its way in: its numbers and what PBS post it is."""

    def __init__(self, row: analytics_files.PostRow, platform: str, values: dict[str, int],
                 match: tuple[str | None, float, list[str]]):
        self.row, self.platform, self.values = row, platform, values
        self.post_id, self.confidence, self.near = match


def _stored_key(m: dict[str, Any]) -> str | None:
    """The export row a stored metric came from (the same key as PostRow.key)."""
    raw = m.get("raw") or {}
    if raw.get("key"):
        return raw["key"]
    url = raw.get("url")
    text = raw.get("text_snippet") if raw.get("text_snippet") != url else None
    return analytics_files.PostRow(None, url, None, raw.get("posted_date"), text).key if (url or text) else None


def _his_decision(old: dict[str, Any] | None) -> str | None:
    """What he decided about an earlier import of this row in the review queue, if he did: "confirmed",
    "history" or "rejected". (Before decisions were marked, a confirmed row below the automatic threshold was his.)"""
    if not old:
        return None
    marked = (old.get("raw") or {}).get("reviewed")
    if marked:
        return str(marked)
    if old.get("status") == "rejected":
        return "rejected"
    if old.get("status") == "confirmed" and old.get("post_id") and (old.get("match_confidence") or 0) < 0.75:
        return "confirmed"
    return None


def rematch_due(ctx: Ctx) -> bool:
    return (ctx.store.get_setting(MATCHER_KEY) or 1) < MATCHER_VERSION


def rematch(ctx: Ctx) -> dict[str, int]:
    """Match the exports already uploaded again with the current matcher, oldest first (his own decisions in the
    review queue stand unless a post's own link says otherwise). Counts only in the log."""
    files = sorted((p for p in (ctx.data_root / "media" / "metrics").glob("*/*")
                    if p.is_file() and p.suffix.lower() in analytics_files.FILE_SUFFIXES),
                   key=lambda p: (p.stat().st_mtime, p.name))
    stats = {"files": 0, "matched": 0, "needs_review": 0}
    for path in files:
        try:
            res = import_file(ctx, path, {"id": "rematch"})
        except Exception as exc:  # noqa: BLE001 - one unreadable file mustn't stop the others
            log.error("metrics:rematch", exc)
            continue
        stats["files"] += 1
        stats["matched"] += res.get("matched", 0)
        stats["needs_review"] += res.get("needs_review", 0)
    ctx.store.set_setting(MATCHER_KEY, MATCHER_VERSION)
    if stats["files"]:
        ctx.hints.add("analysis")
        log.info(f"metrics: matched {stats['files']} uploaded export(s) again: {stats['matched']} matched, "
                 f"{stats['needs_review']} to check")
    return stats


def import_file(ctx: Ctx, path: Any, upload: dict[str, Any]) -> dict[str, Any]:
    """An analytics export: every post's numbers (matched to PBS's posts, or kept as history), the daily series,
    the audience and the follower count. One row per exported post: importing a newer export updates it.

    Matching never gives one PBS post the numbers of two exported posts: the most certain match keeps it. A match
    by the post's own link (its id, or the words LinkedIn puts in it) is certain enough to correct an earlier
    guess, and saves the link on the PBS post so the next export matches it at once."""
    parsed = analytics_files.parse(path)
    res: dict[str, Any] = {"kind": "file", "platform": parsed.platform, "metrics": 0, "needs_review": 0,
                           "matched": 0, "history": 0, "links_saved": 0,
                           **{k: v for k, v in parsed.summary().items() if k in ("days", "audience", "followers")}}
    if parsed.empty:
        res["error"] = "No analytics found in this file"
        return res
    today = ctx.local_date_str()
    now = timeutil.now_iso()
    matcher = _Matcher(ctx)
    rows: list[_Row] = []
    for row in parsed.posts:
        platform = row.platform or parsed.platform
        values = {k: v for k, v in row.values.items() if k in FILE_FIELDS}
        if values and platform in ("linkedin", "x"):
            rows.append(_Row(row, platform, values, matcher.find(platform, row, parsed)))
    existing: dict[str, dict[str, Any]] = {}
    for m in ctx.store.select("metrics", "source = 'file'", order="captured_at"):
        if (k := _stored_key(m)) is not None:
            existing[f"{m.get('platform')}:{k}"] = m
    # His own decisions on earlier imports stand, unless the post's link now says otherwise.
    kept: dict[int, str] = {}
    for i, r in enumerate(rows):
        old = existing.get(f"{r.platform}:{r.row.key}")
        decided = _his_decision(old)
        if decided is None or (r.confidence >= CERTAIN and decided != "rejected"):
            continue
        kept[i] = decided
        r.post_id, r.confidence = (old.get("post_id"), YOURS) if decided == "confirmed" else (None, 0.0)  # type: ignore[union-attr]
    # One exported post per PBS post: the most certain match keeps it, the others look again.
    claimed: dict[str, _Row] = {}
    lost: set[int] = set()
    for i in sorted(range(len(rows)), key=lambda i: -rows[i].confidence):
        r = rows[i]
        if r.post_id and r.post_id in claimed:
            r.post_id, r.confidence = None, 0.0
            if kept.pop(i, None):
                lost.add(i)  # he had said it was that post: he decides again
        elif r.post_id:
            claimed[r.post_id] = r
    for i, r in enumerate(rows):
        old = existing.get(f"{r.platform}:{r.row.key}")
        post_id, confidence = r.post_id, r.confidence
        if i in kept and kept[i] != "confirmed":
            status, note = kept[i], (old or {}).get("notes")
        elif post_id and confidence >= 0.75:
            status, note = "confirmed", None
        elif post_id or any(p not in claimed for p in r.near):
            status = "needs_review"
            note = ("The post you chose has its own row in this export (matched by its link): which post is "
                    "this, or is it one you made without PBS?" if i in lost else
                    "Low-confidence match: please confirm" if post_id else "Couldn't tell which post this is")
        else:
            status, note = "history", None
        mid = old["id"] if old else ids.stable_id("met", r.platform, r.row.key)
        raw = {"url": r.row.url, "posted_date": r.row.date, "key": r.row.key,
               "text_snippet": textutil.truncate(r.row.text or "", 200) or r.row.url or "",
               "file": path.suffix.lower().lstrip(".")}
        if i in kept:
            raw["reviewed"] = kept[i]
        ctx.store.upsert("metrics", {
            "id": mid, "post_id": post_id, "platform": r.platform, "captured_at": now, **r.values, "source": "file",
            "upload_id": upload["id"], "extraction_confidence": 1.0, "match_confidence": round(confidence, 3),
            "status": status, "notes": note, "created_at": (old or {}).get("created_at") or now, "raw": raw,
        })
        if status == "confirmed" and post_id and confidence >= CERTAIN and r.row.url \
                and matcher.save_link(post_id, r.row.url, now):
            res["links_saved"] += 1
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
        audience[platform] = {"at": today, "rows": parsed.audience[:150]}
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
    """Which PBS post an exported row is, most certain first: the post's own id in its link; the words LinkedIn
    puts in the link (the post's hashtags or its opening words), among PBS's posts from around that day; its
    text; and with only a date, being PBS's one post on that platform that day."""

    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.posts = ctx.store.select("posts", order="posted_at DESC", limit=2000)
        self.by_key = {k: p["id"] for p in self.posts if (k := analytics_files.post_key(p.get("post_url")))}
        # PBS posts an earlier export already matched for certain to another exported post.
        self.taken: dict[str, str] = {}
        for m in ctx.store.select("metrics", "source = 'file' AND status = 'confirmed' AND post_id IS NOT NULL",
                                  order="captured_at"):
            if (m.get("match_confidence") or 0) >= CERTAIN and (k := _stored_key(m)):
                self.taken[m["post_id"]] = k

    def _local_day(self, p: dict[str, Any]) -> Any:
        when = timeutil.parse(p.get("posted_at"))
        return timeutil.local(when, self.ctx.tz).date() if when else None

    def _near(self, platform: str, day: str | None, gap: int) -> list[dict[str, Any]]:
        """PBS's posts on that platform within `gap` days of the date (his local dates, as the exports use)."""
        target = timeutil.parse(day) if day else None
        if target is None:
            return []
        return [p for p in self.posts if p["platform"] == platform and (d := self._local_day(p)) is not None
                and abs((d - target.date()).days) <= gap]

    def _free(self, p: dict[str, Any], row: analytics_files.PostRow) -> bool:
        """Could this PBS post be the exported one: not if its own link, or an earlier certain match, says it's
        another post."""
        key = analytics_files.post_key(row.url)
        own = analytics_files.post_key(p.get("post_url"))
        if key and own and own != key:
            return False
        return p["id"] not in self.taken or self.taken[p["id"]] == row.key

    def _by_slug(self, platform: str, row: analytics_files.PostRow) -> tuple[str | None, float]:
        words = analytics_files.slug_words(row.url)
        if len(words) < 2:
            return None, 0.0
        pool = self._near(platform, row.date, 1) if row.date else [p for p in self.posts if p["platform"] == platform]
        scored = sorted(((analytics_files.slug_score(words, p.get("final_text") or "", p.get("hashtags") or []), p)
                         for p in pool if self._free(p, row)), key=lambda t: -t[0])
        if not scored or scored[0][0] < 0.67:
            return None, 0.0
        best, second = scored[0][0], scored[1][0] if len(scored) > 1 else 0.0
        if best - second >= 0.25:
            return scored[0][1]["id"], 0.9
        # The same hashtags on posts a day apart: the one posted that day, if just one was.
        target = timeutil.parse(row.date) if row.date else None
        same = [p for score, p in scored if score == best and target is not None
                and self._local_day(p) == target.date()]
        if len(same) == 1:
            return same[0]["id"], 0.8
        return scored[0][1]["id"], 0.6

    def find(self, platform: str, row: analytics_files.PostRow,
             parsed: analytics_files.Parsed) -> tuple[str | None, float, list[str]]:
        """(post id, confidence, PBS's posts from that day that could be it: if another row takes them all, this
        one is a post made without PBS)."""
        key = analytics_files.post_key(row.url)
        if key and key in self.by_key:
            return self.by_key[key], 1.0, []
        words = analytics_files.slug_words(row.url)
        # A link whose words a post shares none of isn't that post, whatever the date says.
        same_day = [p for p in self._near(platform, row.date, 0) if self._free(p, row) and (
            len(words) < 2 or analytics_files.slug_score(words, p.get("final_text") or "", p.get("hashtags") or [])
            >= 0.34)]
        near = [p["id"] for p in same_day]
        post_id, conf = self._by_slug(platform, row)
        if post_id:
            return post_id, conf, near
        if row.text:
            post_id, conf = match_post(self.ctx, platform, row.text, row.date)
            post = next((p for p in self.posts if p["id"] == post_id), None)
            if post and conf >= 0.5 and self._free(post, row):
                return post_id, conf, near
        if len(same_day) == 1:
            others = sum(1 for p in parsed.posts if p.date == row.date and (p.platform or parsed.platform) == platform)
            return same_day[0]["id"], 0.8 if others == 1 else 0.5, near
        return None, 0.0, near

    def save_link(self, post_id: str, url: str, now: str) -> bool:
        """Keep the post's link from the export when PBS has none for it (the desk links to it, and the next
        export matches it by its id)."""
        post = next((p for p in self.posts if p["id"] == post_id), None)
        if post is None or analytics_files.post_key(post.get("post_url")) or not analytics_files.post_key(url):
            return False
        self.ctx.store.update("posts", post_id, post_url=url, updated_at=now)
        post["post_url"] = url
        self.by_key[analytics_files.post_key(url)] = post_id  # type: ignore[index]
        return True


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
