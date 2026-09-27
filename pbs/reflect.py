"""Weekly reflection (FR-21): rewards, voice, system report, experiments, and playbook changes."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import ids, learn, log, playbook, prompting, report, textutil, timeutil, voice
from .context import Ctx
from .llm.base import BudgetExhausted, LLMRequest


def last_sunday(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def reflection_key(ctx: Ctx) -> str:
    return timeutil.iso_week(last_sunday(ctx.local_date()))


def reflection_due(ctx: Ctx) -> bool:
    if ctx.store.get("system_reports", reflection_key(ctx)):
        return False
    local = ctx.local_now()
    d = ctx.settings.delivery
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    fallback = days.index(d.reflection_fallback_day)
    today = local.weekday()
    if today == 6:  # Sunday: only when Ankit asks (after his screenshot session)
        return False
    return today > fallback or (today == fallback and local.strftime("%H:%M") >= d.reflection_fallback_local_time)


class _Change(BaseModel):
    model_config = ConfigDict(extra="ignore")
    op: Literal["add", "modify", "remove"]
    rule_id: str | None = None
    text: str | None = None
    platform: Literal["linkedin", "x"] | None = None
    pillar: str | None = None
    confidence: Literal["low", "medium", "high"] = "low"
    evidence: list[str] = Field(default_factory=list)
    reversal: str | None = None


class _Experiment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    platform: Literal["linkedin", "x"] | None = None
    pillar: str | None = None
    instruction: str
    hypothesis: str | None = None


class _Proposal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str = "other"
    title: str
    detail: str | None = None
    patch: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"


class _ReflectOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str = ""
    changes: list[_Change] = Field(default_factory=list)
    experiments: list[_Experiment] = Field(default_factory=list)
    proposals: list[_Proposal] = Field(default_factory=list)


def evaluate_experiments(ctx: Ctx) -> list[dict[str, Any]]:
    out = []
    for exp in ctx.store.select("experiments", "status = 'active'"):
        cards = ctx.store.select("cards", "experiment_id = ? AND status IN ('posted','skipped','expired')", (exp["id"],))
        trials, picks = len(cards), sum(1 for c in cards if c["status"] == "posted")
        status = "active"
        if trials >= 4 and picks / trials >= 0.5:
            status = "promoted"
            playbook.apply_changes(ctx, [{"op": "add", "text": exp["instruction"], "platform": exp.get("platform"),
                                          "pillar": exp.get("pillar"), "confidence": "medium",
                                          "evidence": [c["post_id"] for c in cards if c.get("post_id")],
                                          "reversal": "Pick rate on these drafts falls below 30%"}],
                                   source="reflection", summary=f"Experiment promoted: {exp['instruction']}")
        elif trials >= 6 and picks / trials < 0.2:
            status = "retired"
        ctx.store.update("experiments", exp["id"], trials=trials, picks=picks, status=status,
                         stats={"pick_rate": round(picks / trials, 3) if trials else None},
                         updated_at=timeutil.now_iso())
        out.append({"id": exp["id"], "trials": trials, "picks": picks, "status": status})
    return out


def _week_input(ctx: Ctx, start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    s, e = timeutil.iso(start), timeutil.iso(end)
    posts = []
    for p in ctx.store.select("posts", "posted_at >= ? AND posted_at < ?", (s, e), order="posted_at"):
        posts.append({"id": p["id"], "platform": p["platform"], "pillar": p["pillar"], "format": p["format"],
                      "hook": (p.get("hook_used") or {}).get("type"), "edit_ratio": p.get("edit_ratio"),
                      "reward": p.get("reward"), "rank": (p.get("features") or {}).get("rank"),
                      "opening": textutil.truncate(p.get("final_text"), 200)})
    cards = ctx.store.select("cards", "delivered_at >= ? AND delivered_at < ?", (s, e))
    skipped = [{"platform": c["platform"], "pillar": c["pillar"], "format": c["format"],
                "reason": (c.get("skip") or {}).get("reason"), "note": (c.get("skip") or {}).get("note"),
                "title": textutil.truncate(c.get("title"), 90)} for c in cards if c["status"] == "skipped"]
    notes = [i["data"].get("note") for i in ctx.store.select("interactions", "type = 'rewrite_requested' AND at >= ?",
                                                             (s,)) if (i.get("data") or {}).get("note")]
    mix: dict[str, dict[str, int]] = {}
    for c in cards:
        key = f"{c['platform']}:{c['pillar']}"
        m = mix.setdefault(key, {"delivered": 0, "picked": 0})
        m["delivered"] += 1
        m["picked"] += 1 if c["status"] in ("posted", "editing") else 0
    return {"posts": posts, "skipped": skipped[:25], "rewrite_notes": notes[:20], "mix": mix,
            "post_ids": [p["id"] for p in posts]}


def weekly_reflection(ctx: Ctx) -> dict[str, Any]:
    key = reflection_key(ctx)
    end = timeutil.now() + dt.timedelta(seconds=1)  # include anything stamped "now"
    start = end - dt.timedelta(days=7)
    learn.update_rewards(ctx)
    voice.update_voice(ctx, weekly=True)
    playbook.ensure_seed(ctx)
    sections, actions = report.build_report(ctx, start, end)
    applied = report.apply_actions(ctx, actions)
    exp_results = evaluate_experiments(ctx)
    proposal_ids = report.health_proposals(ctx, sections)
    week = _week_input(ctx, start, end)
    summary = ""
    changes_applied = 0
    if week["posts"] or week["skipped"]:
        current = playbook.active(ctx) or {}
        rules = "\n".join(f"- {r['id']}: {r['text']} [{r.get('platform') or 'all'}]" for r in current.get("rules") or [])
        exps = "\n".join(f"- {x['instruction']} ({x.get('trials', 0)} trials, {x.get('picks', 0)} picks)"
                         for x in ctx.store.select("experiments", "status = 'active'")) or "(none)"
        prompt = prompting.render("reflect", display_name=ctx.settings.display_name, rules=rules or "(none)",
                                  experiments=exps, input_json={k: v for k, v in week.items() if k != "post_ids"}
                                  | {"report": {"ranker_accuracy": sections["ranker_accuracy"],
                                                "drafter_quality": sections["drafter_quality"]}})
        req = LLMRequest(task="reflect", system="You improve a writing system carefully, with evidence.",
                         prompt=prompt, max_output_tokens=3000, personal=True, prompt_version=prompting.version("reflect"))
        try:
            out, _ = ctx.llm.call_json(req, _ReflectOut)
            summary = textutil.truncate(out.summary, 500)
            valid_posts = set(week["post_ids"])
            auto = [c.model_dump() | {"evidence": [e for e in c.evidence if e in valid_posts]}
                    for c in out.changes if c.confidence in ("medium", "high")]
            version = playbook.apply_changes(ctx, auto, source="reflection", summary=summary) if auto else None
            changes_applied = len((version or {}).get("changes") or [])
            low = [c for c in out.changes if c.confidence == "low" and c.op == "add" and c.text]
            for exp in [*out.experiments, *(_Experiment(platform=c.platform, pillar=c.pillar, instruction=c.text or "",
                                                         hypothesis=c.reversal) for c in low)][:3]:
                if not exp.instruction.strip():
                    continue
                ctx.store.insert("experiments", {
                    "id": ids.new_id("exp"), "created_at": timeutil.now_iso(), "platform": exp.platform,
                    "pillar": exp.pillar, "instruction": textutil.truncate(exp.instruction, 300),
                    "hypothesis": textutil.truncate(exp.hypothesis or "", 300), "status": "active", "trials": 0,
                    "picks": 0, "stats": {}, "source_version": (playbook.active(ctx) or {}).get("id"),
                    "updated_at": timeutil.now_iso()})
            for prop in out.proposals[:5]:
                payload = {"patch": prop.patch} if prop.patch else {}
                proposal_ids.append(playbook.create_proposal(
                    ctx, kind=prop.kind, title=prop.title, detail=prop.detail, payload=payload,
                    evidence=[e for e in prop.evidence if e in valid_posts], confidence=prop.confidence))
        except (BudgetExhausted, ValueError) as exc:
            log.info(f"reflect: model reflection skipped ({type(exc).__name__})")
            summary = "The model reflection was skipped this week (no model budget). The system report still ran."
    else:
        summary = "No posts or skips this week, so there was nothing to learn from."
    sections["reflection"] = {"summary": summary, "changes_applied": changes_applied, "experiments": exp_results}
    ctx.store.upsert("system_reports", {
        "id": key, "week": key, "created_at": timeutil.now_iso(),
        "period": {"start": timeutil.iso(start), "end": timeutil.iso(end)},
        "sections": sections, "actions": applied, "proposals": proposal_ids,
    })
    log.info(f"reflect: {key} done ({changes_applied} playbook changes, {len(applied)} auto-actions, "
             f"{len(proposal_ids)} proposals)")
    return {"id": key, "changes": changes_applied, "actions": applied, "proposals": proposal_ids}
