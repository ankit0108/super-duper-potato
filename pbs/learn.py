"""Learning from use and results: posts, edit ratios, hooks kept, features, rewards, expiry (FR-18/19/21)."""

from __future__ import annotations

import datetime as dt
import difflib
import re
import statistics
from typing import Any

from . import draft, guardrails, hashtags, ids, images, log, textutil, timeutil
from .context import Ctx

# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------


def _draft_text(d: dict[str, Any] | None) -> str:
    if not d:
        return ""
    posts = d.get("posts") or []
    return "\n\n".join(posts) if posts else (d.get("text") or "")


def classify_opening(opening: str) -> str:
    o = opening.strip()
    low = o.casefold()
    if o.endswith("?"):
        return "question"
    if re.search(r"\d", o[:60]):
        return "number"
    if re.match(r"^(how|here's how|here is how|\d+ ways)", low):
        return "how-to"
    if re.match(r"^(i |i'|last |when i|yesterday|this week|years ago|my )", low):
        return "story"
    if re.search(r"\b(not|wrong|myth|stop|overrated|nobody|unpopular)\b", low):
        return "contrarian"
    return "observation"


def hook_type_for(original: dict[str, Any] | None, text: str) -> str:
    """The type of an opening he edited or wrote: the drafter's label while the text is mostly the same."""
    if original and original.get("text"):
        if text.strip() == original["text"].strip():
            return original.get("type") or "observation"
        sim = difflib.SequenceMatcher(a=original["text"].casefold(), b=text.casefold(), autojunk=False).ratio()
        if sim >= 0.6:
            return original.get("type") or "observation"
    return classify_opening(text)


def card_hooks(card: dict[str, Any]) -> list[dict[str, Any]]:
    """The openings as he last saw them: his edited list when he changed any, otherwise the drafter's."""
    return (card.get("working") or {}).get("hooks") or card.get("hooks") or []


def detect_hook(card: dict[str, Any], final_text: str, hook_index: int | None) -> dict[str, Any]:
    hooks = card_hooks(card)
    if hook_index is not None and 0 <= hook_index < len(hooks):
        return {"index": hook_index, "type": hooks[hook_index]["type"], "method": "explicit", "similarity": 1.0}
    opening = textutil.opening(final_text).casefold()
    options: list[tuple[int | None, str, str]] = []
    draft_open = textutil.opening(_draft_text(card.get("draft")))
    if draft_open:
        options.append((None, card.get("hook_type") or classify_opening(draft_open), draft_open))
    options += [(i, h.get("type", "observation"), h.get("text", "")) for i, h in enumerate(hooks)]
    best = (None, None, 0.0)
    for idx, typ, text in options:
        sim = difflib.SequenceMatcher(a=opening, b=text.casefold(), autojunk=False).ratio()
        if sim > best[2]:
            best = (idx, typ, sim)
    if best[2] >= 0.6:
        return {"index": best[0], "type": best[1], "method": "match" if best[0] is not None else "draft",
                "similarity": round(best[2], 3)}
    return {"index": None, "type": classify_opening(textutil.opening(final_text)), "method": "rewritten",
            "similarity": round(best[2], 3)}


def length_band(platform: str, fmt: str, final_text: str, final_posts: list[str]) -> str:
    if fmt == "x_thread":
        n = len(final_posts)
        return "short" if n <= 3 else ("medium" if n <= 5 else "long")
    n = len(final_text)
    if platform == "linkedin":
        return "short" if n < 600 else ("medium" if n < 1300 else "long")
    return "short" if n <= 140 else "long"


def posted_body(fmt: str, final_text: str, final_posts: list[str]) -> tuple[str, list[str]]:
    """What he posted without the hashtags added at the end: the part comparable with the draft."""
    if fmt == "x_thread" and final_posts:
        body_posts, tags = hashtags.strip_from_posts(final_posts)
        return "\n\n".join(body_posts), tags
    return hashtags.split_trailing(final_text)


