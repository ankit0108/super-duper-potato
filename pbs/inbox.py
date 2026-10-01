"""Ingest desk events from `inbox/` (FR-13). The desk is the only writer of inbox files; this is the only reader.

Each event is validated on its own, applied at most once (processed_events), and a bad event is recorded
as rejected with a reason the desk can show — it never blocks the rest of the batch.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from . import contracts as C
from . import draft, hashtags, ids, learn, log, playbook, settings, timeutil
from .context import Ctx


class Reject(Exception):
    """An event that is valid JSON but can't be applied (unknown card, bad transition, invalid setting)."""


def inbox_dir(ctx: Ctx) -> Path:
    return ctx.data_root / "inbox"


def _event_time(ev: Any) -> str:
    t = timeutil.parse(getattr(ev, "at", None))
    now = timeutil.now()
    if t is None or t > now:
        t = now
    return timeutil.iso(t)  # type: ignore[return-value]


def ingest(ctx: Ctx) -> dict[str, int]:
    """Apply inbox events. Files are only deleted by `cleanup()` after the store has been saved,
    so a crash mid-run never loses an event (processed_events makes re-reading harmless)."""
    folder = inbox_dir(ctx)
    stats = {"files": 0, "applied": 0, "rejected": 0, "skipped": 0}
    if not folder.is_dir():
        return stats
    for path in sorted(folder.glob("*.json")):
        stats["files"] += 1
        try:
            env = C.parse_envelope(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, ValidationError) as exc:
            _record(ctx, path.stem, None, "rejected", f"unreadable batch: {type(exc).__name__}")
            _quarantine(ctx, path)
            stats["rejected"] += 1
            continue
        for raw in env.events:
            ev_id = str(raw.get("id") or "")
            if ev_id and ctx.store.get("processed_events", ev_id):
                stats["skipped"] += 1
                continue
            ev_type = str(raw.get("type") or "unknown")
            try:
                ev = C.parse_event(raw)
            except ValidationError as exc:
                first = exc.errors()[0]
                where = ".".join(str(p) for p in first.get("loc", ())[1:]) or ev_type
                _record(ctx, ev_id or ids.new_id("evx"), ev_type, "rejected", f"{where}: {first.get('msg')}")
                stats["rejected"] += 1
                continue
            try:
                APPLY[ev.type](ctx, ev)
                _record(ctx, ev.id, ev.type, "applied", None, env.id)
                stats["applied"] += 1
            except Reject as exc:
                _record(ctx, ev.id, ev.type, "rejected", str(exc), env.id)
                stats["rejected"] += 1
            except Exception as exc:  # noqa: BLE001
                log.error(f"inbox:{ev.type}", exc)
                _record(ctx, ev.id, ev.type, "rejected", f"internal error ({type(exc).__name__})", env.id)
                stats["rejected"] += 1
        if path not in ctx.inbox_consumed:
            ctx.inbox_consumed.append(path)
    if stats["files"]:
        log.info(f"inbox: {stats['applied']} applied, {stats['rejected']} rejected, {stats['skipped']} duplicates "
                 f"from {stats['files']} files")
    return stats


def cleanup(ctx: Ctx) -> int:
    """Delete inbox files whose events are now in the saved store. The list lives on the run's context (never a
    module-level map keyed by id(ctx): ids are reused, so a later context could delete another run's files)."""
    paths, ctx.inbox_consumed = ctx.inbox_consumed, []
    for path in paths:
        path.unlink(missing_ok=True)
    return len(paths)


def _record(ctx: Ctx, ev_id: str, ev_type: str | None, status: str, error: str | None,
            batch_id: str | None = None) -> None:
    ctx.store.upsert("processed_events", {"id": ev_id, "batch_id": batch_id, "at": timeutil.now_iso(),
                                          "type": ev_type, "status": status, "error": error})


def _quarantine(ctx: Ctx, path: Path) -> None:
    dest = inbox_dir(ctx) / "rejected"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dest / path.name))


def _card(ctx: Ctx, card_id: str) -> dict[str, Any]:
    card = ctx.store.get("cards", card_id)
    if card is None:
        raise Reject(f"unknown card {card_id}")
    return card


