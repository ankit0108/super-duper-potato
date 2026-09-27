"""Run the scouts: fetch active sources, parse, dedupe, store items, track source health."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections import defaultdict
from typing import Any

from .. import ids, log, textutil, timeutil
from ..context import Ctx
from ..store import Store
from .fetch import FetchJob, fetch_all
from .parsers import parse
from .sources import fetch_url, sync_seeds

NEAR_DUP_JACCARD = 0.82


class DedupIndex:
    """Recent items indexed by canonical URL, title key and title tokens for near-duplicate checks."""

    def __init__(self, store: Store, window_days: int):
        since = timeutil.iso(timeutil.now() - dt.timedelta(days=window_days))
        self.by_url: dict[str, str] = {}
        self.by_key: dict[str, str] = {}
        self.tokens: dict[str, frozenset[str]] = {}
        self.inverted: dict[str, set[str]] = defaultdict(set)
        for row in store.conn.execute("SELECT id, canonical_url, title_key, title, title_en FROM items "
                                      "WHERE fetched_at >= ?", (since,)):
            self.add(row["id"], row["canonical_url"], row["title_key"], row["title_en"] or row["title"])

    def add(self, item_id: str, canonical: str | None, key: str | None, title: str | None) -> None:
        if canonical:
            self.by_url[canonical] = item_id
        if key:
            self.by_key.setdefault(key, item_id)
        toks = frozenset(textutil.sim_tokens(title))
        self.tokens[item_id] = toks
        for tok in toks:
            self.inverted[tok].add(item_id)

    def find(self, canonical: str, key: str, title: str) -> str | None:
        if canonical and canonical in self.by_url:
            return self.by_url[canonical]
        if key and key in self.by_key:
            return self.by_key[key]
        toks = frozenset(textutil.sim_tokens(title))
        if len(toks) < 4:
            return None
        candidates: dict[str, int] = defaultdict(int)
        for tok in toks:
            for other in self.inverted.get(tok, ()):
                candidates[other] += 1
        for other, shared in sorted(candidates.items(), key=lambda kv: -kv[1])[:30]:
            if shared < 3:
                break
            if textutil.jaccard(toks, self.tokens[other]) >= NEAR_DUP_JACCARD:
                return other
        return None


def ingest_items(store: Store, source: dict[str, Any], raw_items: list[dict[str, Any]], index: DedupIndex,
                 origin: str = "scout", limit: int | None = None) -> tuple[list[str], int]:
    """Insert new items; count duplicates. Duplicates add their publisher to the original's signals."""
    now = timeutil.now_iso()
    new_ids: list[str] = []
    dups = 0
    for raw in raw_items[: limit or len(raw_items)]:
        title = raw.get("title") or ""
        url = raw.get("url") or ""
        if not title or not url:
            continue
        canonical = textutil.canonical_url(url)
        key = textutil.title_key(title)
        existing_id = index.find(canonical, key, title)
        if existing_id:
            dups += 1
            existing = store.get("items", existing_id)
            if existing is not None:
                signals = dict(existing.get("signals") or {})
                changed = False
                for k, v in (raw.get("signals") or {}).items():
                    if isinstance(v, (int, float)) and v > (signals.get(k) or 0):
                        signals[k] = v
                        changed = True
                pub = raw.get("publisher")
                if pub and pub != (existing.get("signals") or {}).get("publisher"):
                    also = set(signals.get("also_seen_in") or [])
                    if pub not in also and len(also) < 12:
                        also.add(pub)
                        signals["also_seen_in"] = sorted(also)
                        changed = True
                if changed:
                    store.update("items", existing_id, signals=signals)
            continue
        item_id = ids.stable_id("itm", canonical or key)
        signals = dict(raw.get("signals") or {})
        if raw.get("publisher"):
            signals["publisher"] = raw["publisher"]
        store.upsert("items", {
            "id": item_id,
            "source_id": source["id"],
            "scout": source.get("scout"),
            "tier": raw.get("tier") or (raw.get("signals") or {}).get("otd_tier") or source.get("tier"),
            "url": url,
            "canonical_url": canonical,
            "title": title,
            "summary": raw.get("summary") or "",
            "lang": raw.get("lang") or "en",
            "published_at": raw.get("published_at"),
            "fetched_at": now,
            "title_key": key,
            "signals": signals,
            "origin": origin,
        })
        index.add(item_id, canonical, key, title)
        new_ids.append(item_id)
    return new_ids, dups


