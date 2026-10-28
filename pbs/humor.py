"""Funny posts, written in a writers' room.

One call writes several versions of the joke, each with a different device (an absurd detail taken literally,
deadpan understatement, escalation, a parody of corporate or LinkedIn-speak, misdirection, a pattern everyone
recognises said freshly). A second call judges them like a tough editor: surprise, specificity, would people share
it, and whether it's a cliché, explains itself, punches down or says something the material doesn't. The best one
becomes the draft; the next best are kept as other versions on the card. When nothing is good, the card says so
instead of pretending. His taste steers both: the funny posts he likes (settings humor.examples) and the jokes he
skipped as "not funny".
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import guardrails, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import LLMRequest, LLMResponse, json_rows

DEVICES = {
    "linkedin": ["a specific absurd detail from the material, taken literally",
                 "deadpan understatement", "escalation (each line one step more absurd)",
                 "a parody of corporate or LinkedIn-speak",
                 "misdirection (set up one meaning, land another)",
                 "the pattern everyone recognises from work, said in a way nobody has"],
    "x": ["a specific absurd detail from the material, taken literally", "deadpan understatement",
          "misdirection (set up one meaning, land another)", "a fake headline or announcement",
          "escalation in two beats", "the pattern everyone recognises, said in a way nobody has"],
}


def _shape(ctx: Ctx, platform: str) -> str:
    if platform == "x":
        return (f"One post under {ctx.settings.humor.x_max_chars} characters: the shorter, the funnier. One beat, "
                "maybe two.")
    return ("A few short lines, at most about 60 words, each line on its own. The first line is already funny: "
            "no warm-up, no context paragraph.")


def _quoted(lines: list[str], limit: int = 8) -> str:
    rows = [f'- "{textutil.truncate(textutil.normalize_ws(t), 280)}"' for t in lines if t and t.strip()][:limit]
    return "\n".join(rows) or "(none yet)"


def not_funny(ctx: Ctx, days: int = 60) -> list[str]:
    """Jokes he skipped as "not funny" lately, newest first."""
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=days))
    rows = [c for c in ctx.store.select("cards", "status = 'skipped' AND status_changed_at >= ?", (since,))
            if (c.get("skip") or {}).get("reason") == "not_funny"]
    rows.sort(key=lambda c: c.get("status_changed_at") or "", reverse=True)
    return [((c.get("draft") or {}).get("text") or " ".join((c.get("draft") or {}).get("posts") or [])) for c in rows]


def writers_room(ctx: Ctx, card: dict[str, Any], vars_: dict[str, Any]) -> tuple[dict[str, Any], LLMResponse, dict[str, Any]]:
    """The draft for a funny card: (draft output in DraftOut's shape, the writers' response, what the room did).
    Raises ValueError when no version comes back."""
    h = ctx.settings.humor
    platform = card["platform"]
    devices = DEVICES["x" if platform == "x" else "linkedin"][: h.options]
    cliches = ", ".join(f'"{c.strip()}"' for c in h.cliches[:40]) or "(none listed)"
    liked = _quoted(h.examples)
    write = prompting.render("humor_write", **vars_, options=h.options, devices="; ".join(devices),
                             shape=_shape(ctx, platform), cliches=cliches, funny_examples=liked)
    data, resp = ctx.llm.call_json(LLMRequest(task="humor_write", system=vars_["system"], prompt=write,
                                              max_output_tokens=3000,
                                              prompt_version=prompting.version("system", "humor_write")))
    seen: set[str] = set()
    options: list[dict[str, str]] = []
    for row in json_rows(data, "options"):
        text = str(row.get("text") or "").strip()
        key = textutil.normalize_ws(text).casefold()
        if text and key not in seen:
            seen.add(key)
            options.append({"text": text, "device": str(row.get("device") or "")[:80]})
    if not options:
        raise ValueError("the writers' room wrote nothing")
    picked, meta = _judge(ctx, card, vars_, options, cliches, liked)
    best = options[picked[0]]
    out = {"text": best["text"], "posts": [], "hooks": [], "hashtags": data.get("hashtags") or [],
           "first_comment": data.get("first_comment") or "", "angle": card.get("angle") or ""}
    alternatives = [options[i]["text"] for i in picked[1:3]]
    return out, resp, {**meta, "device": best["device"] or None, "alternatives": alternatives}


def _judge(ctx: Ctx, card: dict[str, Any], vars_: dict[str, Any], options: list[dict[str, str]], cliches: str,
           liked: str) -> tuple[list[int], dict[str, Any]]:
    """The versions in the order to use them (best first), and the critic's verdict. Without a critic (the call
    failed), the versions that don't lean on a cliché come first, in the writers' order."""
    known = ctx.settings.humor.cliches
    hits = [bool(guardrails.phrase_hits(o["text"], known)) for o in options]
    fallback = sorted(range(len(options)), key=lambda i: hits[i])
    meta: dict[str, Any] = {"options": len(options), "verdict": None, "note": None}
    if len(options) == 1:
        return fallback, meta
    payload = {"topic": card.get("title"), "material": vars_["material"],
               "versions": [{"version": i + 1, "text": o["text"]} for i, o in enumerate(options)]}
    prompt = prompting.render("humor_judge", display_name=ctx.settings.display_name,
                              platform_label=vars_["platform_label"], cliches=cliches,
                              not_funny=_quoted(not_funny(ctx)), funny_examples=liked, input_json=payload)
    try:
        data, _ = ctx.llm.call_json(LLMRequest(task="humor_judge", system=vars_["system"], prompt=prompt,
                                               max_output_tokens=2000,
                                               prompt_version=prompting.version("humor_judge")))
    except Exception:  # noqa: BLE001 - the writers' best guess still makes a card
        return fallback, meta
    scores: dict[int, float] = {}
    bad: set[int] = {i for i, hit in enumerate(hits) if hit}
    for row in json_rows(data, "scores"):
        try:
            i = int(row.get("version")) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= i < len(options):
            continue
        scores[i] = sum(float(row.get(k) or 0) for k in ("surprise", "specific", "share"))
        if any(row.get(k) is True for k in ("cliche", "mean", "wrong")):
            bad.add(i)

    def choice(v: Any) -> int | None:
        try:
            i = int(v) - 1
        except (TypeError, ValueError):
            return None
        return i if 0 <= i < len(options) else None

    order = sorted(range(len(options)), key=lambda i: (i in bad, -scores.get(i, 0), i))
    best, runner = choice(data.get("best")), choice(data.get("runner_up"))
    for i in (runner, best):  # the critic's own picks lead, unless it picked a bad one
        if i is not None and (i not in bad or all(j in bad for j in order)):
            order.remove(i)
            order.insert(0, i)
    verdict = data.get("verdict") if data.get("verdict") in ("strong", "ok", "weak") else None
    if order[0] in bad:
        verdict = "weak"
    meta.update(verdict=verdict, note=textutil.truncate(str(data.get("note") or ""), 240) or None)
    return order, meta