def _touch(card: dict[str, Any], at: str, status: str | None = None) -> None:
    if status and status != card.get("status"):
        card["status"] = status
        card["status_changed_at"] = at
    card["updated_at"] = at
    card["revision"] = int(card.get("revision") or 0) + 1


# ---------------------------------------------------------------------------
# Card events
# ---------------------------------------------------------------------------


def _card_status(ctx: Ctx, ev: C.CardStatusEvent) -> None:
    card = _card(ctx, ev.card_id)
    at = _event_time(ev)
    if card["status"] in ("posted",):
        raise Reject("card is already posted")
    if ev.status == "editing":
        if card["status"] not in ("suggested", "blocked", "editing", "needs_input", "expired", "skipped"):
            raise Reject(f"can't edit a card in status {card['status']}")
        if card["status"] != "editing":
            draft.log_interaction(ctx, "picked", card, rank=card.get("rank"))
        _touch(card, at, "editing")
    else:
        if card["status"] != "editing":
            raise Reject("only an editing card can go back to suggested")
        _touch(card, at, "suggested")
    draft.save_card(ctx, card)


def _card_edit(ctx: Ctx, ev: C.CardEditEvent) -> None:
    card = _card(ctx, ev.card_id)
    at = _event_time(ev)
    if card["status"] == "posted":
        raise Reject("card is already posted")
    prev = card.get("working") or {}
    hooks = _edited_hooks(card, ev.hooks) if ev.hooks is not None else prev.get("hooks")
    tags = hashtags.clean(ev.hashtags, 15) if ev.hashtags is not None else prev.get("hashtags")
    visual = _edited_visual(card, ev.visual) if ev.visual is not None else prev.get("visual")
    card["working"] = {"text": ev.text, "posts": ev.posts, "hook_index": ev.hook_index, "hooks": hooks,
                       "hashtags": tags, "visual": visual, "updated_at": at}
    if card["status"] in ("suggested", "blocked"):
        draft.log_interaction(ctx, "picked", card, rank=card.get("rank"), via="edit")
        _touch(card, at, "editing")
    else:
        _touch(card, at)
    recent = ctx.store.select("interactions", "card_id = ? AND type = 'edited' AND at >= ?",
                              (card["id"], timeutil.iso(timeutil.now() - _minutes(30))), limit=1)
    if not recent:
        draft.log_interaction(ctx, "edited", card)
    draft.save_card(ctx, card)


def _edited_hooks(card: dict[str, Any], hooks: list[C.HookIn]) -> list[dict[str, str]] | None:
    """His openings, typed: an edit keeps the drafter's label while the text is mostly the same."""
    original = card.get("hooks") or []
    out = []
    for i, h in enumerate(hooks):
        text = h.text.strip()
        if not text:
            continue
        out.append({"type": learn.hook_type_for(original[i] if i < len(original) else None, text), "text": text})
    return out or None


def _edited_visual(card: dict[str, Any], visual: C.VisualIn) -> dict[str, Any] | None:
    """His wording of the card's visual. It belongs to the visual it was edited from (created_at), so a newer
    visual from the pipeline replaces it."""
    base = card.get("visual")
    if not base:
        return None
    return {**visual.model_dump(), "sources": base.get("sources") or [], "unsourced": base.get("unsourced") or [],
            "created_at": base.get("created_at")}


def _minutes(n: int):
    import datetime as dt

    return dt.timedelta(minutes=n)


def _card_posted(ctx: Ctx, ev: C.CardPostedEvent) -> None:
    card = _card(ctx, ev.card_id)
    at = _event_time(ev)
    posted_at = timeutil.iso(timeutil.parse(ev.posted_at)) if ev.posted_at else at
    if card["status"] == "posted" and card.get("post_id"):
        learn.update_post(ctx, card["post_id"], text=ev.text, posts=ev.posts, post_url=ev.post_url,
                          posted_at=posted_at)
        return
    learn.record_post(ctx, card, text=ev.text, posts=ev.posts, post_url=ev.post_url, posted_at=posted_at,
                      editing_seconds=ev.editing_seconds, hook_index=ev.hook_index, tags=ev.hashtags,
                      with_visual=ev.with_visual)


