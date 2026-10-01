"""The morning delivery (FR-7) and the Saturday batch (FR-17). Both are idempotent per local date/week."""

from __future__ import annotations

import datetime as dt
import random
from typing import Any

from . import bandit, draft, ids, log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import BudgetExhausted, LLMRequest, json_rows, why_unavailable
from .rank import Candidate, allocate, build_candidates, build_memory, interview_bank
from .scout.scouting import run_scouts
from .topics import build_topics


def delivery_id(local_date: str) -> str:
    return f"dly_{local_date}"


def next_delivery_at(ctx: Ctx, after_local_date: dt.date) -> dt.datetime:
    nxt = after_local_date + dt.timedelta(days=1)
    return timeutil.at_local_time(nxt, ctx.settings.delivery.earliest_local_time, ctx.tz)


def delivery_due(ctx: Ctx) -> bool:
    local = ctx.local_now()
    d = ctx.settings.delivery
    if ctx.store.get("deliveries", delivery_id(local.date().isoformat())):
        return False
    hhmm = local.strftime("%H:%M")
    return d.earliest_local_time <= hhmm <= d.latest_local_time


def expiry_for(ctx: Ctx, kind: str) -> str:
    now = timeutil.now()
    e = ctx.settings.expiry
    if kind == "news":
        return timeutil.iso(next_delivery_at(ctx, ctx.local_date()))  # type: ignore[return-value]
    days = {"interview": e.interview_days, "evergreen": e.evergreen_days, "request": e.request_days}.get(kind, 1)
    return timeutil.iso(now + dt.timedelta(days=days))  # type: ignore[return-value]


def card_from_candidate(ctx: Ctx, cand: Candidate, dlv_id: str | None, rank: int, kind: str | None = None) -> dict[str, Any]:
    now = timeutil.now_iso()
    topic = cand.topic
    kind = kind or cand.kind
    sources = draft.select_sources(ctx, topic) if topic.get("item_ids") else []
    card = {
        "id": ids.new_id("crd"),
        "topic_id": topic.get("id"),
        "delivery_id": dlv_id,
        "kind": kind,
        "platform": cand.platform,
        "mode": cand.mode,
        "pillar": cand.pillar,
        "format": cand.fmt,
        "affairs_type": cand.affairs_type,
        "issue_key": cand.issue_key,
        "title": topic.get("title_en") or topic.get("title"),
        "why_now": (topic.get("why_now") or {}).get("note"),
        "angle": cand.angle or draft.ANGLE_FALLBACK.get(cand.pillar),
        "format_note": cand.format_note,
        "sources": sources,
        "flags": {"sensitive": cand.sensitive, "sensitive_reason": cand.sensitive_reason if cand.sensitive else None},
        "status": "drafting",
        "rank": rank,
        "score": cand.score,
        "score_parts": {**cand.parts, "base": cand.base},
        "explore": cand.explore,
        "experiment_id": (cand.experiment or {}).get("id"),
        "arm": cand.arm,
        "created_at": now,
        "updated_at": now,
        "delivered_at": now,
        "expires_at": expiry_for(ctx, kind if kind in ("interview", "evergreen", "request") else "news"),
        "revision": 0,
        "draft_state": "pending",
        "rewrite_count": 0,
    }
    if cand.bank:
        card["questions"] = [{"id": f"q{i}", "q": q, "why": None} for i, q in
                             enumerate((cand.bank.get("questions") or [])[:ctx.settings.drafting.questions_per_card], 1)]
    draft.save_card(ctx, card)
    return card


def fill_card(ctx: Ctx, card: dict[str, Any], cand: Candidate | None = None) -> dict[str, Any]:
    """Draft (external) or ask questions (interview). Falls back to a brief card when out of budget."""
    try:
        if card["mode"] == "interview":
            return draft.fill_interview(ctx, card)
        return draft.draft_external(ctx, card, experiment=cand.experiment if cand else None)
    except BudgetExhausted as exc:
        ctx.run.degrade("brief_cards")
        return draft.make_brief(ctx, card, f"Draft skipped: {why_unavailable(exc)}. Tap 'Draft this' to retry.")
    except Exception as exc:  # noqa: BLE001 - deliver the rest of the set
        log.error(f"fill:{card['id']}", exc)
        ctx.run.degrade("brief_cards")
        return draft.make_brief(ctx, card, "Drafting failed. Tap 'Draft this' to retry.")