def record_post(ctx: Ctx, card: dict[str, Any], *, text: str | None, posts: list[str] | None, post_url: str | None,
                posted_at: str, editing_seconds: int | None, hook_index: int | None,
                tags: list[str] | None = None, with_visual: bool | None = None) -> dict[str, Any]:
    working = card.get("working") or {}
    system_draft = card.get("draft") or {}
    if card["format"] == "x_thread":
        final_posts = [p.strip() for p in (posts or working.get("posts") or system_draft.get("posts") or [])
                       if p and p.strip()]
        final_text = "\n\n".join(final_posts) if final_posts else (text or working.get("text") or "")
    else:
        final_posts = []
        final_text = (text if text is not None else working.get("text")) or system_draft.get("text") or ""
    if hook_index is None and working.get("hook_index") is not None:
        hook_index = working.get("hook_index")
    body, found = posted_body(card["format"], final_text, final_posts)
    # The tags that went out are the ones at the end of what he posted (the desk adds the chosen ones there, and
    # he may still delete them before posting). The event's list only counts when the text itself wasn't sent.
    sent = text is not None or posts is not None
    used = hashtags.clean(found if sent or tags is None else tags, 15)
    offered = list(card.get("hashtags") or [])
    base = _draft_text(system_draft)
    # Tags are chosen on the card, not edited into the text: compare the draft with the body alone.
    ratio = textutil.edit_ratio(base, body) if base else None
    changes = textutil.edit_changes(base, body) if base else {"removed": [], "added": []}
    hook_used = detect_hook(card, final_text, hook_index)
    local_posted = timeutil.local(timeutil.parse(posted_at), ctx.tz)  # type: ignore[arg-type]
    delivered = timeutil.parse(card.get("delivered_at") or card.get("created_at"))
    ttp = timeutil.hours_between(delivered, timeutil.parse(posted_at))
    topic = ctx.store.get("topics", card["topic_id"]) if card.get("topic_id") else None
    features = {
        "platform": card["platform"],
        "pillar": card["pillar"],
        "format": card["format"],
        "hook_type": hook_used["type"],
        "source_type": card.get("kind") if card.get("kind") in ("request", "interview", "evergreen", "adapt")
        else (topic or {}).get("scout") or "news",
        "mode": card.get("mode"),
        "draft_basis": card.get("draft_basis"),
        "affairs_type": card.get("affairs_type"),
        "length_band": length_band(card["platform"], card["format"], final_text, final_posts),
        "weekday": local_posted.strftime("%a"),
        "hour": local_posted.hour,
        "explore": bool(card.get("explore")),
        "experiment_id": card.get("experiment_id"),
        "rank": card.get("rank"),
        "versions": card.get("versions") or {},
        "rewrites": int(card.get("rewrite_count") or 0),
        "hashtags_offered": offered,
        "hashtags_used": len(used),
        "crosspost": bool(card.get("crosspost_of")),
        # The kind of visual that went out with it (he says so when marking it posted), or None.
        "visual": ((working.get("visual") or card.get("visual") or {}).get("kind") if with_visual else None),
    }
    guard = guardrails.check_final(final_text, ctx.blocklist)
    if guard["blocked"]:
        ctx.run.note(f"Posted text for card {card['id']} contains a blocklist term — check the live post")
    now = timeutil.now_iso()
    post = {
        "id": ids.new_id("pst"),
        "card_id": card["id"],
        "platform": card["platform"],
        "pillar": card["pillar"],
        "format": card["format"],
        "final_text": final_text,
        "final_posts": final_posts,
        "hashtags": used,
        "posted_at": posted_at,
        "post_url": (post_url or "").strip() or None,
        "edit_ratio": ratio,
        "edit_stats": {
            "draft_words": textutil.word_count(base), "final_words": textutil.word_count(body),
            "draft_chars": len(base), "final_chars": len(body),
            "removed": [p for p in changes["removed"] if len(p) < 200][:30],
            "added": [p for p in changes["added"] if len(p) < 200][:30],
            # What read as AI-written in the draft as shown, and in what went out (voice learning, stats).
            "tells_draft": guardrails.tell_kinds(base), "tells_final": guardrails.tell_kinds(body),
        },
        "hook_used": hook_used,
        "features": features,
        "editing_seconds": editing_seconds,
        "time_to_post_minutes": round(ttp * 60, 1) if ttp is not None else None,
        "guard": guard,
        "created_at": now,
        "updated_at": now,
    }
    ctx.store.insert("posts", post)
    card["status"] = "posted"
    card["status_changed_at"] = posted_at
    card["post_id"] = post["id"]
    card["work"] = None
    card["updated_at"] = now
    card["revision"] = int(card.get("revision") or 0) + 1
    draft.save_card(ctx, card)
    draft.log_interaction(ctx, "posted", card, post_id=post["id"], edit_ratio=ratio, rank=card.get("rank"),
                          time_to_post_minutes=post["time_to_post_minutes"], hook=hook_used["type"],
                          hashtags={"offered": len(offered), "used": len(used),
                                    "kept": len({t.casefold() for t in offered} & {t.casefold() for t in used})})
    if card.get("experiment_id"):
        exp = ctx.store.get("experiments", card["experiment_id"])
        if exp:
            ctx.store.update("experiments", exp["id"], picks=int(exp.get("picks") or 0) + 1,
                             updated_at=now)
    return post