def _card_skip(ctx: Ctx, ev: C.CardSkipEvent) -> None:
    card = _card(ctx, ev.card_id)
    at = _event_time(ev)
    if card["status"] == "posted":
        raise Reject("card is already posted")
    note = (ev.note or "").strip() or None
    earlier = card.get("skip") if card["status"] == "skipped" else None
    if earlier:
        # He added (or changed) the reason after a one-tap skip: same skip, now with his words.
        card["skip"] = {"reason": ev.reason, "note": note or earlier.get("note"), "at": earlier.get("at") or at}
        _touch(card, at)
        draft.save_card(ctx, card)
        draft.log_interaction(ctx, "skip_reason", card, reason=ev.reason, note=note)
        return
    card["skip"] = {"reason": ev.reason, "note": note, "at": at}
    card["work"] = None
    _touch(card, at, "skipped")
    draft.save_card(ctx, card)
    draft.log_interaction(ctx, "skipped", card, reason=ev.reason, note=note, rank=card.get("rank"))


def _card_rewrite(ctx: Ctx, ev: C.CardRewriteEvent) -> None:
    card = _card(ctx, ev.card_id)
    at = _event_time(ev)
    if card["status"] == "posted" and not ev.target_platform:
        raise Reject("card is already posted")
    if ev.target_format and not ev.target_platform:
        spec = ctx.settings.pillar(card["platform"], card["pillar"])
        if spec and ev.target_format in spec.formats:
            card["format"] = ev.target_format
    card["work"] = {"kind": "rewrite", "note": ev.note, "chips": ev.chips, "requested_at": at, "attempts": 0,
                    "target_platform": ev.target_platform, "target_format": ev.target_format}
    _touch(card, at)
    draft.save_card(ctx, card)
    draft.log_interaction(ctx, "rewrite_requested", card, note=ev.note, chips=ev.chips,
                          target_platform=ev.target_platform)
    ctx.hints.add("work")


def _card_crosspost(ctx: Ctx, ev: C.CardCrosspostEvent) -> None:
    """A version for the other platform. "switch" also skips the original: the topic was right, the platform
    wasn't, which the ranking learns (skip value wrong_platform); the new card is learned from like any other."""
    card = _card(ctx, ev.card_id)
    at = _event_time(ev)
    if card["platform"] == ev.target_platform:
        raise Reject(f"the card is already for {ev.target_platform}")
    if ev.target_format and ctx.settings.formats.get(ev.target_format) and \
            ctx.settings.formats[ev.target_format].platform != ev.target_platform:
        raise Reject(f"{ev.target_format} isn't a format for {ev.target_platform}")
    mode = "both" if card["status"] == "posted" else ev.mode
    card["work"] = {"kind": "rewrite", "note": ev.note, "chips": [], "requested_at": at, "attempts": 0,
                    "target_platform": ev.target_platform, "target_format": ev.target_format, "crosspost": mode}
    if mode == "switch":
        card["skip"] = {"reason": "wrong_platform", "note": ev.note.strip() or None, "at": at}
        _touch(card, at, "skipped")
    else:
        _touch(card, at)
    draft.save_card(ctx, card)
    draft.log_interaction(ctx, "crosspost", card, mode=mode, to=ev.target_platform, format=ev.target_format,
                          pillar=card.get("pillar"), note=ev.note or None)
    ctx.hints.add("work")


def _card_visual(ctx: Ctx, ev: C.CardVisualEvent) -> None:
    """Draw a visual for the post (drafted on the next run, from the card's current text)."""
    card = _card(ctx, ev.card_id)
    if card["status"] == "posted":
        raise Reject("card is already posted")
    working = card.get("working") or {}
    if not (card.get("draft") or working.get("text") or working.get("posts")):
        raise Reject("the card has no draft to draw from yet")
    if card.get("work") and card["work"].get("kind") != "visual":
        raise Reject("the card is busy with a rewrite or draft; ask again when it's done")
    if not ctx.settings.visuals.enabled:
        raise Reject("visuals are turned off in settings")
    at = _event_time(ev)
    card["work"] = {"kind": "visual", "visual_kind": ev.kind, "note": ev.note, "requested_at": at, "attempts": 0}
    card["updated_at"] = at  # not a new version of the text: the revision stays
    draft.save_card(ctx, card)
    draft.log_interaction(ctx, "visual_requested", card, kind=ev.kind)
    ctx.hints.add("work")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")[:48] or ids.new_id("stn")