def morning_delivery(ctx: Ctx, scout: bool = True, dlv_id: str | None = None, platforms: list[str] | None = None,
                     per_platform: int | None = None) -> dict[str, Any] | None:
    """The day's set (or, from "Get fresh posts", another one): scout, rank, allocate slots and draft. `platforms`
    and `per_platform` narrow it to what he asked for."""
    local_date = ctx.local_date_str()
    dlv_id = dlv_id or delivery_id(local_date)
    if ctx.store.get("deliveries", dlv_id):
        log.info(f"deliver: {dlv_id} already delivered")
        return None
    if scout:
        with ctx.run.step("scout"):
            run_scouts(ctx)
        with ctx.run.step("topics"):
            build_topics(ctx)
    since = timeutil.iso(timeutil.now() - dt.timedelta(hours=96))
    topics = ctx.store.select("topics", "last_seen_at >= ? AND origin = 'scout'", (since,))
    arms = bandit.compute_arms(ctx.store, ctx.settings)
    bandit.snapshot(ctx.store, arms)
    memory = build_memory(ctx)
    cands = build_candidates(ctx, topics, memory, use_llm=ctx.llm.any_available("triage"))
    rng = random.Random(f"{local_date}:{ctx.run.id}")
    plan: dict[str, list[Candidate]] = {}
    taken: set[str] = set()
    for platform in ("linkedin", "x"):
        if ctx.settings.platform_enabled(platform) and (not platforms or platform in platforms):
            plan[platform] = allocate(ctx, platform, cands.get(platform, []), arms, rng, taken_elsewhere=taken,
                                      slots=per_platform)
            taken |= {c.topic_key for c in plan[platform]}
    return deliver_plan(ctx, plan, dlv_id)


def deliver_plan(ctx: Ctx, plan: dict[str, list[Candidate]], dlv_id: str) -> dict[str, Any]:
    """Create and fill the cards for a ranked plan, within the model budget, and record the delivery."""
    local_date = ctx.local_date_str()
    # Budget: trim lowest-ranked beyond the minimum when the model budget can't cover the whole set.
    draft_now = ctx.settings.drafting.interview_draft_now
    need = sum(1 for cs in plan.values() for c in cs if draft_now or not (c.mode == "interview" and c.bank))
    available = ctx.llm.remaining("draft")
    # Out of budget: fewer cards. Providers failing with errors: the full set, as briefs, so nothing is lost.
    if available < need and not ctx.llm.chain_broken("draft"):
        for platform, cs in plan.items():
            min_slots = getattr(ctx.settings.platforms, platform).min_slots
            while len(cs) > min_slots and need > available:
                cs.pop()
                need -= 1
        ctx.run.degrade("fewer_cards")
        ctx.run.note(f"Fewer cards today: model budget allowed about {available} drafts")

    counts: dict[str, int] = {}
    card_ids: list[str] = []
    for platform, cs in plan.items():
        for rank, cand in enumerate(cs, 1):
            card = card_from_candidate(ctx, cand, dlv_id, rank)
            card = fill_card(ctx, card, cand)
            card_ids.append(card["id"])
            counts[platform] = counts.get(platform, 0) + 1
            if cand.topic.get("id") and not str(cand.topic["id"]).startswith("bank:"):
                ctx.store.update("topics", cand.topic["id"], status="carded")
            draft.log_interaction(ctx, "delivered", card, rank=rank, explore=cand.explore)
    needs_input = ctx.store.count("cards", "delivery_id = ? AND status = 'needs_input'", (dlv_id,))
    ctx.store.upsert("deliveries", {
        "id": dlv_id, "local_date": local_date, "delivered_at": timeutil.now_iso(), "counts": counts,
        "degraded": ctx.run.degraded, "notes": ctx.run.notes[-5:], "run_id": ctx.run.id, "kind": "morning",
    })
    log.info(f"deliver: {dlv_id} linkedin={counts.get('linkedin', 0)} x={counts.get('x', 0)} "
             f"needs_input={needs_input} degraded={ctx.run.degraded}")
    return {"id": dlv_id, "counts": counts, "needs_input": needs_input, "card_ids": card_ids}


# ---------------------------------------------------------------------------
# Saturday batch (FR-17): the week's interview and evergreen cards
# ---------------------------------------------------------------------------


def weekly_batch_key(ctx: Ctx) -> str:
    return f"wkb_{timeutil.iso_week(ctx.local_date())}"


def weekly_batch_due(ctx: Ctx) -> bool:
    d = ctx.settings.delivery
    local = ctx.local_now()
    if ctx.store.get("deliveries", weekly_batch_key(ctx)):
        return False
    day = local.strftime("%A").lower()
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    target = days.index(d.weekly_batch_day)
    today = days.index(day)
    return today > target or (today == target and local.strftime("%H:%M") >= d.weekly_batch_local_time)


def weekly_batch(ctx: Ctx) -> dict[str, Any]:
    key = weekly_batch_key(ctx)
    wb = ctx.settings.weekly_batch
    created: list[str] = []
    proposals = _evergreen_proposals(ctx)
    used_bank: set[str] = set()
    for platform in ("linkedin", "x"):
        if not ctx.settings.platform_enabled(platform):
            continue
        want = int(wb.interview_cards.get(platform, 0))
        interview_props = [p for p in proposals if p.get("platform") == platform and p.get("mode") == "interview"
                           and ctx.settings.pillar(platform, p.get("pillar") or "")]
        for prop in interview_props[:want]:
            created.append(_create_interview(ctx, platform, prop, key)["id"])
        remaining = want - min(want, len(interview_props))
        for entry in interview_bank():
            if remaining <= 0:
                break
            if entry.get("platform") != platform or entry["id"] in used_bank:
                continue
            used_bank.add(entry["id"])
            prop = {"pillar": entry["pillar"], "title": entry["title"], "angle": entry.get("angle"),
                    "questions": [{"q": q} for q in entry.get("questions") or []], "bank_id": entry["id"]}
            created.append(_create_interview(ctx, platform, prop, key)["id"])
            remaining -= 1
        # Evergreen external cards from the week's strongest topics not yet carded.
        want_ever = int(wb.evergreen_cards.get(platform, 0))
        if want_ever:
            created.extend(_evergreen_external(ctx, platform, want_ever, key))
    ctx.store.upsert("deliveries", {"id": key, "local_date": ctx.local_date_str(), "delivered_at": timeutil.now_iso(),
                                    "counts": {"cards": len(created)}, "run_id": ctx.run.id, "kind": "weekly_batch",
                                    "notes": ctx.run.notes[-3:]})
    log.info(f"weekly batch: {len(created)} cards")
    return {"id": key, "cards": created}


