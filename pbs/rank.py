"""Rank topics per platform and fill the day's slots (FR-5, FR-6, FR-7).

pre-score (fit × timeliness × momentum × novelty) → shortlist → LLM triage (angle potential, pillar,
format, sensitivity) → candidates → slot filling with Thompson sampling, reply slots, exploration and
the daily interview cap.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any

import yaml

from . import feedback, guardrails, log, pools, posttypes, prompting, textutil, timeutil
from .bandit import ArmState, arm_id
from .context import Ctx
from .llm.base import BudgetExhausted, LLMRequest, json_rows
from .topics import topic_text

ANGLE_POTENTIAL_DEFAULT = 3


@dataclass
class Candidate:
    topic: dict[str, Any]
    platform: str
    pillar: str
    fmt: str
    mode: str
    base: float
    parts: dict[str, float] = field(default_factory=dict)
    kind: str = "news"
    angle: str | None = None
    affairs_type: str | None = None
    post_type: str | None = None
    issue_key: str | None = None
    sensitive: bool = False
    sensitive_reason: str | None = None
    format_note: str | None = None
    bank: dict[str, Any] | None = None
    explore: bool = False
    experiment: dict[str, Any] | None = None
    score: float = 0.0

    @property
    def arm(self) -> str:
        return arm_id(self.platform, self.pillar, self.fmt)

    @property
    def topic_key(self) -> str:
        return self.topic.get("id") or (self.bank or {}).get("id") or ""


# ---------------------------------------------------------------------------
# Memory of what he posted, skipped and saw recently
# ---------------------------------------------------------------------------


@dataclass
class Memory:
    posted: list[frozenset[str]]
    covered: list[frozenset[str]]
    off_brand: dict[str, list[frozenset[str]]]
    risky: list[frozenset[str]]
    recent_topics: dict[str, set[str]]
    dull: list[frozenset[str]] = field(default_factory=list)  # skipped as not interesting
    other: list[frozenset[str]] = field(default_factory=list)  # skipped for another reason (his note says which)


def build_memory(ctx: Ctx) -> Memory:
    rk = ctx.settings.ranking
    now = timeutil.now()
    since = timeutil.iso(now - dt.timedelta(days=rk.novelty_window_days))
    block_since = timeutil.iso(now - dt.timedelta(days=rk.resuggest_block_days))
    posted: list[frozenset[str]] = []
    covered: list[frozenset[str]] = []
    off_brand: dict[str, list[frozenset[str]]] = {"linkedin": [], "x": []}
    risky: list[frozenset[str]] = []
    dull: list[frozenset[str]] = []
    other: list[frozenset[str]] = []
    recent: dict[str, set[str]] = {"linkedin": set(), "x": set()}
    for c in ctx.store.select("cards", "created_at >= ?", (since,)):
        toks = frozenset(textutil.sim_tokens(c.get("title")))
        if c["status"] == "posted":
            posted.append(toks)
        reason = (c.get("skip") or {}).get("reason") if c["status"] == "skipped" else None
        if reason == "already_covered":
            covered.append(toks)
        elif reason == "off_brand":
            off_brand.setdefault(c["platform"], []).append(toks)
        elif reason == "too_risky":
            risky.append(toks)
        elif reason == "not_interesting":
            dull.append(toks)
        elif reason == "other":
            other.append(toks)
        if (c.get("created_at") or "") >= block_since and c.get("topic_id"):
            recent.setdefault(c["platform"], set()).add(c["topic_id"])
    return Memory(posted, covered, off_brand, risky, recent, dull, other)


def _max_overlap(toks: frozenset[str], pool: list[frozenset[str]]) -> float:
    return max((textutil.jaccard(toks, other) for other in pool), default=0.0)


# ---------------------------------------------------------------------------
# Pre-score
# ---------------------------------------------------------------------------


def novelty(toks: frozenset[str], platform: str, memory: Memory) -> float:
    """1.0 for something new; less when it's like what he posted, or skipped as covered, off brand or dull."""
    value = 1.0 - _max_overlap(toks, memory.posted)
    if _max_overlap(toks, memory.covered) >= 0.4:
        value *= 0.1
    if _max_overlap(toks, memory.off_brand.get(platform, [])) >= 0.35:
        value *= 0.6
    if _max_overlap(toks, memory.dull) >= 0.4:
        value *= 0.6
    if _max_overlap(toks, memory.other) >= 0.4:
        value *= 0.8
    return value