def _card_answers(ctx: Ctx, ev: C.CardAnswersEvent) -> None:
    card = _card(ctx, ev.card_id)
    at = _event_time(ev)
    known = {q["id"] for q in card.get("questions") or []}
    answers = {a["question_id"]: a for a in card.get("answers") or []}
    for a in ev.answers:
        if known and a.question_id not in known:
            raise Reject(f"unknown question {a.question_id}")
        if a.answer.strip():
            answers[a.question_id] = {"question_id": a.question_id, "answer": a.answer.strip(), "at": at}
    if not answers:
        raise Reject("no answers given")
    card["answers"] = list(answers.values())
    if ev.save_as_stance and ev.save_as_stance.text.strip():
        stance_id = ev.save_as_stance.stance_id or card.get("issue_key") or _slug(
            ev.save_as_stance.issue or card.get("title") or "stance")
        existing = ctx.store.get("stances", stance_id)
        row = existing or {"id": stance_id, "issue": ev.save_as_stance.issue or card.get("title"),
                           "tier": ev.save_as_stance.tier or "other", "positions": [], "created_by": "user",
                           "created_at": at, "keywords": []}
        row.update({"chosen": {"custom_text": ev.save_as_stance.text.strip(), "position_key": None},
                    "status": "active", "updated_at": at})
        ctx.store.upsert("stances", row)
        card["issue_key"] = stance_id
        draft.log_interaction(ctx, "stance_updated", card, stance_id=stance_id, via="answers")
    card["work"] = {"kind": "draft", "requested_at": at, "attempts": 0}
    _touch(card, at)
    draft.save_card(ctx, card)
    draft.log_interaction(ctx, "answered", card, reusable=ev.reusable, pillar=card.get("pillar"),
                          answers=[a["answer"] for a in card["answers"]])
    ctx.hints.add("work")


def _card_restore(ctx: Ctx, ev: C.CardRestoreEvent) -> None:
    card = _card(ctx, ev.card_id)
    at = _event_time(ev)
    if card["status"] not in ("skipped", "expired", "blocked", "failed"):
        raise Reject(f"can't restore a card in status {card['status']}")
    if card.get("mode") == "interview" and not card.get("draft"):
        status = "needs_input"
    else:
        status = "editing"
    card["skip"] = None
    card["expires_at"] = timeutil.iso(timeutil.now() + _minutes(24 * 60))
    _touch(card, at, status)
    draft.save_card(ctx, card)
    draft.log_interaction(ctx, "restored", card)


def _card_draft_now(ctx: Ctx, ev: C.CardDraftNowEvent) -> None:
    card = _card(ctx, ev.card_id)
    at = _event_time(ev)
    if card["status"] == "posted":
        raise Reject("card is already posted")
    card["work"] = {"kind": "draft", "requested_at": at, "attempts": 0}
    if card["status"] in ("failed",):
        card["status"] = "drafting"
    _touch(card, at)
    draft.save_card(ctx, card)
    ctx.hints.add("work")


def _card_hook(ctx: Ctx, ev: C.CardHookEvent) -> None:
    card = _card(ctx, ev.card_id)
    original = card.get("hooks") or []
    hooks = learn.card_hooks(card)
    text = (ev.text or "").strip()
    if text:
        # An opening he edited or wrote himself (the desk sends its text, so it needn't be synced yet).
        known = original[ev.hook_index] if ev.hook_index < len(original) else None
        hook_type = learn.hook_type_for(known, text)
        edited = known is None or text != (known.get("text") or "").strip()
    elif ev.hook_index < len(hooks):
        hook_type, edited = hooks[ev.hook_index].get("type") or "observation", False
    else:
        raise Reject("unknown hook")
    draft.log_interaction(ctx, "hook_swapped", card, hook_index=ev.hook_index, hook_type=hook_type, edited=edited)


