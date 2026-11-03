"""Ankit's explicit feedback on suggestions: why he skipped them, and which he moved or copied to the other
platform.

It reaches the ranking the next morning (triage reads it), the weekly reflection (which reads skips with their
notes), and the desk (Insights shows what the system is learning from), so a reason is never just stored.

A skip for the writing ("not written well / not my voice") is about the draft, not the topic: it stays out of the
ranking and reaches the drafter instead (writing_feedback → the style rules, and the weekly voice update).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import textutil, timeutil
from .context import Ctx

REASON_LABEL = {
    "not_interesting": "not interesting",
    "off_brand": "off-brand for this platform",
    "wrong_timing": "wrong timing",
    "too_risky": "too risky",
    "already_covered": "already covered",
    "other": "another reason",
    "wrong_platform": "wrong platform",
    "not_funny": "not funny",
    "poorly_written": "not written well (the topic was fine)",
}
# Reasons that say something about the topic itself; "wrong timing" and "already covered" don't.
TOPIC_REASONS = ("not_interesting", "off_brand", "too_risky", "other")
# Reasons that are about the draft: the drafter learns from them, the ranking never sees them.
WRITING_REASONS = ("poorly_written",)


def recent_feedback(ctx: Ctx, days: int = 21, limit: int = 12, notes_first: bool = False,
                    writing: bool = False) -> list[dict[str, Any]]:
    """Newest first. With `notes_first`, skips that carry his own words come before the rest. Skips for the writing
    are left out unless `writing` (the desk lists them; the ranking must not read them as a dull topic)."""
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=days))
    rows: list[dict[str, Any]] = []
    for c in ctx.store.select("cards", "status = 'skipped' AND status_changed_at >= ?", (since,)):
        skip = c.get("skip") or {}
        reason = skip.get("reason")
        note = (skip.get("note") or "").strip()
        if reason == "wrong_platform" or (reason not in TOPIC_REASONS and not note):
            continue  # a move to the other platform is listed as the cross-post itself
        if reason in WRITING_REASONS and not writing:
            continue
        rows.append({"at": skip.get("at") or c.get("status_changed_at"), "kind": "skip", "card_id": c["id"],
                     "title": textutil.truncate(c.get("title"), 120), "platform": c["platform"],
                     "pillar": c["pillar"], "reason": reason, "note": textutil.truncate(note, 300) or None})
    for i in ctx.store.select("interactions", "type = 'crosspost' AND at >= ?", (since,)):
        data = i.get("data") or {}
        card = ctx.store.get("cards", i["card_id"]) if i.get("card_id") else None
        if not card:
            continue
        rows.append({"at": i["at"], "kind": "crosspost", "card_id": card["id"],
                     "title": textutil.truncate(card.get("title"), 120), "platform": card["platform"],
                     "pillar": card["pillar"], "reason": data.get("mode"), "to": data.get("to"),
                     "note": textutil.truncate(data.get("note") or "", 300) or None})
    rows.sort(key=lambda r: r["at"] or "", reverse=True)
    if notes_first:
        rows.sort(key=lambda r: 0 if r["note"] else 1)
    return rows[:limit]


def writing_feedback(ctx: Ctx, platform: str | None = None, days: int = 45,
                     limit: int = 6) -> list[dict[str, Any]]:
    """Drafts he skipped as not written well, newest first: what the draft said and what he said was off."""
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=days))
    rows: list[dict[str, Any]] = []
    for c in ctx.store.select("cards", "status = 'skipped' AND status_changed_at >= ?", (since,),
                              order="status_changed_at DESC"):
        skip = c.get("skip") or {}
        if skip.get("reason") not in WRITING_REASONS or (platform and c["platform"] != platform):
            continue
        draft = c.get("draft") or {}
        text = draft.get("text") or "\n\n".join(draft.get("posts") or [])
        rows.append({"platform": c["platform"], "format": c.get("format"),
                     "draft": textutil.truncate(text, 400), "note": textutil.truncate(skip.get("note") or "", 300)})
        if len(rows) >= limit:
            break
    return rows


def writing_rules(ctx: Ctx, platform: str, limit: int = 4) -> list[str]:
    """His recent "not my voice" notes, as lines for the drafter's style rules (only skips that say what was off)."""
    return [f'He skipped a recent draft as not written well or not in his voice, saying: "{r["note"]}". Avoid that.'
            for r in writing_feedback(ctx, platform) if r["note"]][:limit]


def render(rows: list[dict[str, Any]]) -> str:
    """One line per item for prompts."""
    if not rows:
        return "(none yet)"
    label = {"linkedin": "LinkedIn", "x": "X"}
    lines = []
    for r in rows:
        where = f"{label[r['platform']]}, {r['pillar']}"
        if r.get("kind") == "crosspost":
            to = label.get(r.get("to") or "", "the other platform")
            line = (f'- Moved "{r["title"]}" from {label[r["platform"]]} to {to}: right topic, wrong platform'
                    if r.get("reason") == "switch" else f'- Wanted "{r["title"]}" on {to} too ({where})')
        else:
            line = f'- Skipped "{r["title"]}" ({where}): {REASON_LABEL.get(r["reason"], r["reason"] or "skipped")}'
        if r.get("note"):
            line += f' — in his words: "{r["note"]}"'
        lines.append(line)
    return "\n".join(lines)
