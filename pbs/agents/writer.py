"""The platform writers: one for LinkedIn, one for X.

Before the morning's drafts are written, each writer reads its scout's report and the posts chosen from it, and
1. plans each post: the one job it has, the direction of the opening, its shape, the source facts that carry it,
   how it ends and what to avoid. The plan goes to the model that writes the draft and shows on the card as the
   "Writer's plan";
2. may swap a pick it has nothing sharp to say about for a better opportunity from the report, in the same lane
   only: the lane mix stays his.

The writer's first model is a different one from the scout's, so a report isn't reviewed by the model that wrote
it. After each draft, check() looks for the platform's basics in code; what it finds goes to the editor pass
with the AI tells. When no model answers, or the day's drafts need the budget, the drafts are written without
plans, as before.

A writer's knowledge of its platform is in pbs/prompts/writer_linkedin.md and writer_x.md, and in the platform
guide every draft gets (pbs/defaults/platform_guide.yaml).
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from .. import guardrails, log, prompting, textutil
from ..context import Ctx
from ..llm.base import AllProvidersFailed, BudgetExhausted, LLMError, LLMRequest
from . import scout as scouts

if TYPE_CHECKING:
    from ..rank import Candidate

SHAPES = {"linkedin": ("news_take", "lesson", "framework", "disagreement", "number"),
          "x": ("observation", "reply", "quote", "thread", "question")}
MAX_SWAPS = 1  # per platform a morning: a writer adjusts the set, it doesn't remake it
BENCH = 3  # bench stories offered for a swap

# What check() can find, as the editor pass names it.
CRAFT_LABELS = {
    "buried_opening": "The opening runs past LinkedIn's fold (about 210 characters before “…see more”)",
    "preamble": "A preamble before the point",
    "link_in_body": "A link in the post (it belongs in the first comment or a reply)",
    "generic_ending": "A generic closing question",
    "headline_prefix": "A headline prefix (“BREAKING:”, “NEW:”)",
    "flattery": "A reply that opens with praise instead of adding something",
}
_PREAMBLE = re.compile(r"^\W*(in today'?s|i want to talk about|i wanted to share|let'?s talk about|let me tell you|"
                       r"as we all know|it'?s no secret|in the world of|in this post|i'?ve been thinking)\b", re.I)
_GENERIC_END = re.compile(r"^\W*(what do you think|what are your thoughts|thoughts|agree|do you agree|"
                          r"what'?s your take|let me know in the comments)\W*$", re.I)
_HEADLINE = re.compile(r"^\W*(breaking|just in|new|news|update|thread|announcement)\s*[:—-]\s", re.I)
_FLATTERY = re.compile(r"^\W*(great (post|point|thread|take)|love this|so true|well said|this\W*$|"
                       r"totally agree|couldn'?t agree more|spot on|100%)", re.I)
_URL = re.compile(r"https?://\S+")


# ---------------------------------------------------------------------------
# After a draft: the platform's basics, checked in code
# ---------------------------------------------------------------------------


def check(card: dict[str, Any], draft: dict[str, Any]) -> list[dict[str, str]]:
    """The platform basics a draft misses, as [{kind, text}] like guardrails.ai_tells. Conservative on purpose:
    each is something a reader of that platform would see at a glance."""
    fmt, platform = card.get("format"), card.get("platform")
    posts = [p for p in (draft.get("posts") or []) if p and p.strip()]
    text = (draft.get("text") or "").strip() or "\n\n".join(posts)
    if not text:
        return []
    first = posts[0] if posts else text
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    opening, last = lines[0], lines[-1]
    found: list[dict[str, str]] = []

    def add(kind: str, quote: str) -> None:
        found.append({"kind": kind, "text": textutil.truncate(quote, 90)})

    if platform == "linkedin":
        if len(opening) > 230:
            add("buried_opening", opening)
        if _PREAMBLE.match(opening):
            add("preamble", opening)
        if _GENERIC_END.match(last):
            add("generic_ending", last)
    else:
        if _HEADLINE.match(first):
            add("headline_prefix", first)
        if fmt == "x_reply" and _FLATTERY.match(first):
            add("flattery", first)
    if (link := _URL.search(first if posts else text)) and fmt != "x_quote":
        add("link_in_body", link.group(0))
    return found


def issues(card: dict[str, Any], draft: dict[str, Any], tells: list[dict[str, str]]) -> list[dict[str, str]]:
    """The AI tells plus the platform basics, for the editor pass."""
    return [*tells, *check(card, draft)]


def label(kind: str) -> str:
    return CRAFT_LABELS.get(kind) or guardrails.AI_TELL_LABELS.get(kind, kind)


# ---------------------------------------------------------------------------
# Before the drafts: the review
# ---------------------------------------------------------------------------


class _Plan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    job: str = ""
    opening: str = ""
    shape: str | None = None
    facts: list[Any] = []
    ending: str = ""
    avoid: str = ""


class _Swap(BaseModel):
    model_config = ConfigDict(extra="ignore")
    drop: str = ""
    take: str = ""
    reason: str = ""


class _Review(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plans: list[_Plan] = []
    swaps: list[_Swap] = []


def plannable(c: Candidate) -> bool:
    """What a writer plans: the plain posts a scout judges (not question cards, funny takes, quotes or thoughts)."""
    return bool(scouts._eligible([c]))


def _clean(value: Any, limit: int) -> str:
    return textutil.truncate(textutil.normalize_ws(str(value or "")), limit)


def _row(ctx: Ctx, ref: str, c: Candidate, opp: dict[str, Any] | None, *, bench: bool = False) -> dict[str, Any]:
    """What the writer sees of a story: short, so ten X picks fit the smallest free model's input."""
    spec = ctx.settings.pillar(c.platform, c.pillar)
    note = c.scout or (scouts.note_of(opp) if opp else {})
    row: dict[str, Any] = {
        "id": ref, "title": _clean(c.topic.get("title_en") or c.topic.get("title"), 110),
        "lane": spec.label if spec else c.pillar, "summary": _clean(c.topic.get("summary"), 140 if bench else 180),
        "evidence": [_clean(e, 70) for e in (note.get("evidence") or [])[:2]],
        "scout_why": _clean(note.get("why"), 120 if bench else 140),
    }
    if not bench:
        row.update(format=c.fmt, angle=_clean(c.angle, 120), evidence_level=note.get("evidence_level"),
                   reply_to=_clean(note.get("reply_to"), 100))
    return {k: v for k, v in row.items() if v not in (None, [], "")}


