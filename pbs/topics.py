"""Group items into topics, attach why-now notes and deterministic pillar fit (FR-4, FR-5 inputs)."""

from __future__ import annotations

import datetime as dt
import math
import re
from collections import Counter, defaultdict
from typing import Any

from . import ids, log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import BudgetExhausted, LLMRequest

MAX_CLUSTER = 14


# ---------------------------------------------------------------------------
# Translation of Hindi items (FR-3)
# ---------------------------------------------------------------------------


def translate_items(ctx: Ctx, items: list[dict[str, Any]], max_items: int = 40) -> int:
    todo = [it for it in items if it.get("lang") == "hi" and not it.get("title_en")][:max_items]
    if not todo:
        return 0
    payload = [{"id": it["id"], "title": it["title"], "summary": textutil.truncate(it.get("summary"), 300)}
               for it in todo]
    req = LLMRequest(task="translate", system="You translate news accurately and neutrally.",
                     prompt=prompting.render("translate", input_json=payload), max_output_tokens=4000,
                     prompt_version=prompting.version("translate"))
    try:
        data, _ = ctx.llm.call_json(req)
    except (BudgetExhausted, ValueError) as exc:
        log.info(f"topics: translation skipped ({type(exc).__name__})")
        return 0
    done = 0
    by_id = {it["id"]: it for it in todo}
    for row in (data or {}).get("items", []):
        item = by_id.get(str(row.get("id")))
        if item and row.get("title_en"):
            item["title_en"] = textutil.normalize_ws(row["title_en"])[:300]
            item["summary_en"] = textutil.truncate(row.get("summary_en") or "", 500)
            ctx.store.update("items", item["id"], title_en=item["title_en"], summary_en=item["summary_en"])
            done += 1
    return done


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def _item_text(it: dict[str, Any]) -> tuple[str, str]:
    title = it.get("title_en") or it.get("title") or ""
    summary = it.get("summary_en") or it.get("summary") or ""
    return title, summary


