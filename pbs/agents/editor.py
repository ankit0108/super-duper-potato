"""The editors: one for LinkedIn, one for X. They decide what gets written each morning and in what order.

After allocation (his lane mix, the learner, exploration, reply slots) and before the writers plan, each editor reads
the platform's picks with a few alternatives from the same lanes, the scouts' marks and evidence, his recent posts,
skips and results, and:
1. orders the board (the card ranks);
2. may swap a pick for a stronger alternative in the same lane (his mix stays his);
3. says in one line why each pick is worth his time today;
4. names up to `agents.runner_ups` runner-ups, shown on the board with "Draft this" (no model call until he taps).

Code keeps the rules: same lane only, exploration picks stay (so the learner keeps learning), reply slots stay
replies, question cards, funny posts, quotes and thoughts can move but not be swapped, unknown ids are ignored. With
no model, or when the drafts need the budget, the allocation stands and the runner-ups are the best alternatives.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from .. import feedback, log, prompting, textutil, timeutil
from ..context import Ctx
from ..llm.base import AllProvidersFailed, BudgetExhausted, LLMError, LLMRequest
from . import scout as scouts

if TYPE_CHECKING:
    from ..rank import Candidate

ALTERNATIVES = 10  # at most, across lanes: enough to choose from, small enough for the smallest model
NOTES = {
    "linkedin": "His LinkedIn readers are engineers and people running AI and automation at work. A pick earns its slot "
                "when it gives them something specific to check against their own work, worth saving or sending on. "
                "Posts reach people by topic and his shown expertise, so stay in his fields.",
    "x": "His X account is small (replies and quote-posts are how he is found). A pick earns its slot when it is live "
         "now (posts go stale within two days) and he can add one specific thing: a detail, an implication, a "
         "precise question.",
}


def slate_id(platform: str, delivery_id: str) -> str:
    return f"es_{platform}_{delivery_id}"


def _locked(c: Candidate) -> bool:
    """A pick the editor can move but not swap: exploration, and the lanes with their own craft."""
    return c.explore or not scouts._eligible([c])


class _Swap(BaseModel):
    model_config = ConfigDict(extra="ignore")
    drop: str = ""
    take: str = ""
    why: str = ""


class _Runner(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    why: str = ""


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order: list[str] = []
    swaps: list[_Swap] = []
    why: dict[str, str] = {}
    runners_up: list[_Runner] = []


def _row(ctx: Ctx, ref: str, c: Candidate, now: dt.datetime) -> dict[str, Any]:
    spec = ctx.settings.pillar(c.platform, c.pillar)
    note = c.scout or {}
    first = timeutil.parse(c.topic.get("first_seen_at") or c.topic.get("last_seen_at"))
    kind = ("question card" if c.mode == "interview" else c.post_type.replace("_", " ") if c.post_type else
            "exploration" if c.explore else "post")
    row = {"id": ref, "title": textutil.truncate(c.topic.get("title_en") or c.topic.get("title") or "", 110),
           "lane": spec.label if spec else c.pillar, "format": c.fmt, "kind": kind,
           "age_hours": round((now - first).total_seconds() / 3600) if first else None,
           "summary": textutil.truncate(c.topic.get("summary") or "", 140),
           "evidence": [textutil.truncate(e, 70) for e in (note.get("evidence") or [])[:2]],
           "scout_score": note.get("score"), "scout_why": textutil.truncate(note.get("why") or "", 110)}
    if _locked(c):
        row["fixed"] = True
    return {k: v for k, v in row.items() if v not in (None, [], "")}


def payload(ctx: Ctx, picks: dict[str, Candidate], alts: dict[str, Candidate]) -> str:
    now = timeutil.now()
    data = {"picks": [_row(ctx, r, c, now) for r, c in picks.items()],
            "alternatives": [_row(ctx, r, c, now) for r, c in alts.items()]}
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def alternatives(picks: list[Candidate], cands: list[Candidate]) -> list[Candidate]:
    """The best unchosen plain stories in the lanes the set already has, a few per lane."""
    lanes = {c.pillar for c in picks}
    chosen = {c.topic_key for c in picks}
    per_lane: dict[str, int] = {}
    out = []
    for c in sorted(cands, key=lambda c: -c.base):
        if c.pillar not in lanes or c.topic_key in chosen or not scouts._eligible([c]) or c.explore:
            continue
        if per_lane.get(c.pillar, 0) >= 3:
            continue
        per_lane[c.pillar] = per_lane.get(c.pillar, 0) + 1
        chosen.add(c.topic_key)
        out.append(c)
        if len(out) >= ALTERNATIVES:
            break
    return out


def request(ctx: Ctx, platform: str, prompt: str) -> LLMRequest:
    return LLMRequest(task="editor", system=f"You are {ctx.settings.display_name}'s {scouts.PLATFORM_LABEL[platform]} "
                                            "editor. You decide what is worth his time today, from the evidence given.",
                      prompt=prompt, max_output_tokens=1800, prompt_version=prompting.version("editor"))


def _runner_row(c: Candidate, why: str) -> dict[str, Any]:
    note = c.scout or {}
    return {"id": c.topic["id"], "title": c.topic.get("title_en") or c.topic.get("title") or "", "lane": c.pillar,
            "format": c.fmt, "angle": c.angle or "", "why": textutil.truncate(textutil.normalize_ws(why), 200),
            "score": note.get("score"), "evidence": note.get("evidence") or [],
            "evidence_level": note.get("evidence_level"), "card_id": None}


def choose(ctx: Ctx, platform: str, picks: list[Candidate], cands: list[Candidate], dlv_id: str, *,
           use_llm: bool = True) -> tuple[list[Candidate], dict[str, Any]]:
    """The editor's set for a platform: (picks in board order, the slate stored for the desk)."""
    n_runners = ctx.settings.agents.runner_ups
    alts = alternatives(picks, cands)
    ref = {f"P{i}": c for i, c in enumerate(picks, 1)}
    aref = {f"A{i}": c for i, c in enumerate(alts, 1)}
    slate: dict[str, Any] = {"id": slate_id(platform, dlv_id), "platform": platform, "delivery_id": dlv_id,
                             "local_date": ctx.local_date_str(), "created_at": timeutil.now_iso(), "status": "fallback",
                             "model": None, "provider": None, "swaps": 0, "runners_up": [], "error": None}
    result = list(picks)
    runners: list[dict[str, Any]] = []
    out: _Out | None = None
    if not picks:
        slate["status"] = "skipped"
    elif not use_llm:
        slate["error"] = "The day's drafts needed the model budget, so the set is as the ranking made it"
    else:
        prompt = prompting.render(
            "editor", display_name=ctx.settings.display_name, today=ctx.local_date_str(),
            platform_label=scouts.PLATFORM_LABEL[platform], platform_notes=NOTES[platform],
            audience=scouts._audience(ctx, platform), results=scouts._his_results(ctx, platform),
            recent_posts=scouts._recent_posts(ctx, platform),
            feedback=feedback.render(feedback.recent_feedback(ctx, limit=6, notes_first=True)),
            n_runners=n_runners, input_json=payload(ctx, ref, aref))
        try:
            out, resp = ctx.llm.call_json(request(ctx, platform, prompt), _Out)
            slate.update(status="ok", model=resp.model, provider=resp.provider)
        except BudgetExhausted:
            slate["error"] = "Model quota was short, so the set is as the ranking made it"
        except (AllProvidersFailed, LLMError, ValueError) as exc:
            slate["error"] = "No model answered, so the set is as the ranking made it"
            log.info(f"editor: {platform} set left as ranked ({type(exc).__name__})")
    why = {k.strip().upper(): v for k, v in (out.why if out else {}).items()}
    taken: set[str] = set()
    if out:
        for swap in out.swaps:
            drop, take = swap.drop.strip().upper(), swap.take.strip().upper()
            if drop not in ref or take not in aref or take in taken:
                continue
            index = next((i for i, c in enumerate(result) if c is ref[drop]), None)
            old, new = ref[drop], aref[take]
            if index is None or _locked(old) or new.pillar != old.pillar:
                continue  # exploration and the special lanes stay; a swap never changes his mix
            fmt = "x_reply" if old.fmt in ("x_reply", "x_quote") and not new.sensitive else new.fmt
            spec = ctx.settings.pillar(platform, new.pillar)
            if spec and fmt not in spec.formats:
                fmt = new.fmt
            result[index] = replace(new, fmt=fmt, score=old.score)
            result[index].editor = {"why": textutil.truncate(textutil.normalize_ws(why.get(take) or swap.why), 220),
                                    "swapped_for": old.topic.get("title_en") or old.topic.get("title")}
            ref[drop] = result[index]
            taken.add(take)
            slate["swaps"] += 1
        order = [r.strip().upper() for r in out.order if r.strip().upper() in ref]
        ranked = list(dict.fromkeys(ref[r].topic_key for r in order))
        result.sort(key=lambda c: ranked.index(c.topic_key) if c.topic_key in ranked else len(ranked))
        for r, c in ref.items():
            if c.editor is None and why.get(r):
                c.editor = {"why": textutil.truncate(textutil.normalize_ws(why[r]), 220), "swapped_for": None}
        for runner in out.runners_up:
            r = runner.id.strip().upper()
            if r in aref and r not in taken and len(runners) < n_runners:
                taken.add(r)
                runners.append(_runner_row(aref[r], runner.why or why.get(r) or ""))
    chosen = {c.topic_key for c in result}
    for r, c in aref.items():  # fill the runner-ups with the best of the rest (no reason given: the ranking's order)
        if len(runners) >= n_runners:
            break
        if r not in taken and c.topic_key not in chosen and all(x["id"] != c.topic["id"] for x in runners):
            runners.append(_runner_row(c, ""))
    for rank, c in enumerate(result, 1):
        c.editor = {**(c.editor or {"why": "", "swapped_for": None}), "rank": rank}
    slate["runners_up"] = runners
    slate["picks"] = [{"id": c.topic_key, "title": c.topic.get("title_en") or c.topic.get("title") or "",
                       "why": (c.editor or {}).get("why") or ""} for c in result]
    ctx.store.upsert("editor_slates", slate)
    log.info(f"editor: {platform} {slate['status']}: {len(result)} picks ordered, {slate['swaps']} swapped, "
             f"{len(runners)} runner-ups")
    return result, slate


def recent(ctx: Ctx, days: int = 2) -> list[dict[str, Any]]:
    since = (ctx.local_date() - dt.timedelta(days=days)).isoformat()
    return ctx.store.select("editor_slates", "local_date >= ?", (since,), order="created_at DESC")


def calibration(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Whether he posts from the top of the editor's order: of the cards he posted, how many were in its top half.
    An observation over few cards, not a verdict."""
    out: dict[str, Any] = {}
    for platform in ("linkedin", "x"):
        sets: dict[str, list[dict[str, Any]]] = {}
        for c in cards:
            if c.get("platform") == platform and (c.get("editor") or {}).get("rank") and c.get("delivery_id"):
                sets.setdefault(c["delivery_id"], []).append(c)
        top = bottom = 0
        for group in sets.values():
            half = len(group) / 2
            for c in group:
                if c.get("status") == "posted":
                    if c["editor"]["rank"] <= half:
                        top += 1
                    else:
                        bottom += 1
        if top or bottom:
            out[platform] = {"posted_top_half": top, "posted_bottom_half": bottom}
    return out