def post_tells(ctx: Ctx, post: dict[str, Any]) -> tuple[list[str], list[str]]:
    """The tell kinds in the draft as shown and in the posted text: recorded when posted, and worked out
    from the card for posts recorded before tells were."""
    s = post.get("edit_stats") or {}
    if "tells_draft" in s:
        return list(s.get("tells_draft") or []), list(s.get("tells_final") or [])
    card = ctx.store.get("cards", post["card_id"]) if post.get("card_id") else None
    body, _ = posted_body(post.get("format") or "", post.get("final_text") or "", post.get("final_posts") or [])
    return guardrails.tell_kinds(_draft_text((card or {}).get("draft"))), guardrails.tell_kinds(body)


def update_post(ctx: Ctx, post_id: str, *, text: str | None = None, posts: list[str] | None = None,
                post_url: str | None = None, posted_at: str | None = None) -> None:
    post = ctx.store.get("posts", post_id)
    if post is None:
        return
    patch: dict[str, Any] = {"updated_at": timeutil.now_iso()}
    if post_url is not None:
        patch["post_url"] = post_url.strip() or None
    if posted_at:
        patch["posted_at"] = posted_at
    if text is not None or posts is not None:
        card = ctx.store.get("cards", post["card_id"]) or {}
        final_posts = [p for p in (posts or []) if p.strip()]
        final_text = "\n\n".join(final_posts) if final_posts else (text or "")
        body, found = posted_body(post.get("format") or card.get("format") or "", final_text, final_posts)
        base = _draft_text(card.get("draft"))
        patch.update(final_text=final_text, final_posts=final_posts, hashtags=hashtags.clean(found, 15),
                     edit_ratio=textutil.edit_ratio(base, body) if base else None,
                     guard=guardrails.check_final(final_text, ctx.blocklist))
        changes = textutil.edit_changes(base, body) if base else {"removed": [], "added": []}
        stats = dict(post.get("edit_stats") or {})
        stats.update(final_words=textutil.word_count(body), final_chars=len(body),
                     removed=changes["removed"][:30], added=changes["added"][:30],
                     tells_draft=guardrails.tell_kinds(base), tells_final=guardrails.tell_kinds(body))
        patch["edit_stats"] = stats
        if card:
            patch["hook_used"] = detect_hook(card, final_text, None)
    ctx.store.update("posts", post_id, **patch)


# ---------------------------------------------------------------------------
# Rewards (relative to Ankit's rolling median)
# ---------------------------------------------------------------------------

COMPONENT_FALLBACK = {"followers_gained": "profile_views"}


def latest_metrics(ctx: Ctx) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in ctx.store.select("metrics", "status = 'confirmed' AND post_id IS NOT NULL", order="captured_at"):
        out[m["post_id"]] = m
    return out