def _vectors(items: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    docs: dict[str, Counter[str]] = {}
    for it in items:
        title, summary = _item_text(it)
        c: Counter[str] = Counter()
        for tok in textutil.sim_tokens(title):
            c[tok] += 2
        for tok in textutil.sim_tokens(summary)[:60]:
            c[tok] += 1
        docs[it["id"]] = c
    df: Counter[str] = Counter()
    for c in docs.values():
        df.update(c.keys())
    n = max(1, len(docs))
    vecs: dict[str, dict[str, float]] = {}
    for iid, c in docs.items():
        v = {t: (1 + math.log(tf)) * (math.log((n + 1) / (df[t] + 1)) + 1) for t, tf in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs[iid] = {t: x / norm for t, x in v.items()}
    return vecs


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


class _UF:
    def __init__(self, keys: list[str]):
        self.p = {k: k for k in keys}

    def find(self, k: str) -> str:
        while self.p[k] != k:
            self.p[k] = self.p[self.p[k]]
            k = self.p[k]
        return k

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def cluster(items: list[dict[str, Any]], threshold: float) -> list[list[str]]:
    vecs = _vectors(items)
    keys = [it["id"] for it in items]
    uf = _UF(keys)
    inverted: dict[str, list[str]] = defaultdict(list)
    for iid, v in vecs.items():
        for tok in v:
            inverted[tok].append(iid)
    limit = max(15, int(len(keys) * 0.2))
    seen: set[tuple[str, str]] = set()
    for _tok, members in inverted.items():
        if len(members) > limit:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                pair = (a, b) if a < b else (b, a)
                if pair in seen:
                    continue
                seen.add(pair)
                if _cosine(vecs[a], vecs[b]) >= threshold:
                    uf.union(a, b)
    # Items that already belong to the same topic stay together across runs.
    by_topic: dict[str, list[str]] = defaultdict(list)
    for it in items:
        if it.get("topic_id"):
            by_topic[it["topic_id"]].append(it["id"])
    for members in by_topic.values():
        for other in members[1:]:
            uf.union(members[0], other)
    groups: dict[str, list[str]] = defaultdict(list)
    for k in keys:
        groups[uf.find(k)].append(k)
    out: list[list[str]] = []
    for members in groups.values():
        out.extend(_split_large(members, vecs, threshold))
    return out


def _split_large(members: list[str], vecs: dict[str, dict[str, float]], threshold: float) -> list[list[str]]:
    if len(members) <= MAX_CLUSTER or threshold >= 0.85:
        return [members]
    tighter = threshold + 0.12
    uf = _UF(members)
    for i, a in enumerate(members):
        for b in members[i + 1 :]:
            if _cosine(vecs[a], vecs[b]) >= tighter:
                uf.union(a, b)
    groups: dict[str, list[str]] = defaultdict(list)
    for k in members:
        groups[uf.find(k)].append(k)
    out: list[list[str]] = []
    for g in groups.values():
        out.extend(_split_large(g, vecs, tighter))
    return out


# ---------------------------------------------------------------------------
# Why-now notes
# ---------------------------------------------------------------------------


def _ago(hours: float | None) -> str:
    if hours is None:
        return "recently"
    if hours < 1:
        return f"{max(1, int(hours * 60))} min ago"
    if hours < 36:
        return f"{int(round(hours))}h ago"
    return f"{int(round(hours / 24))} days ago"


def why_now(items: list[dict[str, Any]], publishers: list[str]) -> dict[str, Any]:
    now = timeutil.now()
    times = [timeutil.parse(it.get("published_at") or it.get("fetched_at")) for it in items]
    times = [t for t in times if t is not None]
    newest = max(times) if times else None
    oldest = min(times) if times else None
    recent = sum(1 for t in times if (now - t).total_seconds() <= 6 * 3600)
    earlier = sum(1 for t in times if 6 * 3600 < (now - t).total_seconds() <= 24 * 3600)
    pace = "accelerating" if recent >= 2 and recent > 1.5 * max(1, earlier) else ("steady" if recent else "cooling")
    signals: dict[str, Any] = {}
    for it in items:
        for k, v in (it.get("signals") or {}).items():
            if isinstance(v, (int, float)) and k != "hf_rank" and v > (signals.get(k) or 0):
                signals[k] = v
            if k == "hf_rank" and (signals.get(k) is None or v < signals[k]):
                signals[k] = v
            if k == "otd_year":
                signals[k] = v
    also = sorted({p for it in items for p in (it.get("signals") or {}).get("also_seen_in", [])} - set(publishers))
    outlets = len(set(publishers) | set(also))
    parts: list[str] = []
    if outlets >= 2:
        span = timeutil.hours_between(oldest, newest) if oldest and newest else None
        within = f" within {int(span) + 1}h" if span is not None and span < 48 else ""
        parts.append(f"Covered by {outlets} outlets{within}; latest {_ago(timeutil.hours_between(newest, now))}")
    elif publishers:
        parts.append(f"Reported by {publishers[0]} {_ago(timeutil.hours_between(newest, now))}")
    if pace == "accelerating":
        parts.append("coverage is accelerating")
    if signals.get("hn_points"):
        parts.append(f"{int(signals['hn_points'])} points on Hacker News")
    if signals.get("hf_upvotes"):
        rank = signals.get("hf_rank")
        parts.append(f"#{rank} on Hugging Face daily papers ({int(signals['hf_upvotes'])} upvotes)" if rank
                     else f"{int(signals['hf_upvotes'])} upvotes on Hugging Face papers")
    if signals.get("otd_year"):
        parts.append(f"on this day in {signals['otd_year']}")
    if any(it.get("lang") == "hi" for it in items):
        parts.append("includes Hindi-language coverage")
    note = "; ".join(parts)
    note = note[:1].upper() + note[1:] if note else "New today"
    return {
        "note": note + ".",
        "recency_hours": round(timeutil.hours_between(newest, now) or 0.0, 1),
        "n_outlets": outlets,
        "pace": pace,
        "signals": signals,
    }


# ---------------------------------------------------------------------------
# Pillar fit (deterministic)
# ---------------------------------------------------------------------------


def _kw_regex(words: list[str]) -> re.Pattern[str] | None:
    words = [w for w in words if w]
    if not words:
        return None
    return re.compile(r"(?<![\w])(?:" + "|".join(re.escape(w.casefold()) for w in words) + r")(?![\w])")


def pillar_fit(ctx: Ctx, topic_text: str, scout: str | None, hints: set[str]) -> dict[str, dict[str, float]]:
    text = topic_text.casefold()
    out: dict[str, dict[str, float]] = {}
    allowed_li_affairs = _kw_regex(ctx.settings.affairs.linkedin_allowed_topics)
    for platform in ("linkedin", "x"):
        scores: dict[str, float] = {}
        for key, pillar in ctx.settings.pillars(platform).items():
            rx = _kw_regex(pillar.keywords)
            matches = len(set(rx.findall(text))) if rx else 0
            kw = 1 - math.exp(-matches / 2.0)
            score = 0.1 + 0.5 * kw
            if scout and scout in pillar.scouts:
                score += 0.3
            if key in hints:
                score += 0.25
            scores[key] = round(min(1.0, score), 3)
        if platform == "linkedin" and scout == "affairs":
            # Affairs reach LinkedIn only where they meet tech, under the industry pillar.
            meets_tech = bool(allowed_li_affairs and allowed_li_affairs.search(text))
            scores = {k: (v if (meets_tech and k == "industry") else 0.0) for k, v in scores.items()}
        out[platform] = scores
    return out


# ---------------------------------------------------------------------------
# Build topics
# ---------------------------------------------------------------------------


def candidate_items(ctx: Ctx) -> list[dict[str, Any]]:
    sc = ctx.settings.scouting
    now = timeutil.now()
    max_hours = max(sc.lookback_hours.values() or [72])
    since = timeutil.iso(now - dt.timedelta(hours=max_hours))
    rows = ctx.store.select("items", "fetched_at >= ? AND origin = 'scout'", (since,))
    out: list[dict[str, Any]] = []
    per_source: dict[str, int] = defaultdict(int)
    rows.sort(key=lambda r: r.get("published_at") or r.get("fetched_at") or "", reverse=True)
    for r in rows:
        hours = sc.lookback_hours.get(r.get("scout") or "", 72)
        t = timeutil.parse(r.get("published_at") or r.get("fetched_at"))
        if t is None or (now - t).total_seconds() > hours * 3600:
            continue
        if per_source[r["source_id"]] >= sc.per_source_cap:
            continue
        per_source[r["source_id"]] += 1
        out.append(r)
    return out


def build_topics(ctx: Ctx, items: list[dict[str, Any]] | None = None, origin: str = "scout",
                 request_id: str | None = None) -> list[str]:
    store = ctx.store
    items = items if items is not None else candidate_items(ctx)
    if not items:
        return []
    translate_items(ctx, items)
    groups = cluster(items, ctx.settings.scouting.cluster_threshold)
    by_id = {it["id"]: it for it in items}
    sources = {s["id"]: s for s in store.select("sources")}
    touched: list[str] = []
    now = timeutil.now_iso()
    for members in groups:
        its = [by_id[m] for m in members]
        existing_ids = Counter(it["topic_id"] for it in its if it.get("topic_id"))
        topic_id = existing_ids.most_common(1)[0][0] if existing_ids else None
        existing = store.get("topics", topic_id) if topic_id else None
        if existing is None:
            topic_id = ids.new_id("top")
        rep = _representative(its)
        publishers = []
        for it in sorted(its, key=lambda x: x.get("published_at") or ""):
            pub = (it.get("signals") or {}).get("publisher") or sources.get(it["source_id"], {}).get("name")
            if pub and pub not in publishers:
                publishers.append(pub)
        scout = Counter(it.get("scout") for it in its).most_common(1)[0][0]
        tiers = Counter(it.get("tier") for it in its if it.get("tier"))
        tier = _tier_pick(tiers)
        hints: set[str] = set()
        for it in its:
            hints.update(sources.get(it["source_id"], {}).get("pillar_hints") or [])
        title, summary = _item_text(rep)
        text = " ".join([title, summary] + [_item_text(it)[0] for it in its[:8]])
        times = [it.get("published_at") for it in its if it.get("published_at")]
        row = {
            "id": topic_id,
            "origin": origin,
            "request_id": request_id,
            "scout": scout,
            "tier": tier,
            "title": rep.get("title"),
            "title_en": rep.get("title_en"),
            "summary": textutil.truncate(summary, 500),
            "item_ids": sorted(members),
            "source_ids": sorted({it["source_id"] for it in its}),
            "publishers": publishers[:12],
            "n_sources": len(publishers),
            "first_seen_at": (existing or {}).get("first_seen_at") or min(it["fetched_at"] for it in its),
            "last_seen_at": now,
            "newest_published_at": max(times) if times else None,
            "why_now": why_now(its, publishers),
            "fit": pillar_fit(ctx, text, scout, hints),
            "status": (existing or {}).get("status") or "candidate",
            "updated_at": now,
        }
        store.upsert("topics", row)
        for it in its:
            if it.get("topic_id") != topic_id:
                store.update("items", it["id"], topic_id=topic_id)
                it["topic_id"] = topic_id
        touched.append(topic_id)
    log.info(f"topics: {len(items)} items -> {len(touched)} topics")
    return touched


def _tier_pick(tiers: Counter[str | None]) -> str | None:
    if not tiers:
        return None
    for t in ("bihar", "india", "world"):
        if tiers.get(t):
            return t
    return tiers.most_common(1)[0][0]


def _representative(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer English items with a summary from the most-covered wording."""
    if len(items) == 1:
        return items[0]
    vecs = _vectors(items)

    def centrality(it: dict[str, Any]) -> float:
        return sum(_cosine(vecs[it["id"]], vecs[o["id"]]) for o in items if o is not it)

    def score(it: dict[str, Any]) -> float:
        english = 1.0 if (it.get("lang") != "hi" or it.get("title_en")) else 0.6
        has_summary = 1.25 if (it.get("summary_en") or it.get("summary")) else 1.0
        words = len((it.get("title_en") or it.get("title") or "").split())
        descriptive = 0.75 if words < 5 else 1.0
        return (centrality(it) + 0.1) * english * has_summary * descriptive

    return max(items, key=score)


def topic_text(topic: dict[str, Any]) -> str:
    return f"{topic.get('title_en') or topic.get('title') or ''} {topic.get('summary') or ''}"
