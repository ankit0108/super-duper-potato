"""Public social evidence: cited LinkedIn/X posts plus no-key feed observations.

Observed activity, indexed coverage and suggested angles are distinct. Search citations prove only that the
search engine returned a page; they do not prove performance or causality. Public feeds continue without AI.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any
from urllib.parse import quote

from . import log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import AllProvidersFailed, BudgetExhausted, LLMError, LLMRequest, extract_json, json_rows
from .scout.scouting import DedupIndex, ingest_items

SOURCE_ID = "social-pulse"
LAST_KEY = "pulse_last"
HISTORY_KEY = "pulse_history"
STATUS_KEY = "pulse_status"  # the last try: {at, ok, engine, found, error} for the desk
HISTORY_DAYS = 8
PLATFORM_NAME = {"linkedin": "LinkedIn", "x": "X"}
# A link to a post itself (not a profile or a search page).
POST_URL = re.compile(r"^https://(www\.)?(linkedin\.com/(posts|feed/update|pulse)/|(x|twitter)\.com/[^/]+/status/)")


def due(ctx: Ctx) -> bool:
    """Once a day, when it's on, its source isn't paused and a model that searches the web is available today."""
    if not ctx.settings.pulse.enabled or ctx.store.get_setting(LAST_KEY) == ctx.local_date_str():
        return False
    source = _unpaused(ctx)
    # Public feed observations still work when every AI search quota is exhausted.
    return source is None or bool(source.get("active"))


def _unpaused(ctx: Ctx) -> dict[str, Any] | None:
    """The pulse's source, switched back on if the feeds' automatic pause caught it (it isn't a feed: days without
    a web search aren't a broken address). A pause he chose stays."""
    from .scout.scouting import AUTO_PAUSE

    source = ctx.store.get("sources", SOURCE_ID)
    if source is not None and not source.get("active") and str(source.get("paused_reason") or "").startswith(AUTO_PAUSE):
        ctx.store.update("sources", SOURCE_ID, active=True, paused_reason=None, consecutive_failures=0,
                         updated_at=timeutil.now_iso())
        source = ctx.store.get("sources", SOURCE_ID)
    return source


def _status(ctx: Ctx, ok: bool, engine: str | None = None, found: int = 0, error: str | None = None) -> None:
    ctx.store.set_setting(STATUS_KEY, {"at": timeutil.now_iso(), "ok": ok, "engine": engine, "found": found,
                                       "error": error})


def _topics(ctx: Ctx) -> dict[str, list[str]]:
    """His pillars and lanes, as the subjects to search for on each platform."""
    out: dict[str, list[str]] = {}
    for platform in ("linkedin", "x"):
        if ctx.settings.platform_enabled(platform):
            out[PLATFORM_NAME[platform]] = [f"{p.label}: {textutil.truncate(p.description.strip(), 160)}"
                                            for p in ctx.settings.pillars(platform).values()]
    return out


def search_url(platform: str, topic: str) -> str:
    if platform == "linkedin":
        return f"https://www.linkedin.com/search/results/content/?keywords={quote(topic)}&sortBy=%22relevance%22"
    return f"https://x.com/search?q={quote(topic)}&f=top"


def feed_observations(ctx: Ctx) -> list[dict[str, Any]]:
    """Evidence from fetched public feeds. Counts stay on their own platform; no causal claims."""
    since = timeutil.iso(timeutil.now() - dt.timedelta(hours=72))
    rows = ctx.store.select("items", "fetched_at >= ?", (since,))
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item in rows:
        published = timeutil.parse(item.get("published_at"))
        if published is None or not 0 <= (timeutil.now() - published).total_seconds() <= 72 * 3600:
            continue
        sig = item.get("signals") or {}
        platform = sig.get("discovery_platform")
        metrics: dict[str, int] = {}
        url = item["url"]
        if sig.get("hn_points"):
            platform, url = "hackernews", sig.get("hn_url") or url
            metrics = {"points": int(sig["hn_points"]), "comments": int(sig.get("hn_comments") or 0)}
        elif sig.get("mastodon_accounts"):
            platform = "mastodon"
            metrics = {"sharing_accounts": int(sig["mastodon_accounts"])}
        elif platform == "bluesky":
            metrics = {k: int(sig.get(f"bsky_{k}") or 0) for k in ("likes", "replies", "reposts")}
        if platform not in ("linkedin", "x", "bluesky", "mastodon", "hackernews"):
            continue
        observed = bool(metrics) and sum(metrics.values()) > 0
        ranked.append((sum(metrics.values()), {
            "date": published.date().isoformat(), "platform": platform,
            "topic": item.get("title_en") or item["title"],
            "said": textutil.truncate(item.get("summary_en") or item.get("summary") or "", 500),
            "why": "", "angle": "", "url": url,
            "evidence": "observed_activity" if observed else "indexed_coverage",
            "metrics": metrics, "observed_at": item.get("fetched_at"),
            "limitation": ("Public counts are a snapshot, not an engagement rate or proof of why it worked."
                           if observed else "Indexed public coverage; engagement and reach are unknown."),
        }))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["url"]))
    out: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for _, row in ranked:
        p = row["platform"]
        if counts.get(p, 0) < ctx.settings.pulse.per_platform:
            out.append(row)
            counts[p] = counts.get(p, 0) + 1
    return out


