"""Check new and changed seed sources from where the pipeline runs (GitHub's servers), before they ship.

`pbs sources-check --base origin/main` fetches and parses every source in pbs/defaults/sources.yaml that is new or
changed since `base` (plus any named with --also), and resolves the feeds that have to be looked up once: a YouTube
channel's feed from its handle, a podcast's feed from Apple's directory. It prints one line per source: its id, the
URL it fetched, the HTTP status, how many items parsed and the newest item's date. Nothing personal is printed, and
nothing is written: the results are for whoever edits sources.yaml (the sources-check workflow runs it on every pull
request that touches the file).
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from typing import Any

import httpx
import yaml

from .fetch import FetchJob, fetch_all
from .parsers import parse
from .sources import fetch_url, seed_sources

# Feeds resolved once, at build (they have no fixed URL to write down without looking it up).
RESOLVE: list[dict[str, Any]] = [
    {"id": "yt-ai-engineer", "youtube": "@aiDotEngineer"},
    {"id": "yt-karpathy", "youtube": "@AndrejKarpathy"},
    {"id": "yt-ai-explained", "youtube": "@aiexplained-official"},
    {"id": "pod-ai-daily-brief", "apple_id": 1680633614},
    {"id": "pod-seen-and-unseen", "apple_search": "the seen and the unseen", "artist": "Amit Varma"},
    {"id": "pod-no-priors", "apple_search": "No Priors AI", "artist": "Conviction"},
    {"id": "pod-20vc", "apple_search": "The Twenty Minute VC 20VC", "artist": "Harry Stebbings"},
]
UA = "PBS/0.2 (personal research digest; sources check)"


def _base_seeds(base: str) -> dict[str, dict[str, Any]]:
    try:
        text = subprocess.run(["git", "show", f"{base}:pbs/defaults/sources.yaml"], check=True, capture_output=True,
                              text=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for scout, entries in (yaml.safe_load(text) or {}).items():
        for e in entries or []:
            out[e["id"]] = {**e, "scout": scout}
    return out


def changed_sources(base: str | None, also: list[str]) -> list[dict[str, Any]]:
    old = _base_seeds(base) if base else {}
    out = []
    for s in seed_sources():
        before = old.get(s["id"])
        fields = ("kind", "url", "query", "hl", "gl", "ceid")
        if s["id"] in also or before is None or any(before.get(k) != s.get(k) for k in fields):
            out.append(s)
    return out


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        return await client.get(url)
    except httpx.HTTPError:
        return None


async def resolve(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each spec with "url" filled in when found, else "error"."""
    out = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": UA}) as client:
        for spec in specs:
            row = {"id": spec["id"]}
            if spec.get("youtube"):
                resp = await _get(client, f"https://www.youtube.com/{spec['youtube']}")
                m = re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', resp.text) if resp is not None else None
                m = m or (re.search(r"youtube\.com/channel/(UC[\w-]{22})", resp.text) if resp is not None else None)
                if m:
                    row["url"] = f"https://www.youtube.com/feeds/videos.xml?channel_id={m.group(1)}"
                else:
                    row["error"] = f"no channel id (HTTP {resp.status_code if resp is not None else 'error'})"
            else:
                url = (f"https://itunes.apple.com/lookup?id={spec['apple_id']}" if spec.get("apple_id") else
                       "https://itunes.apple.com/search?" + httpx.QueryParams(
                           {"term": spec["apple_search"], "entity": "podcast", "limit": 10}).__str__())
                resp = await _get(client, url)
                results = []
                if resp is not None and resp.status_code == 200:
                    try:
                        results = resp.json().get("results") or []
                    except json.JSONDecodeError:
                        results = []
                artist = (spec.get("artist") or "").casefold()
                pick = next((r for r in results if r.get("feedUrl") and (not artist or artist in
                             (r.get("artistName") or "").casefold())), None)
                pick = pick or next((r for r in results if r.get("feedUrl")), None)
                if pick:
                    row.update(url=pick["feedUrl"], title=pick.get("collectionName"), by=pick.get("artistName"))
                else:
                    row["error"] = f"no feed found (HTTP {resp.status_code if resp is not None else 'error'})"
            out.append(row)
    return out


def probe(sources: list[dict[str, Any]], local_date: str | None = None) -> list[dict[str, Any]]:
    jobs = [FetchJob(key=s["id"], url=url) for s in sources if (url := fetch_url(s, local_date))]
    by_id = {s["id"]: s for s in sources}
    results = asyncio.run(fetch_all(jobs, user_agent=UA, timeout=20, concurrency=8))
    rows = []
    for r in results:
        row: dict[str, Any] = {"id": r.key, "url": r.url, "status": r.status, "error": r.error, "items": 0,
                               "newest": None}
        if r.ok and not r.not_modified:
            try:
                items = parse(by_id[r.key], r.content, local_date)
            except Exception as exc:  # noqa: BLE001 - report whatever the parser tripped on
                row["error"] = f"parse error: {type(exc).__name__}"
                items = []
            row["items"] = len(items)
            dates = sorted(i.get("published_at") or "" for i in items)
            row["newest"] = (dates[-1] or None) if dates else None
            if not items and not row["error"]:
                row["error"] = "no items"
        rows.append(row)
    for s in sources:
        if not fetch_url(s, local_date):
            rows.append({"id": s["id"], "url": None, "status": None, "error": "nothing to fetch (search, not a feed)",
                         "items": 0, "newest": None})
    return rows


def run(base: str | None, also: list[str], resolve_feeds: bool = True) -> int:
    sources = changed_sources(base, also)
    print(f"sources-check: {len(sources)} new or changed sources")
    failed = 0
    for row in sorted(probe(sources), key=lambda r: r["id"]):
        ok = row["items"] > 0
        failed += 0 if ok or row["url"] is None else 1
        print(f"{'OK  ' if ok else 'FAIL'} {row['id']}: {row['items']} items, newest {(row['newest'] or '-')[:10]}, "
              f"HTTP {row['status']}{' (' + row['error'] + ')' if row['error'] else ''} <{row['url']}>")
    if resolve_feeds:
        resolved = asyncio.run(resolve(RESOLVE))
        found = [{**spec, "kind": "rss", "url": r["url"]} for spec, r in zip(RESOLVE, resolved, strict=True) if r.get("url")]
        checks = {row["id"]: row for row in probe(found)} if found else {}
        for r in resolved:
            c = checks.get(r["id"]) or {}
            detail = (f"{c.get('items', 0)} items, newest {(c.get('newest') or '-')[:10]}" if r.get("url")
                      else r.get("error"))
            print(f"RESOLVE {r['id']}: {r.get('url') or '-'} ({detail})"
                  + (f" [{r.get('title')} by {r.get('by')}]" if r.get("title") else ""))
    print(f"sources-check: {failed} failing")
    return 0