def prescore(ctx: Ctx, topic: dict[str, Any], platform: str, memory: Memory) -> tuple[str, dict[str, float], float] | None:
    fits: dict[str, float] = (topic.get("fit") or {}).get(platform) or {}
    if not fits:
        return None
    if platform == "linkedin" and (topic.get("why_now") or {}).get("signals", {}).get("x_only"):
        return None
    interview_keys = {k for k, p in ctx.settings.pillars(platform).items() if p.mode == "interview"}
    external = {k: v for k, v in fits.items() if k not in interview_keys}
    pool = external or fits
    pillar = max(pool, key=lambda k: pool[k])
    fit = pool[pillar]
    if fit < 0.3:
        return None
    rk = ctx.settings.ranking
    newest = timeutil.parse(topic.get("newest_published_at") or topic.get("last_seen_at"))
    age_h = timeutil.hours_between(newest, timeutil.now()) or 0.0
    half = rk.timeliness_half_life_hours.get("research" if pillar == "research" else (topic.get("scout") or ""), 30)
    timeliness = 0.5 ** (max(0.0, age_h) / max(1.0, half))
    why = topic.get("why_now") or {}
    sig = why.get("signals") or {}
    outlets = int(why.get("n_outlets") or topic.get("n_sources") or 1)
    momentum = max(1 - math.exp(-(outlets - 1) / 2.5), min(1.0, (sig.get("hn_points") or 0) / 400),
                   min(1.0, (sig.get("hf_upvotes") or 0) / 120))
    new = novelty(frozenset(textutil.sim_tokens(topic_text(topic))), platform, memory)
    parts, pre = _combine(ctx, fit, timeliness, momentum, new)
    return pillar, parts, pre


def _combine(ctx: Ctx, fit: float, timeliness: float, momentum: float, new: float) -> tuple[dict[str, float], float]:
    w = ctx.settings.ranking.weights
    pre = ((fit ** w.get("fit", 1.0)) * ((0.35 + 0.65 * timeliness) ** w.get("timeliness", 1.0))
           * ((0.55 + 0.45 * momentum) ** w.get("momentum", 0.8)) * (max(0.0, new) ** w.get("novelty", 1.0)))
    parts = {"fit": round(fit, 3), "timeliness": round(timeliness, 3), "momentum": round(momentum, 3),
             "novelty": round(new, 3)}
    return parts, round(pre, 4)


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------


def _pillar_lines(ctx: Ctx, platform: str) -> str:
    return "\n".join(f"- {k}: {p.label} — {p.description.strip()} [{p.mode}]"
                     for k, p in ctx.settings.pillars(platform).items())


def _stance_lines(ctx: Ctx) -> str:
    rows = [s for s in ctx.store.select("stances", "status = 'active'") if s.get("chosen")]
    if not rows:
        return "(none recorded yet)"
    from .draft import stance_text

    return "\n".join(f"- {s['id']}: {stance_text(s)}" for s in rows)


TRIAGE_BATCH = 18  # topics per call: small enough for every provider's input limit
TRIAGE_MAX = 54