def run(ctx: Ctx) -> dict[str, Any]:
    """The day's pulse: conversations stored as items (scout "buzz"). Counts only in the log."""
    today = ctx.local_date_str()
    ctx.store.set_setting(LAST_KEY, today)  # once a day, whether it works or not
    per = ctx.settings.pulse.per_platform
    prompt = prompting.render("pulse", display_name=ctx.settings.display_name, today=today, per_platform=per,
                              input_json=_topics(ctx))
    from .draft import _system

    stats: dict[str, Any] = {"found": 0, "linkedin": 0, "x": 0}
    feed_rows = feed_observations(ctx)
    search_error = None
    resp = None
    try:
        resp = ctx.llm.call(LLMRequest(task="pulse", system=_system(ctx), prompt=prompt, json_mode=False,
                                       grounding=True, max_output_tokens=3000,
                                       prompt_version=prompting.version("pulse")))
        rows = json_rows(extract_json(resp.text), "conversations")
    except (BudgetExhausted, AllProvidersFailed, LLMError, ValueError) as exc:
        log.info(f"pulse: unavailable today ({type(exc).__name__})")
        search_error = ("no_search" if isinstance(exc, BudgetExhausted) else
                        "bad_reply" if isinstance(exc, ValueError) else "failed")
        rows = []
    # Example links only from the pages the search read, when the engine says which (no made-up links).
    read = {textutil.canonical_url(g["url"]) for g in (resp.grounding if resp else []) if g.get("url")}
    now = timeutil.now_iso()
    raws: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    counts = {"linkedin": 0, "x": 0}
    for row in rows:
        platform = str(row.get("platform") or "").lower()
        topic = textutil.normalize_ws(str(row.get("topic") or ""))[:200]
        if platform not in counts or len(topic) < 4 or counts[platform] >= per:
            continue
        said = textutil.normalize_ws(str(row.get("what_people_say") or ""))[:500]
        why = textutil.normalize_ws(str(row.get("why_it_works") or ""))[:300]
        angle = textutil.normalize_ws(str(row.get("angle") or ""))[:300]
        examples = [u for u in row.get("examples") or [] if isinstance(u, str) and POST_URL.match(u)
                    and textutil.canonical_url(u) in read
                    and ("linkedin.com/" in u) == (platform == "linkedin")][:2]
        if not examples:
            continue  # A model's claim, or a search page, is not evidence that a conversation exists.
        counts[platform] += 1
        url = examples[0]
        name = PLATFORM_NAME[platform]
        raws.append({
            "url": url,
            # Each day's conversation is its own story, even when the link is a search.
            "canonical": f"{textutil.canonical_url(url)}#pulse-{today}-{textutil.title_key(topic)[:40]}",
            "title": topic,
            "summary": textutil.truncate(f"Public conversation on {name}: {said} "
                                         f"Possible angle (unverified hypothesis): {why}", 900),
            "published_at": now,
            "lang": "en",
            "publisher": f"{name} (social pulse)",
            "signals": {"discovery_platform": platform, "pulse": 1,
                        **({"discussion_url": examples[0]} if examples else {})},
        })
        history.append({"date": today, "platform": platform, "topic": topic, "said": said, "why": why,
                        "angle": angle, "url": url, "evidence": "search_cited", "metrics": {},
                        "observed_at": now,
                        "limitation": "Search-cited public post; performance is unknown and the angle is a hypothesis."})
    source = ctx.store.get("sources", SOURCE_ID) or {"id": SOURCE_ID, "scout": "buzz"}
    index = DedupIndex(ctx.store, ctx.settings.scouting.dedup_window_days)
    new_ids, _ = ingest_items(ctx.store, source, raws, index)
    since = (timeutil.now() - dt.timedelta(days=HISTORY_DAYS)).date().isoformat()
    kept = [h for h in ctx.store.get_setting(HISTORY_KEY, []) or [] if isinstance(h, dict)
            and (h.get("date") or "") >= since and h.get("date") != today]
    by_url = {h.get("url"): h for h in [*kept, *feed_rows, *history]}
    ctx.store.set_setting(HISTORY_KEY, list(by_url.values())[-100:])
    found = len({h["url"] for h in [*feed_rows, *history]})
    stats.update(found=found, linkedin=counts["linkedin"], x=counts["x"], new_items=len(new_ids),
                 public_feed_observations=len(feed_rows))
    _health(ctx, ok=found > 0, found=len(new_ids), error=search_error if not found else None)
    _status(ctx, ok=found > 0, engine=resp.model if resp and history else "Public feeds" if feed_rows else None,
            found=found, error=search_error if not found else None)
    log.info(f"pulse: {found} evidence-backed observations; {len(feed_rows)} from public feeds")
    return stats


def recent(ctx: Ctx) -> dict[str, Any] | None:
    """The last week's conversations, newest first, and how the last search went, for Insights."""
    since = (timeutil.now() - dt.timedelta(days=HISTORY_DAYS)).date().isoformat()
    rows = [h for h in ctx.store.get_setting(HISTORY_KEY, []) or [] if isinstance(h, dict)
            and (h.get("date") or "") >= since]
    status = ctx.store.get_setting(STATUS_KEY)
    if not rows and not status:
        return None
    rows.sort(key=lambda h: h.get("date") or "", reverse=True)
    source = ctx.store.get("sources", SOURCE_ID) or {}
    return {"updated": rows[0].get("date") if rows else None, "conversations": rows[:40],
            "status": status, "engines": ctx.llm.search_engines(),
            "paused": not source.get("active", True) if source else False}


def _health(ctx: Ctx, ok: bool, found: int, error: str | None = None) -> None:
    source = ctx.store.get("sources", SOURCE_ID)
    if source is None:
        return
    now = timeutil.now_iso()
    patch: dict[str, Any] = {"last_fetch_at": now, "items_last_run": found}
    if ok:
        patch.update(last_success_at=now, consecutive_failures=0, last_error=None,
                     items_total=int(source.get("items_total") or 0) + found)
    else:
        patch.update(consecutive_failures=int(source.get("consecutive_failures") or 0) + 1, last_error=error)
    ctx.store.update("sources", SOURCE_ID, **patch)
