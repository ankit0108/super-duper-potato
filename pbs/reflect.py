"""Weekly reflection (FR-21): rewards, voice, system report, experiments, and playbook changes."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import ids, learn, log, playbook, prompting, report, settings, stats, textutil, timeutil, voice
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
    rule: str | None = None  # a guardrail as a playbook rule, when it can't be a setting
    platform: str | None = None  # "linkedin" or "x"; anything else means both
    evidence: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"


class _Advice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    detail: str = ""


class _ReflectOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str = ""
    changes: list[_Change] = Field(default_factory=list)
    experiments: list[_Experiment] = Field(default_factory=list)
    proposals: list[_Proposal] = Field(default_factory=list)
    advice: list[_Advice] = Field(default_factory=list)


def repair_patch(ctx: Ctx, patch: dict[str, Any]) -> dict[str, Any]:
    """A common wrong shape of a lane weight change, put right: {"strategy": {"pillar_weights": {"humor": 0.05}}} or
    {"strategy": {"humor": 0.05}} becomes {"strategy": {"<platform>": {"humor": {"weight": 0.05}}}} when the lane
    exists on exactly one platform. Anything else is returned as it was."""
    strategy = patch.get("strategy")
    if not isinstance(strategy, dict):
        return patch
    flat = {**(strategy.get("pillar_weights") or {}),
            **{k: v for k, v in strategy.items() if k not in ("linkedin", "x", "pillar_weights")}}
    if not flat:
        return patch
    fixed: dict[str, Any] = {pl: dict(strategy.get(pl) or {}) for pl in ("linkedin", "x") if strategy.get(pl)}
    for lane, value in flat.items():
        weight = value.get("weight") if isinstance(value, dict) else value
        homes = [pl for pl in ("linkedin", "x") if lane in ctx.settings.pillars(pl)]
        if len(homes) != 1 or not isinstance(weight, (int, float)):
            return patch  # ambiguous or not a weight: leave it, and validation decides
        fixed.setdefault(homes[0], {})[lane] = {"weight": weight}
    return {**{k: v for k, v in patch.items() if k != "strategy"}, "strategy": fixed}


def proposal_payload(ctx: Ctx, prop: _Proposal, overrides: dict[str, Any]) -> dict[str, Any]:
    """What approving the proposal will change, or {} when nothing valid: a settings patch that validates (after
    repair_patch), else a guardrail written as a playbook rule."""
    if prop.patch:
        for patch in (prop.patch, repair_patch(ctx, prop.patch)):
            _, error = settings.validate_patch(overrides, patch)
            if not error:
                return {"patch": patch}
        log.info("reflect: a proposed setting change isn't valid; kept as advice")
    if prop.rule and prop.rule.strip():
        return {"rule": {"text": textutil.truncate(prop.rule.strip(), 600),
                         "platform": prop.platform if prop.platform in ("linkedin", "x") else None,
                         "confidence": prop.confidence}}
    return {}


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
        in_draft, in_post = learn.post_tells(ctx, p)
        posts.append({"id": p["id"], "platform": p["platform"], "pillar": p["pillar"], "format": p["format"],
                      "hook": (p.get("hook_used") or {}).get("type"), "edit_ratio": p.get("edit_ratio"),
                      "ai_tells_in_draft": in_draft, "ai_tells_posted": in_post,
                      "written_from": (p.get("features") or {}).get("draft_basis"),
                      "visual": (p.get("features") or {}).get("visual"),
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
    edits = [(c.get("llm") or {}).get("edit") or {} for c in cards if c.get("draft")]
    writing = {"drafts": len(edits), "with_ai_tells": sum(1 for x in edits if x.get("before")),
               "editor_kept": sum(1 for x in edits if x.get("kept")),
               "tells_before_editor": sum(int(x.get("before") or 0) for x in edits),
               "tells_after_editor": sum(int(x.get("after") or 0) for x in edits)}
    return {"posts": posts, "skipped": skipped[:25], "rewrite_notes": notes[:20], "mix": mix, "writing": writing,
            # Whether the scouts' scores match what he posted: the average score of posted cards against skipped
            # or expired ones (an observation over a week's cards, not a verdict).
            "scout_scores": stats.scout_calibration(cards),
            # Whether his posts come from the top half of the editors' order (an observation, not a verdict).
            "editor_order": stats.editor_calibration(cards),
            # The pictures from the sources: what he kept of each kind, and kinds no longer attached by themselves.
            "pictures": stats.media_kept(ctx),
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
    proposal_ids, advice = report.health_proposals(ctx, sections)
    week = _week_input(ctx, start, end)
    summary = ""
    changes_applied = 0
    if week["posts"] or week["skipped"]:
        current = playbook.active(ctx) or {}
        rules = "\n".join(f"- {r['id']}: {r['text']} [{r.get('platform') or 'all'}]" for r in current.get("rules") or [])
        exps = "\n".join(f"- {x['instruction']} ({x.get('trials', 0)} trials, {x.get('picks', 0)} picks)"
                         for x in ctx.store.select("experiments", "status = 'active'")) or "(none)"
        pillar_keys = "; ".join(f"{pl}: " + ", ".join(f"{k} (now {spec.weight:g})"
                                                       for k, spec in ctx.settings.pillars(pl).items())
                                for pl in ("linkedin", "x"))
        prompt = prompting.render("reflect", display_name=ctx.settings.display_name, rules=rules or "(none)",
                                  pillar_keys=pillar_keys,
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
            overrides = dict(ctx.store.get_setting("overrides", {}) or {})
            for prop in out.proposals[:5]:
                # Checked now, not when he approves: only a proposal that approving can act on is shown as one;
                # the rest is advice in the weekly review.
                payload = proposal_payload(ctx, prop, overrides)
                if not payload:
                    advice.append({"title": textutil.truncate(prop.title, 200),
                                   "detail": textutil.truncate(prop.detail or "", 500)})
                    continue
                proposal_ids.append(playbook.create_proposal(
                    ctx, kind=prop.kind, title=prop.title, detail=prop.detail, payload=payload,
                    evidence=[e for e in prop.evidence if e in valid_posts], confidence=prop.confidence))
            advice.extend({"title": textutil.truncate(a.title, 200), "detail": textutil.truncate(a.detail, 500)}
                          for a in out.advice[:5] if a.title.strip())
        except (BudgetExhausted, ValueError) as exc:
            log.info(f"reflect: model reflection skipped ({type(exc).__name__})")
            summary = "The model reflection was skipped this week (no model budget). The system report still ran."
    else:
        summary = "No posts or skips this week, so there was nothing to learn from."
    sections["reflection"] = {"summary": summary, "changes_applied": changes_applied, "experiments": exp_results,
                              "advice": advice[:10]}
    ctx.store.upsert("system_reports", {
        "id": key, "week": key, "created_at": timeutil.now_iso(),
        "period": {"start": timeutil.iso(start), "end": timeutil.iso(end)},
        "sections": sections, "actions": applied, "proposals": proposal_ids,
    })
    log.info(f"reflect: {key} done ({changes_applied} playbook changes, {len(applied)} auto-actions, "
             f"{len(proposal_ids)} proposals)")
    return {"id": key, "changes": changes_applied, "actions": applied, "proposals": proposal_ids}