def run_scouts(ctx: Ctx, only: set[str] | None = None) -> dict[str, Any]:
    store, settings = ctx.store, ctx.settings
    added = sync_seeds(store)
    if added:
        log.info(f"scout: added {added} new seed sources")
    sources = [s for s in store.select("sources", "active = 1") if not only or s["scout"] in only]
    local_date = ctx.local_date_str()
    jobs = [FetchJob(key=s["id"], url=fetch_url(s, local_date), etag=s.get("etag"),
                     last_modified=s.get("last_modified")) for s in sources if fetch_url(s, local_date)]
    sc = settings.scouting
    results = asyncio.run(fetch_all(jobs, user_agent=sc.user_agent, timeout=sc.timeout_seconds,
                                    concurrency=sc.concurrency, transport=ctx.transport,
                                    **({"sleep": _nosleep} if ctx.transport is not None else {})))
    index = DedupIndex(store, sc.dedup_window_days)
    by_id = {s["id"]: s for s in sources}
    now = timeutil.now_iso()
    stats = {"sources": len(jobs), "ok": 0, "failed": 0, "not_modified": 0, "new_items": 0, "duplicates": 0}
    for res in results:
        source = by_id[res.key]
        patch: dict[str, Any] = {"last_fetch_at": now}
        if res.ok:
            stats["ok"] += 1
            patch.update(last_success_at=now, consecutive_failures=0, last_error=None)
            if res.etag:
                patch["etag"] = res.etag
            if res.last_modified:
                patch["last_modified"] = res.last_modified
            new_ids: list[str] = []
            if res.not_modified:
                stats["not_modified"] += 1
            else:
                try:
                    raw = parse(source, res.content, local_date)
                except Exception as exc:  # noqa: BLE001 - one bad feed must not stop the scout
                    log.error(f"parse:{source['id']}", exc)
                    raw = []
                    patch["last_error"] = f"parse error: {type(exc).__name__}"
                cap = int(source.get("max_items") or sc.max_items_per_source)
                new_ids, dups = ingest_items(store, source, raw, index, limit=cap)
                stats["duplicates"] += dups
                if not raw and not patch.get("last_error"):
                    patch["last_error"] = "feed returned no items"
            stats["new_items"] += len(new_ids)
            patch["items_last_run"] = len(new_ids)
            patch["items_total"] = int(source.get("items_total") or 0) + len(new_ids)
        else:
            stats["failed"] += 1
            patch.update(consecutive_failures=int(source.get("consecutive_failures") or 0) + 1,
                         last_error=res.error, items_last_run=0)
        store.update("sources", source["id"], **patch)
    _auto_pause(ctx)
    log.info(f"scout: {stats['ok']}/{stats['sources']} sources ok, {stats['new_items']} new items, "
             f"{stats['duplicates']} duplicates, {stats['failed']} failed")
    return stats


async def _nosleep(_seconds: float) -> None:
    return None


def _auto_pause(ctx: Ctx) -> None:
    """Pause sources that have failed for `pause_after_failure_days` (they show on the desk)."""
    days = ctx.settings.scouting.pause_after_failure_days
    cutoff = timeutil.now() - dt.timedelta(days=days)
    for s in ctx.store.select("sources", "active = 1 AND consecutive_failures >= 3"):
        last_ok = timeutil.parse(s.get("last_success_at") or s.get("created_at"))
        if last_ok is not None and last_ok < cutoff:
            ctx.store.update("sources", s["id"], active=False,
                             paused_reason=f"No successful fetch for {days} days ({s.get('last_error') or 'error'})",
                             updated_at=timeutil.now_iso())
            ctx.run.note(f"Paused source {s['id']} after {days} days of failures")


def prune_items(store: Store, retention_days: int) -> int:
    cutoff = timeutil.iso(timeutil.now() - dt.timedelta(days=retention_days))
    return store.delete_where("items", "fetched_at < ?", (cutoff,))