# ---------------------------------------------------------------------------
# Posts and metrics
# ---------------------------------------------------------------------------


def _post_update(ctx: Ctx, ev: C.PostUpdateEvent) -> None:
    if not ctx.store.get("posts", ev.post_id):
        raise Reject(f"unknown post {ev.post_id}")
    learn.update_post(ctx, ev.post_id, text=ev.text, posts=ev.posts, post_url=ev.post_url,
                      posted_at=timeutil.iso(timeutil.parse(ev.posted_at)) if ev.posted_at else None)


def _post_metrics(ctx: Ctx, ev: C.PostMetricsEvent) -> None:
    post = ctx.store.get("posts", ev.post_id)
    if post is None:
        raise Reject(f"unknown post {ev.post_id}")
    values = ev.values.model_dump(exclude_none=True)
    if not values:
        raise Reject("no metric values given")
    ctx.store.insert("metrics", {
        "id": ids.new_id("met"), "post_id": post["id"], "platform": post["platform"],
        "captured_at": timeutil.iso(timeutil.parse(ev.captured_at)) if ev.captured_at else _event_time(ev),
        **values, "source": "manual", "status": "confirmed", "created_at": timeutil.now_iso(),
    })
    draft.log_interaction(ctx, "metrics_added", None, post_id=post["id"], platform=post["platform"], source="manual")
    ctx.hints.add("rewards")


def _metrics_upload(ctx: Ctx, ev: C.MetricsUploadEvent) -> None:
    for p in ev.paths:
        if not p.startswith("inbox/blobs/") or ".." in p:
            raise Reject("uploads must live under inbox/blobs/")
    ctx.store.upsert("metric_uploads", {"id": ev.upload_id, "paths": ev.paths, "week": ev.week, "note": ev.note,
                                        "status": "pending", "created_at": _event_time(ev)})
    ctx.hints.add("metrics")


def _metrics_review(ctx: Ctx, ev: C.MetricsReviewEvent) -> None:
    row = ctx.store.get("metrics", ev.metric_id)
    if row is None:
        raise Reject(f"unknown metric {ev.metric_id}")
    patch: dict[str, Any] = {}
    if ev.action == "reject":
        patch["status"] = "rejected"
    else:
        patch["status"] = "confirmed"
        if ev.post_id:
            post = ctx.store.get("posts", ev.post_id)
            if post is None:
                raise Reject(f"unknown post {ev.post_id}")
            patch["post_id"] = post["id"]
            patch["platform"] = post["platform"]
        if ev.action == "edit" and ev.values:
            patch.update(ev.values.model_dump(exclude_none=True))
        if not (patch.get("post_id") or row.get("post_id")):
            raise Reject("choose which post these numbers belong to")
    ctx.store.update("metrics", ev.metric_id, **patch)
    ctx.hints.add("rewards")


def _account_stats(ctx: Ctx, ev: C.AccountStatsEvent) -> None:
    date = (timeutil.parse(ev.date) or timeutil.now()).strftime("%Y-%m-%d")
    ctx.store.upsert("account_stats", {"id": f"acs_{ev.platform}_{date}", "date": date, "platform": ev.platform,
                                       "followers": ev.followers, "profile_views": ev.profile_views,
                                       "source": "manual", "created_at": timeutil.now_iso()})


# ---------------------------------------------------------------------------
# Requests, stances, sources
# ---------------------------------------------------------------------------


def _request_create(ctx: Ctx, ev: C.RequestCreateEvent) -> None:
    if ctx.store.get("requests", ev.request_id):
        return
    platforms = {k: int(v) for k, v in ev.platforms.items() if v}
    if not platforms:
        raise Reject("choose at least one platform")
    ctx.store.insert("requests", {"id": ev.request_id, "query": ev.query.strip(), "platforms": platforms,
                                  "notes": ev.notes, "status": "queued", "created_at": _event_time(ev),
                                  "attempts": 0, "card_ids": []})
    draft.log_interaction(ctx, "request_created", None, request_id=ev.request_id, query=ev.query)
    ctx.hints.add("requests")


