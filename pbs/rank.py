"""Rank topics per platform and fill the day's slots (FR-5, FR-6, FR-7).

pre-score (fit × timeliness × momentum × novelty) → shortlist → LLM triage (angle potential, pillar,
format, sensitivity) → candidates → slot filling with Thompson sampling, reply slots, exploration and
the daily interview cap.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any

import yaml

from . import guardrails, log, prompting, textutil, timeutil
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


def build_memory(ctx: Ctx) -> Memory:
    rk = ctx.settings.ranking
    now = timeutil.now()
    since = timeutil.iso(now - dt.timedelta(days=rk.novelty_window_days))
    block_since = timeutil.iso(now - dt.timedelta(days=rk.resuggest_block_days))
    posted: list[frozenset[str]] = []
    covered: list[frozenset[str]] = []
    off_brand: dict[str, list[frozenset[str]]] = {"linkedin": [], "x": []}
    risky: list[frozenset[str]] = []
    recent: dict[str, set[str]] = {"linkedin": set(), "x": set()}
    for c in ctx.store.select("cards", "created_at >= ?", (since,)):
        toks = frozenset(textutil.sim_tokens(c.get("title")))
        if c["status"] == "posted":
            posted.append(toks)
        reason = (c.get("skip") or {}).get("reason")
        if reason == "already_covered":
            covered.append(toks)
        elif reason == "off_brand":
            off_brand.setdefault(c["platform"], []).append(toks)
        elif reason == "too_risky":
            risky.append(toks)
        if (c.get("created_at") or "") >= block_since and c.get("topic_id"):
            recent.setdefault(c["platform"], set()).add(c["topic_id"])
    return Memory(posted, covered, off_brand, risky, recent)


def _max_overlap(toks: frozenset[str], pool: list[frozenset[str]]) -> float:
    return max((textutil.jaccard(toks, other) for other in pool), default=0.0)


# ---------------------------------------------------------------------------
# Pre-score
# ---------------------------------------------------------------------------


def prescore(ctx: Ctx, topic: dict[str, Any], platform: str, memory: Memory) -> tuple[str, dict[str, float], float] | None:
    fits: dict[str, float] = (topic.get("fit") or {}).get(platform) or {}
    if not fits:
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
    toks = frozenset(textutil.sim_tokens(topic_text(topic)))
    novelty = 1.0 - _max_overlap(toks, memory.posted)
    if _max_overlap(toks, memory.covered) >= 0.4:
        novelty *= 0.1
    if _max_overlap(toks, memory.off_brand.get(platform, [])) >= 0.35:
        novelty *= 0.6
    w = rk.weights
    pre = ((fit ** w.get("fit", 1.0)) * ((0.35 + 0.65 * timeliness) ** w.get("timeliness", 1.0))
           * ((0.55 + 0.45 * momentum) ** w.get("momentum", 0.8)) * (max(0.0, novelty) ** w.get("novelty", 1.0)))
    parts = {"fit": round(fit, 3), "timeliness": round(timeliness, 3), "momentum": round(momentum, 3),
             "novelty": round(novelty, 3)}
    return pillar, parts, round(pre, 4)


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


def triage(ctx: Ctx, topics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """LLM triage of the shortlist. Returns {topic_id: triage}. Empty dict if the model is unavailable."""
    if not topics:
        return {}
    ref = {f"T{i}": t for i, t in enumerate(topics[:24], 1)}
    payload = [{"id": k, "title": t.get("title_en") or t.get("title"), "summary": textutil.truncate(t.get("summary"), 300),
                "scout": t.get("scout"), "tier": t.get("tier"), "why_now": (t.get("why_now") or {}).get("note"),
                "outlets": t.get("n_sources"), "publishers": (t.get("publishers") or [])[:3]}
               for k, t in ref.items()]
    li_keys = "|".join(ctx.settings.pillars("linkedin"))
    x_keys = "|".join(ctx.settings.pillars("x"))
    prompt = prompting.render(
        "triage", display_name=ctx.settings.display_name, linkedin_pillars=_pillar_lines(ctx, "linkedin"),
        x_lanes=_pillar_lines(ctx, "x"), stances=_stance_lines(ctx),
        linkedin_affairs=", ".join(ctx.settings.affairs.linkedin_allowed_topics[:4]),
        linkedin_keys=li_keys, x_keys=x_keys, input_json=payload)
    from .draft import _system

    req = LLMRequest(task="triage", system=_system(ctx), prompt=prompt, max_output_tokens=6000,
                     prompt_version=prompting.version("triage"))
    try:
        data, _ = ctx.llm.call_json(req)
    except (BudgetExhausted, ValueError) as exc:
        log.info(f"rank: triage unavailable ({type(exc).__name__}); using deterministic triage")
        ctx.run.note("Triage used the deterministic fallback (model unavailable)")
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in json_rows(data, "topics"):
        t = ref.get(str(row.get("id")))
        if t is not None:
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
    pre: dict[str, dict[str, tuple[str, dict[str, float], float]]] = {"linkedin": {}, "x": {}}
    for platform in ("linkedin", "x"):
        if not ctx.settings.platform_enabled(platform):
            continue
        scored = []
        for t in topics:
            if t["id"] in memory.recent_topics.get(platform, set()):
                continue
            res = prescore(ctx, t, platform, memory)
            if res:
                scored.append((t, res))
        scored.sort(key=lambda tr: -tr[1][2])
        for t, res in scored[: ctx.settings.scouting.shortlist_per_platform]:
            pre[platform][t["id"]] = res
    shortlist_ids = list(dict.fromkeys([*pre["linkedin"], *pre["x"]]))
    by_id = {t["id"]: t for t in topics}
    tri = triage(ctx, [by_id[i] for i in shortlist_ids]) if use_llm else {}

    out: dict[str, list[Candidate]] = {"linkedin": [], "x": []}
    for platform in ("linkedin", "x"):
        for tid, (det_pillar, parts, base) in pre[platform].items():
            topic = by_id[tid]
            t = tri.get(tid) or {}
            p = t.get(platform) or {}
            key = "pillar" if platform == "linkedin" else "lane"
            if tri and tid in tri:
                pillar = _valid_pillar(ctx, platform, p.get(key) or p.get("pillar") or p.get("lane"))
                if pillar is None:
                    continue
            else:
                pillar = det_pillar
            spec = ctx.settings.pillar(platform, pillar)
            if spec is None:
                continue
            ap = _angle_potential(p.get("angle_potential"))
            det_sensitive, det_reason = guardrails.sensitive_check(topic.get("title_en") or topic.get("title"),
                                                                   topic.get("summary"))
            sensitive = bool(t.get("sensitive")) or det_sensitive
            if not sensitive and _max_overlap(frozenset(textutil.sim_tokens(topic_text(topic))), memory.risky) >= 0.4:
                sensitive, det_reason = True, "similar to a topic you skipped as too risky"
            if platform == "linkedin":
                fmt = "li_text"
            else:
                fmt = p.get("format") if p.get("format") in spec.formats else _default_x_format(
                    ctx, pillar, parts.get("momentum", 0), int(topic.get("n_sources") or 1))
            affairs_type = None
            issue_key = t.get("issue_key") if isinstance(t.get("issue_key"), str) else None
            mode = spec.mode
            kind = "news"
            if pillar == "affairs":
                affairs_type = p.get("affairs_type") if p.get("affairs_type") in ctx.settings.affairs.types else "tracker"
                if (topic.get("why_now") or {}).get("signals", {}).get("otd_year"):
                    affairs_type = "history"
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
            cand = Candidate(
                topic=topic, platform=platform, pillar=pillar, fmt=fmt, mode=mode,
                base=round(base * factor, 4), parts={**parts, "angle_potential": ap}, kind=kind,
                angle=(p.get("angle") or None), affairs_type=affairs_type, issue_key=issue_key,
                sensitive=sensitive, sensitive_reason=t.get("sensitive_reason") or det_reason,
                format_note=p.get("format_note") or None,
            )
            out[platform].append(cand)
        out[platform].extend(bank_candidates(ctx, platform))
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
             rng: random.Random, taken_elsewhere: set[str] | None = None) -> list[Candidate]:
    pconf = getattr(ctx.settings.platforms, platform)
    n = pconf.slots
    cap_interview = pconf.max_interview_per_day
    penalty = ctx.settings.ranking.diversity_arm_penalty
    rate = explore_rate(ctx)
    shares = target_shares(ctx, platform, arms)
    elsewhere = taken_elsewhere or set()
    chosen: list[Candidate] = []
    used_topics: set[str] = set()
    arm_counts: Counter[str] = Counter()
    pillar_counts: Counter[str] = Counter()
    interviews = 0
    experiments = active_experiments(ctx, platform)

    def take(c: Candidate) -> None:
        nonlocal interviews
        chosen.append(c)
        used_topics.add(c.topic_key)
        arm_counts[c.arm] += 1
        pillar_counts[c.pillar] += 1
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
        if pconf.reply_slots and (followers is None or followers < pconf.reply_until_followers):
            max_replies = pconf.reply_slots + 1
            pool = [c for c in cands if c.kind == "news" and not c.sensitive and c.mode == "external"
                    and "x_reply" in (ctx.settings.pillar("x", c.pillar).formats if ctx.settings.pillar("x", c.pillar) else [])]
            pool.sort(key=lambda c: -(c.base * (0.6 + 0.4 * c.parts.get("momentum", 0))))
            for c in pool:
                if len([x for x in chosen if x.fmt == "x_reply"]) >= pconf.reply_slots:
                    break
                if c.topic_key in used_topics:
                    continue
                reply = Candidate(**{**c.__dict__, "fmt": "x_reply"})
                reply.score = reply.base * arms.get(reply.arm, _neutral(reply)).mean
                take(reply)

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
                pool_arms = sorted({c.arm for c in pool},
                                   key=lambda a: (arms.get(a).n_obs if a in arms else 0.0, rng.random()))
                target = pool_arms[0]
                pick = max((c for c in pool if c.arm == target), key=lambda c: c.base)
                pick = Candidate(**{**pick.__dict__, "explore": True})
        if pick is None:
            thetas = {a: (arms[a].sample(rng) if a in arms else rng.betavariate(2, 2)) for a in {c.arm for c in pool}}
            pick = max(pool, key=lambda c: c.base * thetas[c.arm] * (penalty ** arm_counts[c.arm]) * mix(c))
        pick.score = round(pick.base * (arms[pick.arm].mean if pick.arm in arms else 0.5), 4)
        take(pick)

    chosen.sort(key=lambda c: (-c.score, c.topic_key))
    return chosen


def _neutral(c: Candidate) -> ArmState:
    return ArmState(c.arm, c.platform, c.pillar, c.fmt, 2.0, 2.0, 0.5, 0.0)
