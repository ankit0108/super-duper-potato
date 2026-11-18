"""Versioned playbook (drafting guidance) and proposals that wait for Ankit (FR-21, FR-32)."""

from __future__ import annotations

from typing import Any

from . import ids, settings, timeutil
from .context import Ctx

SEED_RULES: list[dict[str, Any]] = [
    {"text": "Lead with the most specific detail available (a named thing, a figure from the sources, a sharp "
             "contrast), not a general statement.", "platform": None},
    {"text": "One idea per post; cut anything that doesn't serve it.", "platform": None},
    {"text": "Say what changes in practice, and for whom, not just what was announced.", "platform": "linkedin"},
    {"text": "Short sentences and plain words; translate any jargon.", "platform": None},
    {"text": "End on a specific takeaway or a genuine question tied to the post, never generic engagement bait.",
     "platform": "linkedin"},
    {"text": "On X, make the first line carry the whole point; no preamble.", "platform": "x"},
    {"text": "Replies add one specific thing (a detail, an implication or a precise question) and never flatter.",
     "platform": "x"},
    {"text": "Affairs posts stay neutral in framing and source every figure; opinion only where a stance is recorded.",
     "platform": "x", "pillar": "affairs"},
]


# Starting rules reworded since they were seeded: old text -> new. A playbook that still has the old wording from
# the seed gets the new one (a rule the reflection or Ankit rewrote is left alone).
UPDATED_SEED_RULES = {
    "Say what changes in practice for people automating real work, not just what was announced.":
        "Say what changes in practice, and for whom, not just what was announced.",
}


# Rules added to an existing playbook once, when the evidence for them arrived. Each has a key; once added (or
# found already there) it's never added again, so a rule he removes stays removed.
ADDED_RULES: dict[str, dict[str, Any]] = {
    # His first LinkedIn export (Oct 2026): news about the big AI labs got the most views; the one post that
    # opened with a number and his own take got almost a quarter of the month's engagement.
    "2026-11-linkedin-news-openings": {
        "text": "On LinkedIn news posts, open with the most specific number in the material or his own sharp claim "
                "about it, then the news; never with \"X announced Y\". End on what it means for the people "
                "building and running AI and automation.",
        "platform": "linkedin",
        "reversal": "News posts that open this way don't get more engagement than his other news posts.",
        "summary": "From your LinkedIn analytics: news gets the views, a number and your take get the engagement.",
    },
}
ADDITIONS_KEY = "playbook_additions"


def ensure_additions(ctx: Ctx) -> dict[str, Any] | None:
    """Add the rules in ADDED_RULES not yet added (each once). Returns the new version, if any."""
    done = list(ctx.store.get_setting(ADDITIONS_KEY, []) or [])
    todo = [k for k in ADDED_RULES if k not in done]
    if not todo:
        return None
    version = None
    for key in todo:
        spec = ADDED_RULES[key]
        version = apply_changes(ctx, [{"op": "add", "text": spec["text"], "platform": spec.get("platform"),
                                       "pillar": spec.get("pillar"), "confidence": "high",
                                       "reversal": spec.get("reversal")}],
                                source="analytics", summary=spec.get("summary")) or version
    ctx.store.set_setting(ADDITIONS_KEY, sorted({*done, *todo}))
    return version


def active(ctx: Ctx) -> dict[str, Any] | None:
    rows = ctx.store.select("playbook_versions", "status = 'active'", order="version DESC", limit=1)
    return rows[0] if rows else None


def _update_seed_rules(ctx: Ctx, current: dict[str, Any]) -> dict[str, Any]:
    rules = [dict(r) for r in current.get("rules") or []]
    changes = []
    for r in rules:
        new = UPDATED_SEED_RULES.get(r.get("text") or "")
        if new and r.get("source") == "seed":
            r["text"] = new
            changes.append({"op": "modify", "rule_id": r["id"], "text": new})
    if not changes:
        return current
    return new_version(ctx, rules, changes, source="seed",
                       summary="Starting guidance updated: takes fit each story, not always automation.")


def ensure_seed(ctx: Ctx) -> dict[str, Any]:
    current = active(ctx)
    if current:
        return _update_seed_rules(ctx, current)
    rules = [{"id": f"r{i}", "text": r["text"], "platform": r.get("platform"), "pillar": r.get("pillar"),
              "confidence": "medium", "evidence": [], "reversal": None, "source": "seed", "added_in": "v1"}
             for i, r in enumerate(SEED_RULES, 1)]
    return new_version(ctx, rules, [{"op": "seed", "count": len(rules)}], source="seed",
                       summary="Starting playbook: general guidance until the system learns from your edits.")


