"""Ankit's explicit feedback on suggestions: why he skipped them.

It reaches the ranking the next morning (triage reads it), the weekly reflection (which reads skips with their
notes), and the desk (Insights shows what the system is learning from), so a reason is never just stored.
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
}
# Reasons that say something about the topic itself; "wrong timing" and "already covered" don't.
TOPIC_REASONS = ("not_interesting", "off_brand", "too_risky", "other")


def recent_feedback(ctx: Ctx, days: int = 21, limit: int = 12, notes_first: bool = False) -> list[dict[str, Any]]:
    """Newest first. With `notes_first`, skips that carry his own words come before the rest."""
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=days))
    rows: list[dict[str, Any]] = []
    for c in ctx.store.select("cards", "status = 'skipped' AND status_changed_at >= ?", (since,)):
        skip = c.get("skip") or {}
        reason = skip.get("reason")
        note = (skip.get("note") or "").strip()
        if reason not in TOPIC_REASONS and not note:
            continue
        rows.append({"at": skip.get("at") or c.get("status_changed_at"), "kind": "skip", "card_id": c["id"],
                     "title": textutil.truncate(c.get("title"), 120), "platform": c["platform"],
                     "pillar": c["pillar"], "reason": reason, "note": textutil.truncate(note, 300) or None})
    rows.sort(key=lambda r: r["at"] or "", reverse=True)
    if notes_first:
        rows.sort(key=lambda r: 0 if r["note"] else 1)
    return rows[:limit]


def render(rows: list[dict[str, Any]]) -> str:
    """One line per item for prompts."""
    if not rows:
        return "(none yet)"
    lines = []
    for r in rows:
        where = f"{'LinkedIn' if r['platform'] == 'linkedin' else 'X'}, {r['pillar']}"
        line = f'- Skipped "{r["title"]}" ({where}): {REASON_LABEL.get(r["reason"], r["reason"] or "skipped")}'
        if r.get("note"):
            line += f' — in his words: "{r["note"]}"'
        lines.append(line)
    return "\n".join(lines)
