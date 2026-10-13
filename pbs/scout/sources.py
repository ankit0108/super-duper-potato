"""Source registry: seeds from pbs/defaults/sources.yaml merged into the `sources` table."""

from __future__ import annotations

import datetime as dt
from functools import cache
from importlib import resources
from typing import Any
from urllib.parse import quote, urlencode

import yaml

from .. import timeutil
from ..store import Store

SEED_FIELDS = ("name", "kind", "url", "query", "lang", "hl", "gl", "ceid", "scout", "pillar_hints", "tier",
               "best_effort", "max_items")


@cache
def seed_sources() -> list[dict[str, Any]]:
    data = yaml.safe_load(resources.files("pbs.defaults").joinpath("sources.yaml").read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for scout, entries in (data or {}).items():
        for entry in entries or []:
            row = dict(entry)
            row["scout"] = scout
            if row.get("topic"):
                row["extra"] = {"topic": row.pop("topic")}
            out.append(row)
    return out


AUTO_PAUSE = "No successful fetch for"  # the start of the reason scouting gives when it pauses a source


def sync_seeds(store: Store) -> int:
    """Add new seed sources; never overwrite Ankit's edits or health history. Returns count added."""
    now = timeutil.now_iso()
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
        elif existing.get("added_by") == "seed":
            # Refresh seed-owned fields (URL fixes ship with code) unless Ankit edited the source.
            if not (existing.get("extra") or {}).get("user_edited"):
                patch = {k: seed.get(k) for k in ("name", "kind", "url", "query", "hl", "gl", "ceid", "pillar_hints",
                                                   "tier", "max_items") if seed.get(k) != existing.get(k)}
                if bool(seed.get("best_effort", False)) != bool(existing.get("best_effort")):
                    patch["best_effort"] = bool(seed.get("best_effort", False))
                if seed.get("extra") and (existing.get("extra") or {}).get("topic") != seed["extra"].get("topic"):
                    patch["extra"] = {**(existing.get("extra") or {}), **seed["extra"]}
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