def new_version(ctx: Ctx, rules: list[dict[str, Any]], changes: list[dict[str, Any]], source: str,
                summary: str | None = None, experiments: list[str] | None = None) -> dict[str, Any]:
    prev = active(ctx)
    version = int(prev["version"]) + 1 if prev else 1
    if prev:
        ctx.store.update("playbook_versions", prev["id"], status="retired")
    row = {"id": f"pb_v{version:03d}", "version": version, "created_at": timeutil.now_iso(), "status": "active",
           "rules": rules, "changes": changes, "experiments": experiments or [], "summary": summary,
           "source": source}
    ctx.store.upsert("playbook_versions", row)
    return row


def _next_rule_id(rules: list[dict[str, Any]]) -> str:
    nums = [int(r["id"][1:]) for r in rules if str(r.get("id", "")).startswith("r") and r["id"][1:].isdigit()]
    return f"r{(max(nums) if nums else 0) + 1}"


def apply_changes(ctx: Ctx, changes: list[dict[str, Any]], source: str, summary: str | None) -> dict[str, Any] | None:
    """Apply add/remove/modify rule changes as a new version. Returns the version, or None if nothing changed."""
    current = ensure_seed(ctx)
    rules = [dict(r) for r in current.get("rules") or []]
    applied: list[dict[str, Any]] = []
    version_tag = f"v{int(current['version']) + 1}"
    for ch in changes:
        op = ch.get("op")
        if op == "add" and (ch.get("text") or "").strip():
            text = ch["text"].strip()
            if any(r["text"].casefold() == text.casefold() for r in rules):
                continue
            rule = {"id": _next_rule_id(rules), "text": text[:600], "platform": ch.get("platform"),
                    "pillar": ch.get("pillar"), "confidence": ch.get("confidence", "medium"),
                    "evidence": list(ch.get("evidence") or [])[:10], "reversal": ch.get("reversal"),
                    "source": source, "added_in": version_tag}
            rules.append(rule)
            applied.append({**ch, "rule_id": rule["id"]})
        elif op == "remove" and ch.get("rule_id"):
            before = len(rules)
            rules = [r for r in rules if r["id"] != ch["rule_id"]]
            if len(rules) != before:
                applied.append(ch)
        elif op == "modify" and ch.get("rule_id") and (ch.get("text") or "").strip():
            for r in rules:
                if r["id"] == ch["rule_id"]:
                    r.update(text=ch["text"].strip()[:600], confidence=ch.get("confidence", r.get("confidence")),
                             evidence=list(ch.get("evidence") or r.get("evidence") or [])[:10],
                             reversal=ch.get("reversal") or r.get("reversal"), added_in=version_tag,
                             source=source)
                    applied.append(ch)
    if not applied:
        return None
    return new_version(ctx, rules, applied, source=source, summary=summary)


def user_rule(ctx: Ctx, action: str, *, rule_id: str | None, text: str | None, platform: str | None,
              pillar: str | None) -> str | None:
    if action in ("remove", "edit") and not rule_id:
        return "rule_id is required"
    if action in ("add", "edit") and not (text or "").strip():
        return "rule text is required"
    current = ensure_seed(ctx)
    if rule_id and action in ("remove", "edit") and not any(r["id"] == rule_id for r in current.get("rules") or []):
        return f"unknown rule {rule_id}"
    op = {"add": "add", "remove": "remove", "edit": "modify"}[action]
    result = apply_changes(ctx, [{"op": op, "rule_id": rule_id, "text": text, "platform": platform, "pillar": pillar,
                                  "confidence": "high"}], source="user", summary="Edited by Ankit")
    return None if result else "nothing changed"


def create_proposal(ctx: Ctx, *, kind: str, title: str, detail: str | None, payload: dict[str, Any],
                    evidence: list[str] | None = None, confidence: str = "medium", source: str = "reflection") -> str:
    pid = ids.new_id("prp")
    ctx.store.insert("proposals", {"id": pid, "kind": kind, "title": title[:200], "detail": detail,
                                   "payload": payload, "evidence": evidence or [], "confidence": confidence,
                                   "status": "pending", "created_at": timeutil.now_iso(), "source": source})
    return pid


CHANGE_KEYS = ("patch", "rule", "source", "guide_change", "revert_playbook", "review")


def has_change(proposal: dict[str, Any]) -> bool:
    """Whether approving the proposal changes something by itself (a setting, a rule, a source, the guide, or undoing
    a playbook change)."""
    payload = proposal.get("payload") or {}
    return any(payload.get(k) for k in CHANGE_KEYS)