def _evergreen_proposals(ctx: Ctx) -> list[dict[str, Any]]:
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=7))
    recent = [c.get("title") for c in ctx.store.select("cards", "created_at >= ?", (since,))][:40]
    posted = [p.get("final_text", "")[:200] for p in ctx.store.select("posts", "posted_at >= ?", (since,))][:10]
    pillars = {pl: {k: {"label": p.label, "mode": p.mode} for k, p in ctx.settings.pillars(pl).items()}
               for pl in ("linkedin", "x")}
    payload = {"this_weeks_topics": recent, "recent_posts": posted, "pillars": pillars,
               "want_interview": dict(ctx.settings.weekly_batch.interview_cards)}
    prompt = prompting.render("evergreen", display_name=ctx.settings.display_name, input_json=payload)
    req = LLMRequest(task="evergreen", system=draft._system(ctx), prompt=prompt, max_output_tokens=2500,
                     prompt_version=prompting.version("evergreen"))
    try:
        data, _ = ctx.llm.call_json(req)
    except (BudgetExhausted, ValueError) as exc:
        log.info(f"weekly batch: proposals unavailable ({type(exc).__name__}); using the interview bank")
        return []
    return [t for t in json_rows(data, "topics") if t.get("title")]


def _create_interview(ctx: Ctx, platform: str, prop: dict[str, Any], key: str) -> dict[str, Any]:
    pillar = prop.get("pillar")
    spec = ctx.settings.pillar(platform, pillar or "")
    if spec is None:
        pillar = next(k for k, p in ctx.settings.pillars(platform).items() if p.mode == "interview")
        spec = ctx.settings.pillar(platform, pillar)
    now = timeutil.now_iso()
    questions = [q for q in (prop.get("questions") or [])
                 if isinstance(q, dict) and q.get("q")][:ctx.settings.drafting.questions_per_card]
    card = {
        "id": ids.new_id("crd"),
        "topic_id": f"bank:{prop['bank_id']}" if prop.get("bank_id") else None,
        "delivery_id": key,
        "kind": "interview",
        "platform": platform,
        "mode": "interview",
        "pillar": pillar,
        "format": spec.formats[0],  # type: ignore[union-attr]
        "title": textutil.truncate(prop["title"], 200),
        "why_now": "Prepared in the Saturday batch for this week.",
        "angle": prop.get("angle"),
        "sources": [],
        "flags": {},
        "questions": [{"id": f"q{i}", "q": draft.clean_text(q["q"]), "why": q.get("why")} for i, q in
                      enumerate(questions, 1)],
        "status": "drafting",
        "created_at": now,
        "updated_at": now,
        "delivered_at": now,
        "expires_at": expiry_for(ctx, "interview"),
        "arm": bandit.arm_id(platform, pillar, spec.formats[0]),  # type: ignore[union-attr, arg-type]
        "revision": 0,
        "draft_state": "pending",
    }
    draft.save_card(ctx, card)
    return fill_card(ctx, card)


def _evergreen_external(ctx: Ctx, platform: str, n: int, key: str) -> list[str]:
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=7))
    topics = ctx.store.select("topics", "last_seen_at >= ? AND status = 'candidate' AND origin = 'scout'", (since,))
    memory = build_memory(ctx)
    cands = build_candidates(ctx, topics, memory, use_llm=False).get(platform, [])
    cands = [c for c in cands if c.kind == "news" and c.mode == "external" and not c.sensitive
             and (c.pillar in ("research", "affairs", "learning", "tech"))]
    cands.sort(key=lambda c: -(c.parts.get("fit", 0) * c.parts.get("novelty", 1)))
    out: list[str] = []
    for i, cand in enumerate(cands[:n], 1):
        if platform == "x" and cand.fmt in ("x_reply", "x_quote"):
            cand.fmt = "x_thread" if "x_thread" in ctx.settings.pillar("x", cand.pillar).formats else "x_single"  # type: ignore[union-attr]
        card = card_from_candidate(ctx, cand, key, i, kind="evergreen")
        card["why_now"] = f"Evergreen for this week. {card.get('why_now') or ''}".strip()
        draft.save_card(ctx, card)
        out.append(fill_card(ctx, card, cand)["id"])
        ctx.store.update("topics", cand.topic["id"], status="carded")
    return out
