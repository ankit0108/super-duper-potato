"""The social pulse: what's working on LinkedIn and X.

Neither platform can be read without logging in (and scraping them breaks their terms), so once a day one Gemini
call with Google Search looks for public LinkedIn and X posts on his topics: the conversations taking off, what
people are saying and why posts about them travel. Each one becomes a story for the day's ranking, marked
"Trending on LinkedIn" or "Trending on X", with the why-it-works note in the drafter's material. The last week's
are kept for Insights ("What's working").
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
HISTORY_DAYS = 8
PLATFORM_NAME = {"linkedin": "LinkedIn", "x": "X"}
# A link to a post itself (not a profile or a search page).
POST_URL = re.compile(r"^https://(www\.)?(linkedin\.com/(posts|feed/update|pulse)/|(x|twitter)\.com/[^/]+/status/)")


def due(ctx: Ctx) -> bool:
    """Once a day, when it's on, its source isn't paused and search grounding hasn't said no today."""
    if not ctx.settings.pulse.enabled or ctx.store.get_setting(LAST_KEY) == ctx.local_date_str():
        return False
    source = ctx.store.get("sources", SOURCE_ID)
    if source is not None and not source.get("active"):
        return False
    return not ctx.llm.grounding_off_today()


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


def run(ctx: Ctx) -> dict[str, Any]:
    """The day's pulse: conversations stored as items (scout "buzz"). Counts only in the log."""
    today = ctx.local_date_str()
    ctx.store.set_setting(LAST_KEY, today)  # once a day, whether it works or not
    per = ctx.settings.pulse.per_platform
    prompt = prompting.render("pulse", display_name=ctx.settings.display_name, today=today, per_platform=per,
                              input_json=_topics(ctx))
    from .draft import _system

    stats: dict[str, Any] = {"found": 0, "linkedin": 0, "x": 0}
    try:
        resp = ctx.llm.call(LLMRequest(task="pulse", system=_system(ctx), prompt=prompt, json_mode=False,
                                       grounding=True, max_output_tokens=3000,
                                       prompt_version=prompting.version("pulse")))
        rows = json_rows(extract_json(resp.text), "conversations")
    except (BudgetExhausted, AllProvidersFailed, LLMError, ValueError) as exc:
        log.info(f"pulse: unavailable today ({type(exc).__name__})")
        _health(ctx, ok=False, found=0, error=type(exc).__name__)
        return stats
    now = timeutil.now_iso()
    raws: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    counts = {"linkedin": 0, "x": 0}
    for row in rows:
        platform = str(row.get("platform") or "").lower()
        topic = textutil.normalize_ws(str(row.get("topic") or ""))[:200]
        if platform not in counts or len(topic) < 4 or counts[platform] >= per:
            continue
        counts[platform] += 1
        said = textutil.normalize_ws(str(row.get("what_people_say") or ""))[:500]
        why = textutil.normalize_ws(str(row.get("why_it_works") or ""))[:300]
        angle = textutil.normalize_ws(str(row.get("angle") or ""))[:300]
        examples = [u for u in row.get("examples") or [] if isinstance(u, str) and POST_URL.match(u)][:2]
        url = examples[0] if examples else search_url(platform, topic)
        name = PLATFORM_NAME[platform]
        raws.append({
            "url": url,
            # Each day's conversation is its own story, even when the link is a search.
            "canonical": f"{textutil.canonical_url(url)}#pulse-{today}-{textutil.title_key(topic)[:40]}",
            "title": topic,
            "summary": textutil.truncate(f"What people on {name} are saying: {said} Why posts about it are working: "
                                         f"{why}", 900),
            "published_at": now,
            "lang": "en",
            "publisher": f"{name} (social pulse)",
            "signals": {"trending_on": platform, "why_works": why, "pulse": 1,
                        **({"discussion_url": examples[0]} if examples else {})},
        })
        history.append({"date": today, "platform": platform, "topic": topic, "said": said, "why": why,
                        "angle": angle, "url": url})
    source = ctx.store.get("sources", SOURCE_ID) or {"id": SOURCE_ID, "scout": "buzz"}
    index = DedupIndex(ctx.store, ctx.settings.scouting.dedup_window_days)
    new_ids, _ = ingest_items(ctx.store, source, raws, index)
    since = (timeutil.now() - dt.timedelta(days=HISTORY_DAYS)).date().isoformat()
    kept = [h for h in ctx.store.get_setting(HISTORY_KEY, []) or [] if isinstance(h, dict)
            and (h.get("date") or "") >= since and h.get("date") != today]
    ctx.store.set_setting(HISTORY_KEY, (kept + history)[-80:])
    stats.update(found=len(raws), linkedin=counts["linkedin"], x=counts["x"], new_items=len(new_ids))
    _health(ctx, ok=True, found=len(new_ids))
    log.info(f"pulse: {len(raws)} conversations (linkedin {counts['linkedin']}, x {counts['x']}), "
             f"{len(resp.grounding)} search results")
    return stats


def recent(ctx: Ctx) -> dict[str, Any] | None:
    """The last week's conversations, newest first, for Insights."""
    rows = [h for h in ctx.store.get_setting(HISTORY_KEY, []) or [] if isinstance(h, dict)]
    if not rows:
        return None
    rows.sort(key=lambda h: h.get("date") or "", reverse=True)
    return {"updated": rows[0].get("date"), "conversations": rows[:40]}


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