def undo_changes(ctx: Ctx, version_id: str) -> list[dict[str, Any]]:
    """The rule changes that undo a playbook version's changes: an added rule is removed, a changed one gets its
    earlier text back, a removed one comes back. Only what is still as that version left it."""
    version = ctx.store.get("playbook_versions", version_id)
    if not version:
        return []
    before = {r["id"]: r for r in (ctx.store.get("playbook_versions", f"pb_v{int(version['version']) - 1:03d}")
                                   or {}).get("rules") or []}
    now = {r["id"]: r for r in (active(ctx) or {}).get("rules") or []}
    undo: list[dict[str, Any]] = []
    for ch in version.get("changes") or []:
        rid = ch.get("rule_id")
        if ch.get("op") == "add" and rid in now:
            undo.append({"op": "remove", "rule_id": rid})
        elif ch.get("op") == "modify" and rid in now and rid in before and now[rid]["text"] == (ch.get("text") or "").strip():
            undo.append({"op": "modify", "rule_id": rid, "text": before[rid]["text"],
                         "confidence": before[rid].get("confidence", "medium")})
        elif ch.get("op") == "remove" and rid in before and rid not in now:
            old = before[rid]
            undo.append({"op": "add", "text": old["text"], "platform": old.get("platform"),
                         "pillar": old.get("pillar"), "confidence": old.get("confidence", "medium")})
    return undo


# Proposals that can't do what they said: closed once, so "Waiting for you" only holds what approving changes.
TIDY_KEY = "proposals_cleanup_2026_11_v1"


def tidy_proposals(ctx: Ctx) -> int:
    """Close proposals that approving can't act on: a failed one whose setting change isn't valid (trying again
    fails the same way) and a pending one that only asked him to look at something. Runs once. Returns how many."""
    if ctx.store.get_setting(TIDY_KEY):
        return 0
    now = timeutil.now_iso()
    closed = 0
    overrides = dict(ctx.store.get_setting("overrides", {}) or {})
    for p in ctx.store.select("proposals", "status IN ('pending', 'failed')"):
        payload = p.get("payload") or {}
        if p["status"] == "failed" and payload.get("patch"):
            _, error = settings.validate_patch(overrides, payload["patch"])
            if not error:
                continue  # it can be applied now: leave it for him
            ctx.store.update("proposals", p["id"], status="expired", decided_at=now,
                             error="The change it asked for isn't a valid setting, so it can't be applied.")
            closed += 1
        elif p["status"] == "pending" and not has_change(p):
            ctx.store.update("proposals", p["id"], status="expired", decided_at=now,
                             error="It only asked you to look at something; that advice is in the weekly review now.")
            closed += 1
    ctx.store.set_setting(TIDY_KEY, True)
    return closed


def apply_proposal(ctx: Ctx, proposal: dict[str, Any],
                   choices: dict[str, str] | None = None) -> tuple[str, str | None]:
    """Apply an approved proposal. Returns (status, reason): ("applied", None); ("noted", None) for one that only
    asked him to look at something; or ("failed", why) when its change can't be made. `choices`: his Keep or Remove
    for each source a source review listed (one he didn't mark is kept)."""
    payload = proposal.get("payload") or {}
    if not has_change(proposal):
        return "noted", None
    if payload.get("review"):
        from .report import KEPT_KEY
        from .scout.sources import delete_source

        kept = dict(ctx.store.get_setting(KEPT_KEY, {}) or {})
        today = ctx.local_date_str()
        for row in payload["review"]:
            if (choices or {}).get(row["id"]) == "remove":
                delete_source(ctx.store, row["id"])
                kept.pop(row["id"], None)
            elif ctx.store.get("sources", row["id"]):
                kept[row["id"]] = {"on": today, "failing": bool(row.get("failing"))}
        ctx.store.set_setting(KEPT_KEY, kept)
    if payload.get("patch"):
        current = dict(ctx.store.get_setting("overrides", {}) or {})
        new, error = settings.validate_patch(current, payload["patch"])
        if error:
            return "failed", f"the setting change isn't valid ({error})"
        ctx.store.set_setting("overrides", new)
        ctx.reload_settings()
    if payload.get("rule"):
        rule = payload["rule"]
        apply_changes(ctx, [{"op": "add", **rule, "confidence": rule.get("confidence", "medium")}], source="reflection",
                      summary=f"Approved: {proposal.get('title')}")
    if payload.get("source"):
        src = payload["source"]
        if not ctx.store.get("sources", src.get("id", "")):
            now = timeutil.now_iso()
            ctx.store.upsert("sources", {**src, "added_by": "system", "active": True, "created_at": now,
                                         "updated_at": now, "consecutive_failures": 0, "items_total": 0})
    if payload.get("guide_change"):
        from . import platform

        error = platform.apply_update(ctx, payload["guide_change"])
        if error:
            return "failed", error
    if payload.get("revert_playbook"):
        undo = undo_changes(ctx, payload["revert_playbook"])
        if not undo:
            return "failed", "those playbook changes were already changed or undone"
        apply_changes(ctx, undo, source="user", summary=f"Undone at your request: {proposal.get('title')}")
    return "applied", None