def _request_cancel(ctx: Ctx, ev: C.RequestCancelEvent) -> None:
    row = ctx.store.get("requests", ev.request_id)
    if row is None:
        raise Reject(f"unknown request {ev.request_id}")
    if row["status"] in ("queued", "running", "failed"):
        ctx.store.update("requests", ev.request_id, status="cancelled")


def _stance_upsert(ctx: Ctx, ev: C.StanceUpsertEvent) -> None:
    at = _event_time(ev)
    row = ctx.store.get("stances", ev.stance_id)
    if row is None:
        if not ev.issue:
            raise Reject("a new stance needs an issue")
        row = {"id": ev.stance_id, "issue": ev.issue, "tier": ev.tier or "other", "positions": [],
               "status": "active", "created_by": "user", "created_at": at, "keywords": []}
    for field in ("issue", "tier", "context", "keywords", "status"):
        value = getattr(ev, field)
        if value is not None:
            row[field] = value
    if ev.positions is not None:
        row["positions"] = [p.model_dump() for p in ev.positions]
    if ev.clear_choice:
        row["chosen"] = None
    elif ev.chosen_key is not None or ev.custom_text is not None:
        keys = {p["key"] for p in row.get("positions") or []}
        if ev.chosen_key and ev.chosen_key not in keys:
            raise Reject(f"unknown position {ev.chosen_key}")
        row["chosen"] = {"position_key": ev.chosen_key or None, "custom_text": (ev.custom_text or "").strip() or None}
        if row.get("status") == "proposed":
            row["status"] = "active"
    row["updated_at"] = at
    ctx.store.upsert("stances", row)
    draft.log_interaction(ctx, "stance_updated", None, stance_id=ev.stance_id)


def _stance_delete(ctx: Ctx, ev: C.StanceDeleteEvent) -> None:
    if ctx.store.get("stances", ev.stance_id) is None:
        raise Reject(f"unknown stance {ev.stance_id}")
    ctx.store.update("stances", ev.stance_id, status="archived", updated_at=_event_time(ev))


def _stance_propose(ctx: Ctx, ev: C.StanceProposeEvent) -> None:
    ctx.hints.add("stances")
    ctx.store.set_setting("stance_proposals_wanted", ev.count)


def _source_upsert(ctx: Ctx, ev: C.SourceUpsertEvent) -> None:
    at = _event_time(ev)
    row = ctx.store.get("sources", ev.source_id)
    new = row is None
    if new:
        if not (ev.kind and ev.scout and ev.name):
            raise Reject("a new source needs a name, kind and scout")
        row = {"id": ev.source_id, "added_by": "user", "created_at": at, "consecutive_failures": 0, "items_total": 0,
               "active": True, "lang": "en", "best_effort": False}
    for field in ("name", "kind", "url", "query", "scout", "tier", "lang", "active", "pillar_hints"):
        value = getattr(ev, field)
        if value is not None:
            row[field] = value
    kind = row.get("kind")
    if kind in ("rss", "reddit") and not str(row.get("url") or "").startswith(("http://", "https://")):
        raise Reject("an RSS source needs an http(s) URL")
    if kind == "gnews" and not (row.get("query") or (row.get("extra") or {}).get("topic")):
        raise Reject("a Google News source needs a query")
    if ev.active:
        row["paused_reason"] = None
        row["consecutive_failures"] = 0
    if not new and row.get("added_by") == "seed":
        row["extra"] = {**(row.get("extra") or {}), "user_edited": True}
    row["updated_at"] = at
    ctx.store.upsert("sources", row)


def _source_delete(ctx: Ctx, ev: C.SourceDeleteEvent) -> None:
    row = ctx.store.get("sources", ev.source_id)
    if row is None:
        raise Reject(f"unknown source {ev.source_id}")
    if row.get("added_by") == "seed":
        deleted = list(ctx.store.get_setting("deleted_sources", []) or [])
        if ev.source_id not in deleted:
            deleted.append(ev.source_id)
        ctx.store.set_setting("deleted_sources", deleted)
    ctx.store.delete("sources", ev.source_id)


