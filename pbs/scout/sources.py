"""Source registry: seeds from pbs/defaults/sources.yaml merged into the `sources` table."""

from __future__ import annotations

import datetime as dt
import re
from functools import cache
from importlib import resources
from typing import Any
from urllib.parse import quote, urlencode

import yaml

from .. import timeutil
from ..store import Store

SEED_FIELDS = ("name", "kind", "url", "query", "lang", "hl", "gl", "ceid", "scout", "pillar_hints", "tier",
               "best_effort", "max_items")
# Per-kind options kept in a source's `extra`: a Google News topic, a subreddit's score floor, where a trend is.
EXTRA_FIELDS = ("topic", "min_score", "geo", "region", "social_platform")


@cache
def seed_sources() -> list[dict[str, Any]]:
    data = yaml.safe_load(resources.files("pbs.defaults").joinpath("sources.yaml").read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for scout, entries in (data or {}).items():
        for entry in entries or []:
            row = dict(entry)
            row["scout"] = scout
            extra = {k: row.pop(k) for k in EXTRA_FIELDS if row.get(k) is not None}
            if extra:
                row["extra"] = extra
            out.append(row)
    return out


AUTO_PAUSE = "No successful fetch for"  # the start of the reason older releases gave when they paused a source

# The November 2026 source review, from his marks on the source candidates sheet (18 Nov): what he cut, what is dead,
# and the Reddit sources not moved to RSS. Deleted once, the way the Sources page deletes, so they stay gone.
REVIEW_2026_11 = "source_review_2026_11_v1"
REVIEW_2026_11_DELETE = (
    # Cut on the Trim tab
    "gnews-bihar-hi", "theprint", "indian-express-india", "pib-releases", "ht-india", "gnews-india-nation",
    "gnews-patna-hi", "gnews-world", "gnews-bihar-en",
    # Dead or empty (Fixes tab)
    "uber-engineering", "gizmodo", "trends24-india", "trends24-australia", "trends24-world", "livehindustan-bihar",
    "mcp-python-sdk", "bsky-fchollet", "gnews-mistral",
    # Reddit JSON sources not moved to RSS (Reddit refuses GitHub's servers)
    "reddit-technology", "reddit-programming", "reddit-singularity", "reddit-chatgpt", "reddit-openai",
    "reddit-artificial", "reddit-cscareerquestions", "reddit-experienceddevs", "reddit-dataengineering",
)
# Fixed in place in sources.yaml (same id); a row he edited is patched here, since seed refresh leaves those alone.
REVIEW_2026_11_FIX = ("ainews", "gary-marcus", "hbr", "lobsters", "langchain-blog", "reddit-ai-agents",
                      "reddit-llmdevs", "reddit-rpa", "reddit-developersindia", "reddit-programmerhumor",
                      "reddit-linkedinlunatics")


def delete_source(store: Store, source_id: str) -> bool:
    """Remove a source the way the Sources page does: a seed is remembered as deleted, so it isn't added back."""
    row = store.get("sources", source_id)
    if row is None:
        return False
    if row.get("added_by") == "seed":
        deleted = list(store.get_setting("deleted_sources", []) or [])
        if source_id not in deleted:
            deleted.append(source_id)
            store.set_setting("deleted_sources", deleted)
    store.delete("sources", source_id)
    return True


def system_paused(row: dict[str, Any]) -> bool:
    """Paused by the system, not by him: older releases paused failing or unpicked sources and gave a reason; a pause
    from the Sources page has none (or says it was his)."""
    reason = str(row.get("paused_reason") or "")
    return not row.get("active") and bool(reason) and not reason.lower().startswith("paused by")


def _review_2026_11(store: Store, now: str) -> None:
    for sid in REVIEW_2026_11_DELETE:
        delete_source(store, sid)
    seeds = {s["id"]: s for s in seed_sources()}
    for sid in REVIEW_2026_11_FIX:
        row, seed = store.get("sources", sid), seeds.get(sid)
        if not row or not seed:
            continue
        patch: dict[str, Any] = {}
        if (row.get("extra") or {}).get("user_edited"):
            patch = {k: seed.get(k) for k in ("kind", "url", "query") if seed.get(k) != row.get(k)}
        if (row.get("extra") or {}).get("min_score") is not None and seed.get("kind") == "reddit":
            patch["extra"] = {k: v for k, v in (row.get("extra") or {}).items() if k != "min_score"}
        if patch:
            patch.update(etag=None, last_modified=None, consecutive_failures=0, last_error=None, updated_at=now)
            store.update("sources", sid, **patch)
    # Nothing is paused without him now: lift every pause the system made. His own pauses stay.
    for row in store.select("sources", "active = 0"):
        if system_paused(row):
            store.update("sources", row["id"], active=True, paused_reason=None, consecutive_failures=0, updated_at=now)


def sync_seeds(store: Store) -> int:
    """Add new seed sources; never overwrite Ankit's edits or health history. Returns count added."""
    now = timeutil.now_iso()
    if not store.get_setting(REVIEW_2026_11):
        _review_2026_11(store, now)
        store.set_setting(REVIEW_2026_11, True)
    if not store.get_setting("source_yield_recovery_v1"):
        # Old reports confused "not selected" with "bad source" and removed healthy primary coverage.
        # Only undo that exact automatic reason; user pauses and HTTP failure pauses remain intact.
        for source in store.select("sources", "active = 0"):
            if re.fullmatch(r"No picked cards from \d+ items in \d+ weeks", source.get("paused_reason") or ""):
                store.update("sources", source["id"], active=True, paused_reason=None, updated_at=now)
        store.set_setting("source_yield_recovery_v1", True)
    added = 0
    deleted = set(store.get_setting("deleted_sources", []) or [])
    for seed in seed_sources():
        if seed["id"] in deleted:
            continue
        existing = store.get("sources", seed["id"])
        if existing is None:
            row = {k: seed.get(k) for k in SEED_FIELDS if seed.get(k) is not None}
            row.update({
                "id": seed["id"],
                "lang": seed.get("lang", "en"),
                "active": True,
                "best_effort": bool(seed.get("best_effort", False)),
                "added_by": "seed",
                "created_at": now,
                "updated_at": now,
                "consecutive_failures": 0,
                "items_total": 0,
                "extra": seed.get("extra"),
            })
            store.insert("sources", row)
            added += 1
        elif existing.get("added_by") == "seed":  # noqa: SIM102 - keep seed ownership separate from user edits
            # Refresh seed-owned fields (URL fixes ship with code) unless Ankit edited the source.
            if not (existing.get("extra") or {}).get("user_edited"):
                patch = {k: seed.get(k) for k in ("name", "kind", "url", "query", "hl", "gl", "ceid", "pillar_hints",
                                                   "tier", "max_items") if seed.get(k) != existing.get(k)}
                if bool(seed.get("best_effort", False)) != bool(existing.get("best_effort")):
                    patch["best_effort"] = bool(seed.get("best_effort", False))
                old_extra = existing.get("extra") or {}
                if seed.get("extra") and any(old_extra.get(k) != v for k, v in seed["extra"].items()):
                    patch["extra"] = {**old_extra, **seed["extra"]}
                if set(patch) & {"kind", "url", "query", "hl", "gl", "ceid"}:
                    # A new address gets a fresh start: no stale validators, failure count or automatic pause.
                    patch.update(etag=None, last_modified=None, consecutive_failures=0, last_error=None)
                    if not existing.get("active") and str(existing.get("paused_reason") or "").startswith(AUTO_PAUSE):
                        patch.update(active=True, paused_reason=None)
                if patch:
                    patch["updated_at"] = now
                    store.update("sources", seed["id"], **patch)
    return added


def fetch_url(source: dict[str, Any], local_date: str | None = None) -> str:
    """The URL to fetch for a source (Google News queries, arXiv queries and OTD are built here)."""
    kind = source.get("kind")
    if kind == "bsky_search":
        since = timeutil.iso(timeutil.now() - dt.timedelta(hours=72))
        return "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?" + urlencode({
            "q": source.get("query") or "AI", "sort": "top", "limit": 25, "since": since, "lang": "en",
        })
    if kind == "gnews":
        params = {"hl": source.get("hl") or "en-US", "gl": source.get("gl") or "US",
                  "ceid": source.get("ceid") or "US:en"}
        topic = (source.get("extra") or {}).get("topic")
        if topic:
            return f"https://news.google.com/rss/headlines/section/topic/{topic}?{urlencode(params)}"
        return f"https://news.google.com/rss/search?q={quote(source.get('query') or '')}&{urlencode(params)}"
    if kind == "arxiv":
        n = int(source.get("max_items") or 30)
        q = quote(source.get("query") or "cat:cs.AI")
        return (f"https://export.arxiv.org/api/query?search_query={q}&sortBy=submittedDate"
                f"&sortOrder=descending&max_results={n}")
    if kind == "wikipedia_otd":
        day = local_date or timeutil.now().strftime("%Y-%m-%d")
        return f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{day[5:7]}/{day[8:10]}"
    if kind == "wikipedia_pool":
        titles = pool_titles(source.get("query") or "", local_date, int(source.get("max_items") or 3))
        if not titles:
            return ""
        params = {"action": "query", "format": "json", "formatversion": "2", "redirects": "1",
                  "prop": "extracts|info|description", "inprop": "url", "exintro": "1", "explaintext": "1",
                  "exlimit": "20", "titles": "|".join(titles)}
        return f"https://en.wikipedia.org/w/api.php?{urlencode(params)}"
    if kind == "wikiquote_pool":
        pages = quote_pages(local_date, int(source.get("max_items") or 6))
        if not pages:
            return ""
        params = {"action": "query", "format": "json", "formatversion": "2", "redirects": "1",
                  "prop": "revisions|info", "rvprop": "content", "rvslots": "main", "inprop": "url",
                  "titles": "|".join(pages)}
        return f"https://en.wikiquote.org/w/api.php?{urlencode(params)}"
    return source.get("url") or ""


def todays_quotes(local_date: str | None, n: int) -> list[dict[str, Any]]:
    """The day's quotes from the quote pool (pools.quotes), checked against Wikiquote by the parser."""
    from .. import pools

    return pools.todays(pools.quotes(), local_date, n)


def quote_pages(local_date: str | None, n: int) -> list[str]:
    """The Wikiquote pages the day's quotes are checked against, each once."""
    return list(dict.fromkeys(q["page"] for q in todays_quotes(local_date, n)))


@cache
def story_pool(name: str) -> list[str]:
    """A story pool's articles in batch order: one from each theme in turn (pbs/defaults/story_pools.yaml)."""
    data = yaml.safe_load(resources.files("pbs.defaults").joinpath("story_pools.yaml").read_text(encoding="utf-8"))
    themes = [list(t or []) for t in ((data or {}).get(name) or {}).values()]
    out: list[str] = []
    for i in range(max((len(t) for t in themes), default=0)):
        out.extend(t[i] for t in themes if i < len(t) and t[i] not in out)
    return out


def pool_titles(name: str, local_date: str | None, n: int) -> list[str]:
    """The day's batch from a story pool: the next `n` articles, so the whole pool comes round in turn."""
    pool = story_pool(name)
    if not pool or n <= 0:
        return []
    day = dt.date.fromisoformat(local_date) if local_date else timeutil.now().date()
    start = (day.toordinal() * n) % len(pool)
    return [pool[(start + k) % len(pool)] for k in range(min(n, len(pool)))]


def gnews_search_url(query: str, lang: str = "en", region: str = "IN") -> str:
    if lang == "hi":
        params = {"hl": "hi", "gl": "IN", "ceid": "IN:hi"}
    else:
        params = {"hl": f"en-{region}", "gl": region, "ceid": f"{region}:en"}
    return f"https://news.google.com/rss/search?q={quote(query)}&{urlencode(params)}"
