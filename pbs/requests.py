"""On-demand requests (FR-14): any topic Ankit adds becomes a fresh search and full drafts."""

from __future__ import annotations

import itertools
from typing import Any

from . import draft, ids, log, textutil, timeutil
from .bandit import arm_id
from .context import Ctx
from .deliver import expiry_for
from .llm.base import BudgetExhausted
from .scout.scouting import DedupIndex
from .scout.search import run_search
from .topics import pillar_fit, why_now

X_FORMAT_CYCLE = ["x_single", "x_thread", "x_reply", "x_quote"]


def _ingest(ctx: Ctx, request: dict[str, Any], found: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[str]:
    """Store search results as items (reusing existing items for URLs we already have)."""
    index = DedupIndex(ctx.store, ctx.settings.scouting.dedup_window_days)
    now = timeutil.now_iso()
    item_ids: list[str] = []
    for src, raw in found:
        canonical = textutil.canonical_url(raw["url"])
        key = textutil.title_key(raw["title"])
        existing = index.find(canonical, key, raw["title"])
        if existing:
            if existing not in item_ids:
                item_ids.append(existing)
            continue
        item_id = ids.stable_id("itm", canonical or key)
        signals = dict(raw.get("signals") or {})
        signals["publisher"] = raw.get("publisher") or src.get("name")
        ctx.store.upsert("items", {
            "id": item_id, "source_id": src["id"], "scout": "request", "url": raw["url"], "canonical_url": canonical,
            "title": raw["title"], "summary": raw.get("summary") or "", "lang": raw.get("lang") or "en",
            "published_at": raw.get("published_at"), "fetched_at": now, "title_key": key, "signals": signals,
            "origin": f"request:{request['id']}",
        })
        index.add(item_id, canonical, key, raw["title"])
        item_ids.append(item_id)
    return item_ids[:12]


def _request_topic(ctx: Ctx, request: dict[str, Any], item_ids: list[str]) -> dict[str, Any]:
    items = [ctx.store.get("items", i) for i in item_ids]
    items = [i for i in items if i]
    publishers = []
    for it in items:
        pub = (it.get("signals") or {}).get("publisher")
        if pub and pub not in publishers:
            publishers.append(pub)
    text = " ".join([request["query"], *(it.get("title") or "" for it in items[:8])])
    wn = why_now(items, publishers) if items else {"note": "You asked for this."}
    wn["note"] = f"You asked for this ({timeutil.local(timeutil.now(), ctx.tz):%a %d %b}). " + wn.get("note", "")
    topic = {
        "id": f"top_req_{request['id']}",
        "origin": "request",
        "request_id": request["id"],
        "scout": "request",
        "title": request["query"],
        "summary": textutil.truncate(" ".join(it.get("summary") or "" for it in items[:3]), 500),
        "item_ids": item_ids,
        "source_ids": sorted({it["source_id"] for it in items}),
        "publishers": publishers[:12],
        "n_sources": len(publishers),
        "first_seen_at": timeutil.now_iso(),
        "last_seen_at": timeutil.now_iso(),
        "why_now": wn,
        "fit": pillar_fit(ctx, text, None, set()),
        "status": "carded",
        "updated_at": timeutil.now_iso(),
    }
    ctx.store.upsert("topics", topic)
    return topic


def _pillar_for(ctx: Ctx, platform: str, topic: dict[str, Any]) -> str:
    fits = (topic.get("fit") or {}).get(platform) or {}
    external = {k: v for k, v in fits.items()
                if (p := ctx.settings.pillar(platform, k)) is not None and p.mode == "external"}
    if external:
        return max(external, key=lambda k: external[k])
    return next(k for k, p in ctx.settings.pillars(platform).items() if p.mode == "external")


def handle_requests(ctx: Ctx, max_requests: int = 2) -> dict[str, int]:
    stats = {"done": 0, "failed": 0}
    queued = ctx.store.select("requests", "status IN ('queued', 'running')", order="created_at")
    for request in queued[:max_requests]:
        attempts = int(request.get("attempts") or 0) + 1
        ctx.store.update("requests", request["id"], status="running", started_at=timeutil.now_iso(), attempts=attempts)
        try:
            found = run_search(ctx, request["query"])
            item_ids = _ingest(ctx, request, found)
            topic = _request_topic(ctx, request, item_ids)
            sources = draft.select_sources(ctx, topic, limit=6)
            card_ids: list[str] = []
            budget_hit = False
            for platform, count in (request.get("platforms") or {}).items():
                if not count or platform not in ("linkedin", "x"):
                    continue
                pillar = _pillar_for(ctx, platform, topic)
                formats = (itertools.cycle(["li_text"]) if platform == "linkedin" else
                           itertools.cycle([f for f in X_FORMAT_CYCLE
                                            if f in ctx.settings.pillar(platform, pillar).formats]))  # type: ignore[union-attr]
                angles: list[str] = []
                for rank in range(1, int(count) + 1):
                    fmt = next(formats)
                    card = _new_request_card(ctx, request, topic, sources, platform, pillar, fmt, rank)
                    card_ids.append(card["id"])
                    if budget_hit:
                        draft.make_brief(ctx, card, "Draft skipped: the free model quota ran out. Tap 'Draft this'.")
                        continue
                    try:
                        card = draft.draft_external(ctx, card, avoid_angles=angles)
                        if card.get("angle"):
                            angles.append(card["angle"])
                    except BudgetExhausted:
                        budget_hit = True
                        ctx.run.degrade("brief_cards")
                        draft.make_brief(ctx, card, "Draft skipped: the free model quota ran out. Tap 'Draft this'.")
            status = "partial" if budget_hit else "done"
            ctx.store.update("requests", request["id"], status=status, completed_at=timeutil.now_iso(),
                             card_ids=card_ids, error=None,
                             search={"results": len(found), "items": len(item_ids)})
            draft.log_interaction(ctx, "request_done", None, request_id=request["id"], cards=len(card_ids))
            stats["done"] += 1
        except Exception as exc:  # noqa: BLE001
            log.error(f"request:{request['id']}", exc)
            ctx.store.update("requests", request["id"], status="failed" if attempts >= 3 else "queued",
                             error=f"{type(exc).__name__} (attempt {attempts})")
            stats["failed"] += 1
    return stats


def _new_request_card(ctx: Ctx, request: dict[str, Any], topic: dict[str, Any], sources: list[dict[str, Any]],
                      platform: str, pillar: str, fmt: str, rank: int) -> dict[str, Any]:
    now = timeutil.now_iso()
    card = {
        "id": ids.new_id("crd"),
        "topic_id": topic["id"],
        "request_id": request["id"],
        "kind": "request",
        "platform": platform,
        "mode": "external",
        "pillar": pillar,
        "format": fmt,
        "title": request["query"],
        "why_now": topic["why_now"]["note"],
        "angle": (request.get("notes") or "").strip() or None,
        "sources": sources,
        "flags": {},
        "status": "drafting",
        "rank": rank,
        "arm": arm_id(platform, pillar, fmt),
        "created_at": now,
        "updated_at": now,
        "delivered_at": now,
        "expires_at": expiry_for(ctx, "request"),
        "revision": 0,
        "draft_state": "pending",
    }
    draft.save_card(ctx, card)
    return card
