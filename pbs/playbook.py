"""Versioned playbook (drafting guidance) and proposals that wait for Ankit (FR-21, FR-32)."""

from __future__ import annotations

from typing import Any

from . import ids, settings, timeutil
from .context import Ctx

SEED_RULES: list[dict[str, Any]] = [
    {"text": "Lead with the most specific detail available (a named thing, a figure from the sources, a sharp "
             "contrast), not a general statement.", "platform": None},
    {"text": "One idea per post; cut anything that doesn't serve it.", "platform": None},
    {"text": "Say what changes in practice for people automating real work, not just what was announced.",
     "platform": "linkedin"},
    {"text": "Short sentences and plain words; translate any jargon.", "platform": None},
    {"text": "End on a specific takeaway or a genuine question tied to the post, never generic engagement bait.",
     "platform": "linkedin"},
    {"text": "On X, make the first line carry the whole point; no preamble.", "platform": "x"},
    {"text": "Replies add one specific thing (a detail, an implication or a precise question) and never flatter.",
     "platform": "x"},
    {"text": "Affairs posts stay neutral in framing and source every figure; opinion only where a stance is recorded.",
     "platform": "x", "pillar": "affairs"},
]


def active(ctx: Ctx) -> dict[str, Any] | None:
    rows = ctx.store.select("playbook_versions", "status = 'active'", order="version DESC", limit=1)
    return rows[0] if rows else None


def ensure_seed(ctx: Ctx) -> dict[str, Any]:
    current = active(ctx)
    if current:
        return current
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


def apply_proposal(ctx: Ctx, proposal: dict[str, Any]) -> str | None:
    """Apply an approved proposal. Returns an error message, or None on success."""
    payload = proposal.get("payload") or {}
    if payload.get("patch"):
        current = dict(ctx.store.get_setting("overrides", {}) or {})
        new, error = settings.validate_patch(current, payload["patch"])
        if error:
            return f"can't apply: {error}"
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
            return f"can't apply: {error}"
    if not (payload.get("patch") or payload.get("rule") or payload.get("source") or payload.get("guide_change")):
        return "this proposal has nothing to apply automatically; make the change in Settings"
    return None