def payload(ctx: Ctx, picks: dict[str, Candidate], bench: dict[str, Candidate],
            opps: dict[str, dict[str, Any]]) -> str:
    """The review's input as compact JSON (no indentation: every character counts against a small model's limit)."""
    data = {"picks": [_row(ctx, r, c, opps.get(c.topic.get("id"))) for r, c in picks.items()],
            "bench": [_row(ctx, r, c, opps.get(c.topic.get("id")), bench=True) for r, c in bench.items()]}
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _brief(platform: str, plan: _Plan) -> dict[str, Any] | None:
    job = _clean(plan.job, 220)
    if not job:
        return None
    return {
        "job": job, "opening": _clean(plan.opening, 220),
        "shape": plan.shape if plan.shape in SHAPES[platform] else None,
        "facts": [f for f in (_clean(x, 160) for x in plan.facts[:4]) if f],
        "ending": _clean(plan.ending, 180), "avoid": _clean(plan.avoid, 180),
        "swapped_for": None, "reason": None,
    }


def request(platform: str, prompt: str) -> LLMRequest:
    return LLMRequest(task="brief", system=f"You are an expert {scouts.PLATFORM_LABEL[platform]} writer and editor "
                                           "planning posts. You use only the facts you are given.",
                      prompt=prompt, max_output_tokens=2400, prompt_version=prompting.version(f"writer_{platform}"))


def review(ctx: Ctx, platform: str, picks: list[Candidate], cands: list[Candidate],
           report: dict[str, Any] | None) -> tuple[list[Candidate], dict[str, Any]]:
    """Plan the platform's picks and apply at most one same-lane swap. Returns (picks, what happened); the picks
    come back unchanged when there's nothing to plan or no model answers."""
    info: dict[str, Any] = {"planned": 0, "swapped": 0, "status": "skipped"}
    mine = [(i, c) for i, c in enumerate(picks) if plannable(c)]
    if not mine:
        return picks, info
    opps = {o["id"]: o for o in (report or {}).get("opportunities") or []}
    ref = {f"P{n}": (i, c) for n, (i, c) in enumerate(mine, 1)}
    by_topic = {c.topic.get("id"): c for c in cands if plannable(c)}
    chosen = {c.topic_key for c in picks}
    bench_opps = [o for o in opps.values() if not o.get("card_id") and o["id"] not in chosen and o["id"] in by_topic]
    bench = {f"B{n}": by_topic[o["id"]] for n, o in enumerate(bench_opps[:BENCH], 1)}
    prompt = prompting.render(
        f"writer_{platform}", display_name=ctx.settings.display_name, today=ctx.local_date_str(),
        shapes=", ".join(SHAPES[platform]), input_json=payload(ctx, {r: c for r, (_, c) in ref.items()}, bench, opps))
    try:
        out, resp = ctx.llm.call_json(request(platform, prompt), _Review)
    except BudgetExhausted:
        info["status"] = "budget"
        return picks, info
    except (AllProvidersFailed, LLMError, ValueError) as exc:
        info["status"] = "failed"
        log.info(f"writer: {platform} drafts go ahead without plans ({type(exc).__name__})")
        return picks, info
    plans = {p.id.strip().upper(): p for p in out.plans}
    result = list(picks)
    swapped_refs: set[str] = set()
    for swap in out.swaps:
        drop, take = swap.drop.strip().upper(), swap.take.strip().upper()
        if info["swapped"] >= MAX_SWAPS or drop not in ref or take not in bench or drop in swapped_refs:
            continue
        index, old = ref[drop]
        new = bench[take]
        if new.pillar != old.pillar or new.topic_key in {c.topic_key for c in result}:
            continue  # another lane, or already in the set: the mix isn't the writer's to change
        fmt = new.fmt
        if old.fmt in ("x_reply", "x_quote") and not new.sensitive and new.affairs_type != "story":
            fmt = "x_reply"  # the set keeps its replies
        incoming = replace(new, fmt=fmt, score=old.score, explore=False, experiment=None)
        brief = _brief(platform, plans.get(take) or plans.get(drop) or _Plan(id=take)) or {
            "job": "", "opening": "", "shape": None, "facts": [], "ending": "", "avoid": ""}
        brief.update(swapped_for=old.topic.get("title_en") or old.topic.get("title"),
                     reason=_clean(swap.reason, 200) or None)
        incoming.brief = {**brief, "by": resp.model}
        result[index] = incoming
        swapped_refs.add(drop)
        info["swapped"] += 1
    for r, (_, c) in ref.items():
        if r in swapped_refs or r not in plans:
            continue
        brief = _brief(platform, plans[r])
        if brief:
            c.brief = {**brief, "by": resp.model}
            info["planned"] += 1
    info.update(status="ok", model=resp.model, provider=resp.provider,
                planned=info["planned"] + info["swapped"])
    log.info(f"writer: {platform} planned {info['planned']} of {len(mine)} posts, {info['swapped']} swapped")
    return result, info
