"""The editor pass: a second look at each new draft that rewrites only what reads as AI-written.

guardrails.ai_tells finds the patterns: contrast framing, labelled reveals, stock openers and closers, em dashes,
emoji bullets, stacked questions, filler and same-length sentences. When a draft has any, one more model call
rewrites just those sentences. The revision replaces the draft only if all of these hold:
- it has fewer tells;
- it passes every check the draft passed: no figure the sources lack, none dropped, no blocklist term, no avoided
  phrase or bait, no new first-person claim, and no worse length;
- it's still recognisably the same post (at most half the words changed).
Otherwise the original stays: the pass can make a draft better, never worse. It's skipped when the run is short on
model calls (drafts come first: drafting.editor_reserve). A kind of tell that keeps going into posts by hand is part of the voice (voice
stats), so the pass leaves it alone.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import guardrails, hashtags, log, prompting, textutil
from .context import Ctx
from .guardrails import AI_TELL_LABELS, draft_text
from .llm.base import LLMRequest
from .style import Style, render_examples

_THREAD_NUM = re.compile(r"^\s*\d{1,2}\s*/\s*\d{0,2}\s*")


class EditOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = ""
    posts: list[str] = Field(default_factory=list)

    @field_validator("text", mode="before")
    @classmethod
    def _text(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("posts", mode="before")
    @classmethod
    def _posts(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v] if v.strip() else []
        return [str(p) for p in v or [] if p is not None]


def _usable(ctx: Ctx, personal: bool) -> str | None:
    """Why the pass can't run now (None when it can)."""
    s = ctx.settings.drafting
    if not s.editor_pass:
        return "off"
    if ctx.run.degraded:
        return "degraded run"
    if ctx.edits >= s.editor_max_per_run:
        return "run limit"
    if ctx.llm.remaining("edit", personal) <= s.editor_reserve:
        return "budget"
    return None


def tells_in(text: str, style: Style) -> list[dict[str, str]]:
    """The AI tells in a text, minus the kinds that are part of the voice (put into posts by hand, again and again)."""
    return [t for t in guardrails.ai_tells(text) if t["kind"] not in style.own_tells]


def _figures(text: str, evidence: str) -> set[str]:
    """The sourced figures in a text, normalised (so "41 %" and "41%" are the same figure)."""
    unsourced = set(guardrails.unsourced_numbers(text, evidence))
    return {textutil.number_core(n) for n in textutil.numeric_claims(text) if n not in unsourced} - {""}


def reject_reason(ctx: Ctx, card: dict[str, Any], before: dict[str, Any], after: dict[str, Any], *,
                  evidence: str, style: Style, tells_before: int) -> str | None:
    """Why a revision can't replace the draft, or None when it's an improvement that passes every check."""
    old, new = draft_text(before), draft_text(after)
    if not new.strip():
        return "empty"
    if card["format"] == "x_thread" and len(after.get("posts") or []) != len(before.get("posts") or []):
        return "changed the thread's length"
    if len(tells_in(new, style)) >= tells_before:
        return "no fewer tells"
    if set(guardrails.unsourced_numbers(new, evidence)) - set(guardrails.unsourced_numbers(old, evidence)):
        return "added a figure the sources don't have"
    if _figures(old, evidence) - _figures(new, evidence):
        return "dropped a figure"
    if set(guardrails.find_terms(new, ctx.blocklist)) - set(guardrails.find_terms(old, ctx.blocklist)):
        return "blocklist term"
    phrases = [*style.avoid, *ctx.settings.voice.bait_phrases]
    if set(guardrails.phrase_hits(new, phrases)) - set(guardrails.phrase_hits(old, phrases)):
        return "an avoided phrase"
    external = card.get("mode") == "external" or card.get("draft_basis") == "sources" or not card.get("answers")
    if external and set(guardrails.first_person_claims(new)) - set(guardrails.first_person_claims(old)):
        return "claimed an experience"
    lengths = (len(guardrails.length_flags(card["platform"], card["format"], d, ctx.settings)) for d in (before, after))
    if next(lengths) < next(lengths):
        return "too long"
    # The edit-ratio measure used for posted drafts: more than half the words changed is a new post, not an edit.
    if textutil.edit_ratio(old, new) > 0.5:
        return "rewrote too much"
    return None


def polish(ctx: Ctx, card: dict[str, Any], norm: dict[str, Any], style: Style, *, evidence: str,
           personal: bool) -> dict[str, Any]:
    """`norm` is a normalised draft (draft.normalize_output). Returns it with norm["edit"] saying what happened,
    and norm["draft"] replaced when the revision is better."""
    from . import draft as drafting  # draft imports this module

    before = norm["draft"]
    tells = tells_in(draft_text(before), style)
    if not tells:
        norm["edit"] = None
        return norm
    record: dict[str, Any] = {"before": len(tells), "after": len(tells), "kept": False,
                              "kinds": sorted({t["kind"] for t in tells})}
    why_not = _usable(ctx, personal)
    if why_not:
        norm["edit"] = {**record, "skipped": why_not}
        if why_not != "off":
            log.info(f"edit: skipped a {card['platform']} draft ({why_not})")
        return norm
    listed = "\n".join(f"- {AI_TELL_LABELS.get(t['kind'], t['kind'])}: \"{t['text']}\"" for t in tells)
    fmt = ctx.settings.formats.get(card["format"])
    prompt = prompting.render(
        "edit",
        display_name=ctx.settings.display_name,
        platform_label=drafting.PLATFORM_LABEL[card["platform"]],
        format_label=fmt.label.lower() if fmt else "post",
        tells=listed,
        format_instructions=drafting.format_instructions(ctx, card["format"]),
        avoid=", ".join(style.avoid[:40]) or "(nothing listed)",
        examples=render_examples(style.examples),
        input_json={"text": before.get("text") or "", "posts": before.get("posts") or [],
                    "hook_type": norm.get("hook_type"), "claims": norm.get("claims") or []},
    )
    req = LLMRequest(task="edit", system=drafting._system(ctx), prompt=prompt, max_output_tokens=2500,
                     personal=personal, prompt_version=prompting.version("system", "edit"))
    try:
        out, resp = ctx.llm.call_json(req, EditOut)
    except Exception as exc:  # noqa: BLE001 - the draft is fine as it is; the pass is a bonus
        norm["edit"] = {**record, "skipped": type(exc).__name__}
        log.info(f"edit: skipped a {card['platform']} draft ({type(exc).__name__})")
        return norm
    ctx.edits += 1
    text, _ = hashtags.split_trailing(drafting.clean_text(out.text))
    posts = [drafting.clean_text(_THREAD_NUM.sub("", p)) for p in out.posts if p and p.strip()]
    if card["format"] == "x_thread":
        after = {**before, "text": "", "posts": posts or [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]}
    else:
        after = {**before, "text": text or "\n\n".join(posts), "posts": []}
    record.update(after=len(tells_in(draft_text(after), style)), provider=resp.provider)
    reason = reject_reason(ctx, card, before, after, evidence=evidence, style=style, tells_before=len(tells))
    if reason:
        norm["edit"] = {**record, "reason": reason}
        log.info(f"edit: kept the original draft of a {card['platform']} card ({reason})")
        return norm
    norm["draft"] = after
    norm["edit"] = {**record, "kept": True}
    log.info(f"edit: polished a {card['platform']} draft (tells {record['before']}→{record['after']})")
    return norm