# ---------------------------------------------------------------------------
# Settings, profile, proposals, playbook, runs
# ---------------------------------------------------------------------------


def _settings_update(ctx: Ctx, ev: C.SettingsUpdateEvent) -> None:
    current = dict(ctx.store.get_setting("overrides", {}) or {})
    if "profile" in ev.patch:
        raise Reject("edit the profile on the Profile page")
    new, error = settings.validate_patch(current, ev.patch)
    if error:
        raise Reject(error)
    ctx.store.set_setting("overrides", _prune_nulls(new))
    ctx.reload_settings()
    draft.log_interaction(ctx, "settings_changed", None, keys=sorted(_leaf_paths(ev.patch)))


def _prune_nulls(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            v = _prune_nulls(v)
            if v:
                out[k] = v
        elif v is not None:
            out[k] = v
    return out


def _leaf_paths(d: dict[str, Any], prefix: str = "") -> list[str]:
    out = []
    for k, v in d.items():
        path = f"{prefix}.{k}" if prefix else k
        out.extend(_leaf_paths(v, path) if isinstance(v, dict) and v else [path])
    return out


def _profile_update(ctx: Ctx, ev: C.ProfileUpdateEvent) -> None:
    ctx.store.set_setting("profile", ev.text.strip())
    ctx.reload_settings()
    draft.log_interaction(ctx, "profile_updated", None)


def _proposal_decide(ctx: Ctx, ev: C.ProposalDecideEvent) -> None:
    row = ctx.store.get("proposals", ev.proposal_id)
    if row is None:
        raise Reject(f"unknown proposal {ev.proposal_id}")
    if row["status"] != "pending":
        raise Reject(f"proposal is already {row['status']}")
    at = _event_time(ev)
    if ev.decision == "reject":
        ctx.store.update("proposals", row["id"], status="rejected", decided_at=at, decision_note=ev.note)
        return
    error = playbook.apply_proposal(ctx, row)
    if error:
        raise Reject(error)
    ctx.store.update("proposals", row["id"], status="applied", decided_at=at, decision_note=ev.note)


def _playbook_rule(ctx: Ctx, ev: C.PlaybookRuleEvent) -> None:
    error = playbook.user_rule(ctx, ev.action, rule_id=ev.rule_id, text=ev.text, platform=ev.platform,
                               pillar=ev.pillar)
    if error:
        raise Reject(error)


def _run_request(ctx: Ctx, ev: C.RunRequestEvent) -> None:
    ctx.hints.update(ev.tasks)
    if ev.force:
        ctx.force = True
    if "morning" in ev.tasks and ev.force:
        # "Get fresh posts": a new set now. When he asks (hour, platforms, how many) is a signal of its own.
        ctx.fresh = {"platforms": list(ev.platforms or []) or None, "per_platform": ev.per_platform,
                     "find_sources": ev.find_sources}
        draft.log_interaction(ctx, "fresh_requested", None, platforms=ctx.fresh["platforms"],
                              per_platform=ev.per_platform, find_sources=ev.find_sources,
                              local_hour=ctx.local_now().hour)


APPLY = {
    "card.status": _card_status,
    "card.edit": _card_edit,
    "card.posted": _card_posted,
    "card.skip": _card_skip,
    "card.rewrite": _card_rewrite,
    "card.crosspost": _card_crosspost,
    "card.visual": _card_visual,
    "card.answers": _card_answers,
    "card.restore": _card_restore,
    "card.draft_now": _card_draft_now,
    "card.hook": _card_hook,
    "post.update": _post_update,
    "post.metrics": _post_metrics,
    "metrics.upload": _metrics_upload,
    "metrics.review": _metrics_review,
    "account.stats": _account_stats,
    "request.create": _request_create,
    "request.cancel": _request_cancel,
    "stance.upsert": _stance_upsert,
    "stance.delete": _stance_delete,
    "stance.propose": _stance_propose,
    "source.upsert": _source_upsert,
    "source.delete": _source_delete,
    "settings.update": _settings_update,
    "profile.update": _profile_update,
    "proposal.decide": _proposal_decide,
    "playbook.rule": _playbook_rule,
    "run.request": _run_request,
}