def triage(ctx: Ctx, topics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """LLM triage of the shortlist, in batches. Returns {topic_id: triage}; topics a batch couldn't triage are
    left out (they get the deterministic triage). Empty dict if the model is unavailable."""
    out: dict[str, dict[str, Any]] = {}
    # Topics triaged in the last few hours keep that triage: a fresh set asks only about what's new.
    hours = ctx.settings.ranking.triage_reuse_hours
    since = timeutil.iso(timeutil.now() - dt.timedelta(hours=hours))
    fresh = []
    for t in topics:
        cached = t.get("triage") or {}
        if hours > 0 and cached.get("at") and cached["at"] >= since:
            out[t["id"]] = cached
        else:
            fresh.append(t)
    batches = [fresh[i:i + TRIAGE_BATCH] for i in range(0, min(len(fresh), TRIAGE_MAX), TRIAGE_BATCH)]

    def one(n: int, batch: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        try:
            return _triage_batch(ctx, batch)
        except (BudgetExhausted, ValueError) as exc:
            log.info(f"rank: triage batch {n + 1}/{len(batches)} unavailable ({type(exc).__name__}); "
                     "using deterministic triage for it")
            return {}

    if len(batches) > 1 and not os.environ.get("PBS_SERIAL"):
        with ThreadPoolExecutor(max_workers=min(len(batches), ctx.settings.drafting.parallel)) as pool:
            for result in pool.map(lambda nb: one(*nb), enumerate(batches)):
                out.update(result)
    else:
        for n, batch in enumerate(batches):
            out.update(one(n, batch))
    if batches and len(out) == len(topics) - len(fresh):
        ctx.run.note("Triage used the deterministic fallback (model unavailable)")
    return out


def _triage_batch(ctx: Ctx, topics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    ref = {f"T{i}": t for i, t in enumerate(topics, 1)}
    payload = [{"id": k, "title": t.get("title_en") or t.get("title"), "summary": textutil.truncate(t.get("summary"), 300),
                "scout": t.get("scout"), "tier": t.get("tier"), "why_now": (t.get("why_now") or {}).get("note"),
                "outlets": t.get("n_sources"), "publishers": (t.get("publishers") or [])[:3]}
               for k, t in ref.items()]
    li_keys = "|".join(ctx.settings.pillars("linkedin"))
    x_keys = "|".join(ctx.settings.pillars("x"))
    prompt = prompting.render(
        "triage", display_name=ctx.settings.display_name, linkedin_pillars=_pillar_lines(ctx, "linkedin"),
        x_lanes=_pillar_lines(ctx, "x"), stances=_stance_lines(ctx),
        feedback=feedback.render(feedback.recent_feedback(ctx, notes_first=True)),
        linkedin_affairs=", ".join(ctx.settings.affairs.linkedin_allowed_topics[:4]),
        linkedin_keys=li_keys, x_keys=x_keys, input_json=payload)
    from .draft import _system

    req = LLMRequest(task="triage", system=_system(ctx), prompt=prompt, max_output_tokens=6000,
                     prompt_version=prompting.version("triage"))
    data, _ = ctx.llm.call_json(req)
    out: dict[str, dict[str, Any]] = {}
    at = timeutil.now_iso()
    for row in json_rows(data, "topics"):
        t = ref.get(str(row.get("id")))
        if t is not None:
            row = {**row, "at": at}
            out[t["id"]] = row
            ctx.store.update("topics", t["id"], triage=row)
    return out


def _valid_pillar(ctx: Ctx, platform: str, value: Any) -> str | None:
    if isinstance(value, str) and value in ctx.settings.pillars(platform):
        return value
    return None


def _angle_potential(value: Any) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return ANGLE_POTENTIAL_DEFAULT


def _default_x_format(ctx: Ctx, pillar: str, momentum: float, outlets: int) -> str:
    formats = ctx.settings.pillar("x", pillar).formats  # type: ignore[union-attr]
    if momentum >= 0.6 and "x_reply" in formats:
        return "x_reply"
    if outlets >= 3 and "x_thread" in formats:
        return "x_thread"
    return "x_single" if "x_single" in formats else formats[0]


def _stance_ready(ctx: Ctx, issue_key: str | None) -> bool:
    if not issue_key:
        return False
    stance = ctx.store.get("stances", issue_key)
    return bool(stance and stance.get("chosen") and stance.get("status") != "archived")


def build_candidates(ctx: Ctx, topics: list[dict[str, Any]], memory: Memory,
                     use_llm: bool = True) -> dict[str, list[Candidate]]:
    # Quotes (a quote pool's, checked on Wikiquote) aren't news: they skip triage and go to the quote lane.
    quotes = [t for t in topics if _signals(t).get("quote")]
    news = [t for t in topics if not _signals(t).get("quote")]
    pre: dict[str, dict[str, tuple[str, dict[str, float], float]]] = {"linkedin": {}, "x": {}}
    for platform in ("linkedin", "x"):
        if not ctx.settings.platform_enabled(platform):
            continue
        scored = []
        for t in news:
            if t["id"] in memory.recent_topics.get(platform, set()):
                continue
            res = prescore(ctx, t, platform, memory)
            if res:
                scored.append((t, res))
        scored.sort(key=lambda tr: -tr[1][2])
        for t, res in scored[: ctx.settings.scouting.shortlist_per_platform]:
            pre[platform][t["id"]] = res
    shortlist_ids = list(dict.fromkeys([*pre["linkedin"], *pre["x"]]))
    by_id = {t["id"]: t for t in news}
    tri = triage(ctx, [by_id[i] for i in shortlist_ids]) if use_llm else {}

    out: dict[str, list[Candidate]] = {"linkedin": [], "x": []}
    for platform in ("linkedin", "x"):
        if not ctx.settings.platform_enabled(platform):
            continue
        for tid, (det_pillar, parts, base) in pre[platform].items():
            cand = _news_candidate(ctx, platform, by_id[tid], tri.get(tid), bool(tri), det_pillar, parts, base,
                                   memory)
            if cand is not None:
                out[platform].append(cand)
        out[platform].extend(quote_candidates(ctx, platform, quotes, memory))
        out[platform].extend(pool_candidates(ctx, platform, memory))
        out[platform].extend(bank_candidates(ctx, platform))
    return out


def _signals(topic: dict[str, Any]) -> dict[str, Any]:
    return (topic.get("why_now") or {}).get("signals") or {}


def _news_candidate(ctx: Ctx, platform: str, topic: dict[str, Any], t: dict[str, Any] | None, triaged: bool,
                    det_pillar: str, parts: dict[str, float], base: float, memory: Memory) -> Candidate | None:
    t = t or {}
    p = t.get(platform) or {}
    key = "pillar" if platform == "linkedin" else "lane"
    if triaged and t:
        pillar = _valid_pillar(ctx, platform, p.get(key) or p.get("pillar") or p.get("lane"))
        if pillar is None:
            return None
    else:
        pillar = det_pillar
    if ctx.settings.pillar(platform, pillar) is None:
        return None
    ap = _angle_potential(p.get("angle_potential"))
    det_sensitive, det_reason = guardrails.sensitive_check(topic.get("title_en") or topic.get("title"),
                                                           topic.get("summary"))
    sensitive = bool(t.get("sensitive")) or det_sensitive
    if not sensitive and _max_overlap(frozenset(textutil.sim_tokens(topic_text(topic))), memory.risky) >= 0.4:
        sensitive, det_reason = True, "similar to a topic you skipped as too risky"
    spec = ctx.settings.pillar(platform, pillar)
    post_type = posttypes.for_news(spec.post_types, p.get("post_type"))  # type: ignore[union-attr]
    if sensitive and post_type in posttypes.HUMOROUS:
        # Never a joke about a tragedy, violence or a communal incident: the topic's best serious pillar instead.
        fits = (topic.get("fit") or {}).get(platform) or {}
        serious = {k: v for k, v in fits.items() if v >= 0.3 and (ps := ctx.settings.pillar(platform, k))
                   and ps.mode == "external" and not set(ps.post_types) & posttypes.HUMOROUS}
        if not serious:
            return None
        pillar = max(serious, key=lambda k: serious[k])
        spec = ctx.settings.pillar(platform, pillar)
        post_type = posttypes.for_news(spec.post_types, None)  # type: ignore[union-attr]
    assert spec is not None
    if platform == "linkedin":
        fmt = "li_text"
    elif p.get("format") in spec.formats and post_type != "thought":
        fmt = p["format"]
    else:
        fmt = _default_x_format(ctx, pillar, parts.get("momentum", 0), int(topic.get("n_sources") or 1))
        if post_type == "thought" and "x_single" in spec.formats:
            fmt = "x_single"
    affairs_type = None
    issue_key = t.get("issue_key") if isinstance(t.get("issue_key"), str) else None
    mode = spec.mode
    kind = "news"
    signals = _signals(topic)
    # A story (a story pool's article, or on this day) has no announcement to reply to or post to quote.
    if (signals.get("evergreen") or signals.get("otd_year")) and fmt in ("x_reply", "x_quote"):
        fmt = "x_thread" if "x_thread" in spec.formats else spec.formats[0]
    if signals.get("evergreen"):
        kind = "evergreen"  # it keeps for days
    if pillar == "affairs":
        affairs_type = p.get("affairs_type") if p.get("affairs_type") in ctx.settings.affairs.types else "tracker"
        if signals.get("otd_year") or signals.get("evergreen"):
            affairs_type = "story" if "story" in ctx.settings.affairs.types else "history"
        if affairs_type == "opinion" and not _stance_ready(ctx, issue_key):
            # Questions first, draft second — or a non-opinion type if the interview cap is used.
            mode, kind = "interview", "interview"
    if sensitive:
        if affairs_type == "opinion":
            affairs_type, mode, kind = "tracker", "external", "news"
        if fmt in ("x_reply", "x_quote"):
            fmt = "x_single" if "x_single" in spec.formats else fmt
        if mode == "interview" and spec.mode != "interview":
            mode, kind = "external", "news"
    if mode == "interview":
        kind = "interview"
    factor = 0.55 + 0.15 * ap
    return Candidate(
        topic=topic, platform=platform, pillar=pillar, fmt=fmt, mode=mode,
        base=round(base * factor, 4), parts={**parts, "angle_potential": ap}, kind=kind,
        angle=(p.get("angle") or None), affairs_type=affairs_type, post_type=post_type, issue_key=issue_key,
        sensitive=sensitive, sensitive_reason=t.get("sensitive_reason") or det_reason,
        format_note=p.get("format_note") or None,
    )


# ---------------------------------------------------------------------------
# Material that isn't news: quotes, funny premises and themes for a thought (pools.py)
# ---------------------------------------------------------------------------

POOL_FIT = 0.7  # what a pool entry starts from, next to a news topic's fit; the learner moves its lane from there


def _pool_candidate(ctx: Ctx, platform: str, topic: dict[str, Any], post_type: str, memory: Memory) -> Candidate | None:
    pillar = posttypes.pillar_for(ctx.settings, platform, post_type)
    spec = ctx.settings.pillar(platform, pillar or "")
    if spec is None or spec.mode != "external" or topic["id"] in memory.recent_topics.get(platform, set()):
        return None
    new = novelty(frozenset(textutil.sim_tokens(topic_text(topic))), platform, memory)
    parts, base = _combine(ctx, POOL_FIT, 1.0, 0.0, new)
    fmt = "li_text" if platform == "linkedin" else ("x_single" if "x_single" in spec.formats else spec.formats[0])
    # Kind "news": it goes when the next morning's set comes, which brings new ones (the pool comes round again).
    return Candidate(topic=topic, platform=platform, pillar=pillar or "", fmt=fmt, mode="external", base=base,
                     parts={**parts, "pool": 1.0}, kind="news", angle=posttypes.POOL_ANGLE.get(post_type),
                     post_type=post_type)


def quote_candidates(ctx: Ctx, platform: str, topics: list[dict[str, Any]], memory: Memory) -> list[Candidate]:
    """The day's verified quotes (topics from a wikiquote_pool source), for the lane that makes quote posts."""
    if platform == "linkedin":
        return []
    return [c for t in topics if (c := _pool_candidate(ctx, platform, t, "quote", memory)) is not None]


def pool_candidates(ctx: Ctx, platform: str, memory: Memory) -> list[Candidate]:
    """Today's funny premises and themes for a thought, each as a candidate in the lane that makes that kind of
    post. A premise or theme carded in the last month is passed over for the next one."""
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=30))
    used = {r[0] for r in ctx.store.conn.execute(
        "SELECT topic_id FROM cards WHERE topic_id LIKE 'pool:%' AND created_at >= ?", (since,)) if r[0]}
    day = ctx.local_date_str()
    out: list[Candidate] = []
    for entries, n, post_type, note in (
            (pools.humor(), ctx.settings.pools.humor, "observation", "A premise for a funny post; not news."),
            (pools.thoughts(), ctx.settings.pools.thoughts, "thought", "A theme for a thought of your own; not news.")):
        here = [e for e in entries if platform in e["platforms"]]
        for e in pools.todays(here, day, n, skip=used):
            topic = {"id": e["id"], "title": e["text"], "summary": "", "item_ids": [], "why_now": {"note": note}}
            cand = _pool_candidate(ctx, platform, topic, post_type, memory)
            if cand is not None:
                out.append(cand)
    return out


# ---------------------------------------------------------------------------
# Interview bank
# ---------------------------------------------------------------------------


@cache
def interview_bank() -> list[dict[str, Any]]:
    text = resources.files("pbs.defaults").joinpath("interview_bank.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text) or []


def bank_candidates(ctx: Ctx, platform: str, per_pillar: int = 1) -> list[Candidate]:
    used_since = timeutil.iso(timeutil.now() - dt.timedelta(days=60))
    used = {r[0] for r in ctx.store.conn.execute(
        "SELECT topic_id FROM cards WHERE kind = 'interview' AND created_at >= ?", (used_since,)) if r[0]}
    out: list[Candidate] = []
    counts: Counter[str] = Counter()
    for entry in interview_bank():
        if entry.get("platform") != platform or f"bank:{entry['id']}" in used:
            continue
        spec = ctx.settings.pillar(platform, entry["pillar"])
        if spec is None or counts[entry["pillar"]] >= per_pillar:
            continue
        counts[entry["pillar"]] += 1
        fmt = spec.formats[0]
        topic = {"id": f"bank:{entry['id']}", "title": entry["title"], "summary": entry.get("angle", ""),
                 "why_now": {"note": "Evergreen: from your interview bank."}, "item_ids": []}
        out.append(Candidate(topic=topic, platform=platform, pillar=entry["pillar"], fmt=fmt, mode="interview",
                             base=0.22, parts={"bank": 1.0}, kind="interview", angle=entry.get("angle"),
                             bank=entry))
    return out


# ---------------------------------------------------------------------------
# Slot allocation
# ---------------------------------------------------------------------------


def explore_rate(ctx: Ctx) -> float:
    lp = ctx.settings.learning
    first = ctx.store.scalar("SELECT MIN(delivered_at) FROM deliveries")
    if first is None:
        return lp.explore_rate_cold_start
    age_days = (timeutil.now() - timeutil.parse(first)).total_seconds() / 86400  # type: ignore[operator]
    return lp.explore_rate_cold_start if age_days < lp.cold_start_days else lp.explore_rate


def x_followers(ctx: Ctx) -> int | None:
    row = ctx.store.select("account_stats", "platform = 'x' AND followers IS NOT NULL", order="date DESC", limit=1)
    return int(row[0]["followers"]) if row else None


def active_experiments(ctx: Ctx, platform: str) -> list[dict[str, Any]]:
    return [e for e in ctx.store.select("experiments", "status = 'active'")
            if e.get("platform") in (None, platform)]


def target_shares(ctx: Ctx, platform: str, arms: dict[str, ArmState]) -> dict[str, float]:
    """Starting weights moved by evidence: weight × (pillar posterior mean / pillar prior mean)."""
    weights = ctx.settings.normalized_weights(platform)
    raw: dict[str, float] = {}
    for pillar, w in weights.items():
        own = [a for a in arms.values() if a.platform == platform and a.pillar == pillar]
        if not own:
            raw[pillar] = w
            continue
        alpha = sum(a.alpha for a in own)
        beta = sum(a.beta for a in own)
        prior = sum(a.prior_mean for a in own) / len(own)
        raw[pillar] = w * ((alpha / (alpha + beta)) / max(prior, 1e-3))
    total = sum(raw.values()) or 1.0
    return {k: v / total for k, v in raw.items()}


def allocate(ctx: Ctx, platform: str, cands: list[Candidate], arms: dict[str, ArmState],
             rng: random.Random, taken_elsewhere: set[str] | None = None, slots: int | None = None) -> list[Candidate]:
    pconf = getattr(ctx.settings.platforms, platform)
    n = slots or pconf.slots
    reply_slots = getattr(pconf, "reply_slots", 0)  # X only
    if slots:
        reply_slots = min(reply_slots, n // 2)  # a small fresh set stays mostly posts, not replies
    cap_interview = pconf.max_interview_per_day
    penalty = ctx.settings.ranking.diversity_arm_penalty
    rate = explore_rate(ctx)
    shares = target_shares(ctx, platform, arms)
    elsewhere = taken_elsewhere or set()
    chosen: list[Candidate] = []
    used_topics: set[str] = set()
    arm_counts: Counter[str] = Counter()
    pillar_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()  # post types (posttypes.py): a set mixes a quote and a thought
    interviews = 0
    experiments = active_experiments(ctx, platform)

    def take(c: Candidate) -> None:
        nonlocal interviews
        chosen.append(c)
        used_topics.add(c.topic_key)
        arm_counts[c.arm] += 1
        pillar_counts[c.pillar] += 1
        if c.post_type:
            type_counts[c.post_type] += 1
        if c.mode == "interview":
            interviews += 1

    def mix(c: Candidate) -> float:
        expected = shares.get(c.pillar, 0.0) * n
        after = pillar_counts[c.pillar] + 1
        factor = 1.0 if after <= expected + 0.6 else 0.4 ** (after - expected)
        return factor * (0.85 if c.topic_key in elsewhere else 1.0)

    # Reply angles on the day's biggest announcements while the X account is small.
    max_replies = n
    if platform == "x":
        followers = x_followers(ctx)
        if reply_slots and (followers is None or followers < pconf.reply_until_followers):
            max_replies = reply_slots + 1
            pool = [c for c in cands if c.kind == "news" and not c.sensitive and c.mode == "external"
                    and c.affairs_type != "story" and "x_reply" in (ctx.settings.pillar("x", c.pillar).formats if ctx.settings.pillar("x", c.pillar) else [])]
            pool.sort(key=lambda c: -(c.base * (0.6 + 0.4 * c.parts.get("momentum", 0))))
            for c in pool:
                if len([x for x in chosen if x.fmt == "x_reply"]) >= reply_slots:
                    break
                if c.topic_key in used_topics:
                    continue
                reply = Candidate(**{**c.__dict__, "fmt": "x_reply"})
                reply.score = reply.base * arms.get(reply.arm, _neutral(reply)).mean
                take(reply)

    def reserve(pool: list[Candidate], count: int) -> None:
        """Take the best `count` of a pool before the open slots are filled."""
        for c in sorted(pool, key=lambda c: (-c.base * (arms[c.arm].mean if c.arm in arms else 0.5), c.topic_key)):
            if count <= 0 or len(chosen) >= n:
                break
            if c.topic_key in used_topics or (c.mode == "interview" and interviews >= cap_interview):
                continue
            c.score = round(c.base * (arms[c.arm].mean if c.arm in arms else 0.5), 4)
            take(c)
            count -= 1

    # The day's evergreen story (Bihar, history to now), when a full set has room for one.
    if platform == "x" and n >= 4:
        reserve([c for c in cands if c.affairs_type == "story" and c.mode == "external"],
                ctx.settings.affairs.stories_per_day)
    # Slots a pillar keeps every morning (LinkedIn's tech humour: one funny post a day).
    if slots is None and n >= 3:
        for key, spec in ctx.settings.pillars(platform).items():
            if spec.min_per_day > pillar_counts[key]:
                reserve([c for c in cands if c.pillar == key], spec.min_per_day - pillar_counts[key])

    while len(chosen) < n:
        replies = sum(1 for c in chosen if c.fmt == "x_reply")
        pool = [c for c in cands if c.topic_key not in used_topics
                and (c.mode != "interview" or interviews < cap_interview)
                and (c.fmt != "x_reply" or replies < max_replies)]
        if not pool:
            break
        explore = rng.random() < rate
        pick: Candidate | None = None
        if explore:
            exp = next((e for e in experiments if any(c.pillar == e.get("pillar") or e.get("pillar") is None
                                                      for c in pool)), None)
            if exp:
                sub = [c for c in pool if exp.get("pillar") in (None, c.pillar) and c.kind == "news"] or pool
                pick = max(sub, key=lambda c: c.base)
                pick = Candidate(**{**pick.__dict__, "explore": True, "experiment": exp})
                experiments.remove(exp)
            else:
                # sorted() first: set order varies between processes, and it decides which draw goes where.
                pool_arms = sorted(sorted({c.arm for c in pool}),
                                   key=lambda a: (arms.get(a).n_obs if a in arms else 0.0, rng.random()))
                target = pool_arms[0]
                pick = max((c for c in pool if c.arm == target), key=lambda c: c.base)
                pick = Candidate(**{**pick.__dict__, "explore": True})
        if pick is None:
            thetas = {a: (arms[a].sample(rng) if a in arms else rng.betavariate(2, 2)) for a in sorted({c.arm for c in pool})}
            pick = max(pool, key=lambda c: c.base * thetas[c.arm] * (penalty ** arm_counts[c.arm]) * mix(c)
                       * (penalty ** type_counts[c.post_type] if c.post_type else 1.0))
        pick.score = round(pick.base * (arms[pick.arm].mean if pick.arm in arms else 0.5), 4)
        take(pick)

    chosen.sort(key=lambda c: (-c.score, c.topic_key))
    return chosen


def _neutral(c: Candidate) -> ArmState:
    return ArmState(c.arm, c.platform, c.pillar, c.fmt, 2.0, 2.0, 0.5, 0.0)