def update_rewards(ctx: Ctx) -> int:
    lm = latest_metrics(ctx)
    window = ctx.settings.learning.median_window
    updated = 0
    for platform in ("linkedin", "x"):
        weights = ctx.settings.rewards.get(platform, {})
        posts = [p for p in ctx.store.select("posts", "platform = ?", (platform,), order="posted_at") if p["id"] in lm]
        for i, post in enumerate(posts):
            ref = posts[max(0, i - window + 1): i + 1]
            parts: dict[str, Any] = {}
            num = den = 0.0
            for comp, w in weights.items():
                value = _metric_value(lm[post["id"]], comp)
                if value is None:
                    continue
                series = [v for p in ref if (v := _metric_value(lm[p["id"]], comp)) is not None]
                median = statistics.median(series) if series else value
                score = (value + 1) / (median + 1)
                parts[comp] = {"value": value, "median": median, "score": round(score, 3), "weight": w}
                num += w * score
                den += w
            if den == 0:
                continue
            reward = num / den
            ctx.store.update("posts", post["id"], reward=round(reward, 4), reward_parts=parts,
                             perf=round(reward / (reward + 1), 4))
            updated += 1
    if updated:
        log.info(f"learn: rewards updated for {updated} posts")
    return updated


def _metric_value(m: dict[str, Any], comp: str) -> float | None:
    v = m.get(comp)
    if v is None and comp in COMPONENT_FALLBACK:
        v = m.get(COMPONENT_FALLBACK[comp])
    if comp == "reposts" and v is not None and m.get("sends") is not None and m.get("platform") == "linkedin":
        v = v + m["sends"]
    return float(v) if v is not None else None


# ---------------------------------------------------------------------------
# Expiry and housekeeping
# ---------------------------------------------------------------------------


def expire_cards(ctx: Ctx) -> int:
    now = timeutil.now()
    now_iso = timeutil.iso(now)
    n = 0
    for card in ctx.store.select("cards", "status IN ('suggested','needs_input','blocked','failed') "
                                 "AND expires_at IS NOT NULL AND expires_at <= ? AND work IS NULL", (now_iso,)):
        _expire(ctx, card, now_iso)
        n += 1
    idle = timeutil.iso(now - dt.timedelta(hours=ctx.settings.expiry.editing_idle_hours))
    for card in ctx.store.select("cards", "status = 'editing' AND updated_at <= ?", (idle,)):
        _expire(ctx, card, now_iso, reason="idle")
        n += 1
    # Cards left 'drafting' by an interrupted run become brief cards with a 'Draft this' button.
    stale = timeutil.iso(now - dt.timedelta(minutes=45))
    for card in ctx.store.select("cards", "status = 'drafting' AND updated_at <= ? AND work IS NULL", (stale,)):
        draft.make_brief(ctx, card, "Drafting was interrupted. Tap 'Draft this' to retry.")
    if n:
        log.info(f"learn: expired {n} cards")
    return n


def _expire(ctx: Ctx, card: dict[str, Any], at: str, reason: str = "time") -> None:
    card["status"] = "expired"
    card["status_changed_at"] = at
    card["updated_at"] = at
    draft.save_card(ctx, card)
    draft.log_interaction(ctx, "expired", card, reason=reason, rank=card.get("rank"))


def prune(ctx: Ctx) -> dict[str, int]:
    from .scout.scouting import prune_items

    out = {"items": prune_items(ctx.store, ctx.settings.scouting.item_retention_days)}
    cutoff = timeutil.iso(timeutil.now() - dt.timedelta(days=30))
    out["processed_events"] = ctx.store.delete_where("processed_events", "at < ?", (cutoff,))
    run_cutoff = timeutil.iso(timeutil.now() - dt.timedelta(days=120))
    out["runs"] = ctx.store.delete_where("runs", "started_at < ?", (run_cutoff,))
    old_quota = (timeutil.now() - dt.timedelta(days=60)).strftime("%Y-%m-%d")
    out["quota"] = ctx.store.delete_where("quota", "day < ?", (old_quota,))
    out["image_rows"] = ctx.store.delete_where("images", "day < ?", (old_quota,))
    out["media"] = images.prune_media(ctx)
    return out
