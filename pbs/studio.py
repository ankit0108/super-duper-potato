"""The Studio: a chat on the desk that answers in seconds (it calls Gemini from the browser with a key kept on the
device) and writes posts and carousels in Ankit's voice.

The pipeline's part is small. It exports the *Studio kit* in desk.json: the system rules, the style learned from
edits, the platform guide, examples of past posts, hashtag habits and the kinds of post, rendered into the
Studio's instructions (prompts/studio.md), so a Studio draft follows the same rules as a morning card. And it turns
a draft saved from the Studio into a card on the board (`studio.save`), so posting it teaches the learner like
any other card.
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
from typing import Any

from . import draft, guardrails, hashtags, posttypes, prompting, textutil, timeutil, visuals
from .bandit import arm_id
from .context import Ctx
from .platform import render as render_platform_rules
from .style import render_examples, render_rules, style_for

STYLE_FORMAT = {"linkedin": "li_text", "x": "x_single"}


def _style_block(ctx: Ctx, platform: str) -> str:
    style = style_for(ctx, platform, "", STYLE_FORMAT[platform])
    name = ctx.settings.display_name
    parts = [
        f"Rules learned from {name}'s edits:\n{render_rules(style.rules)}",
        f"What works on {draft.PLATFORM_LABEL[platform]} now:\n{render_platform_rules(style.platform_rules)}",
        draft.format_instructions(ctx, STYLE_FORMAT[platform]),
    ]
    if platform == "x":
        parts.append(draft.format_instructions(ctx, "x_thread"))
    parts += [
        f"Target length: {style.length_target or 'as short as the idea allows'}",
        f"Never use: {', '.join(style.avoid[:40]) or '(nothing listed)'}",
        f"Recent posts {name} published (match the voice, never reuse the content):\n{render_examples(style.examples)}",
    ]
    return "\n\n".join(parts)


def kit(ctx: Ctx) -> dict[str, Any]:
    """What the desk's Studio needs to write like the pipeline: its full instructions, and the lists the desk uses
    for the live checks and the post editor."""
    s = ctx.settings
    tags = s.hashtags
    hashtag_rule = (f"LinkedIn {tags.linkedin.min} to {tags.linkedin.max}, X at most {tags.x.max}: one or two broad "
                    "tags people follow and the rest specific to the post, CamelCase") if tags.enabled else "[] (none)"
    pillars = {pl: {k: p.label for k, p in s.pillars(pl).items()} for pl in ("linkedin", "x")}
    instructions = prompting.render(
        "studio", display_name=s.display_name, thread_min=s.platforms.x.thread_min,
        thread_max=s.platforms.x.thread_max, x_limit=s.x_char_limit(), hashtags=hashtag_rule,
        linkedin_pillars=", ".join(pillars["linkedin"]), x_pillars=", ".join(pillars["x"]),
        linkedin=_style_block(ctx, "linkedin"), x=_style_block(ctx, "x"),
        post_types="\n".join(f"- {k} ({posttypes.LABELS.get(k, k)}): {v}"
                             for k, v in draft.POST_TYPE_INSTRUCTIONS.items()),
        visual_kinds="\n".join(f"  - {k}: {rule}" for k, rule in visuals.KIND_RULES.items() if k != "image"))
    return {
        "version": prompting.version("system", "studio"),
        "system": draft._system(ctx) + "\n\n" + instructions,
        "pillars": pillars,
        "avoid": sorted({*s.voice.avoid_phrases}, key=str.lower),
        "bait": list(s.voice.bait_phrases),
        "x_limit": s.x_char_limit(),
        "fold": s.platforms.linkedin.fold_chars,
    }


def save(ctx: Ctx, ev: Any) -> dict[str, Any]:
    """A draft saved from the Studio, as a card on today's board: ready to edit, post and learn from."""
    platform = ev.platform
    fmt = ev.format if ev.format in ctx.settings.formats and ctx.settings.formats[ev.format].platform == platform \
        else ("li_text" if platform == "linkedin" else "x_single")
    pillar = ev.pillar if ev.pillar and ctx.settings.pillar(platform, ev.pillar) else \
        ("industry" if platform == "linkedin" else "tech")
    if ctx.settings.pillar(platform, pillar) is None:
        pillar = next(iter(ctx.settings.pillars(platform)))
    now = timeutil.now_iso()
    card_id = ev.card_id
    posts = [p.strip() for p in ev.posts or [] if p.strip()] if fmt == "x_thread" else []
    text = "" if posts else (ev.text or "").strip()
    sources = [{"url": s.url, "title": s.title or s.url, "publisher": textutil.url_host(s.url) or None, "lang": "en"}
               for s in ev.sources or [] if s.url.startswith(("http://", "https://"))][:8]
    tags = hashtags.clean(ev.hashtags or [], 10, [], ctx.blocklist)
    attachments = [{**_keep_blob(ctx, card_id, img.path, i), "width": img.width, "height": img.height}
                   for i, img in enumerate(ev.images or [])]
    visual: dict[str, Any] | None = None
    if ev.visual:
        v = ev.visual
        visual = {"kind": v.kind, "title": v.title, "subtitle": v.subtitle, "caption": v.caption,
                  "alt_text": v.alt_text, "items": [{"title": it.title, "body": it.body} for it in v.items],
                  "created_at": now}
        if v.photo is not None and v.photo < len(attachments):
            # The shared picture behind the cover, the big number or the quote, kept with the card.
            att = attachments[v.photo]
            visual["image"] = {"path": att["path"], "width": att["width"] or 1080, "height": att["height"] or 1080,
                               "content_type": att["content_type"], "provider": "your photo", "created_at": now}
    draft_ = {"text": text, "posts": posts}
    if ev.first_comment:
        draft_["first_comment"] = ev.first_comment.strip()[:500]
    card = {
        "id": card_id,
        "kind": "studio",
        "platform": platform,
        "mode": "external",
        "pillar": pillar,
        "format": fmt,
        "post_type": ev.post_type if ev.post_type in posttypes.LABELS else None,
        "title": (ev.title or text or (posts[0] if posts else "Studio post"))[:200],
        "why_now": "Written with you in the Studio.",
        "angle": None,
        "draft": draft_,
        "draft_original": draft_,
        "hooks": [{"type": "observation", "text": h.strip()} for h in (ev.hooks or []) if h.strip()][:3],
        "hashtags": tags,
        "sources": sources,
        "claims": [],
        "status": "suggested",
        "draft_state": "full",
        "draft_basis": "sources" if sources else "answers",
        "arm": arm_id(platform, pillar, fmt),
        "versions": {"prompt": ev.kit_version},
        "llm": {"provider": "studio", "model": ev.model or "gemini"},
        "visual": visual,
        "attachments": attachments,
        "created_at": now,
        "updated_at": now,
        "delivered_at": now,
        "expires_at": timeutil.iso(timeutil.now() + dt.timedelta(days=ctx.settings.expiry.request_days)),
        "revision": 1,
        "rewrite_count": 0,
    }
    evidence = "\n".join([card["title"], *(s["title"] for s in sources), ev.evidence or ""])
    check = guardrails.check_card(card, settings=ctx.settings, blocklist=ctx.blocklist, evidence=evidence,
                                  avoid_phrases=ctx.settings.voice.avoid_phrases,
                                  bait_phrases=ctx.settings.voice.bait_phrases)
    card["flags"] = check.flags
    if check.blocked:
        card["status"] = "blocked"
    draft.save_card(ctx, card)
    draft.log_interaction(ctx, "studio_saved", card, images=len(attachments), visual=bool(visual))
    return card


def _keep_blob(ctx: Ctx, card_id: str, path: str, n: int) -> dict[str, Any]:
    """Move a picture the desk uploaded (inbox/blobs/…) to the card's media folder."""
    if not re.fullmatch(r"inbox/blobs/[A-Za-z0-9_-][A-Za-z0-9_.-]*", path) or ".." in path:
        raise ValueError(f"pictures must be uploaded under inbox/blobs/ ({path})")
    src = ctx.data_root / path
    suffix = src.suffix.lower() if src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
    rel = f"media/studio/{card_id}/{n + 1}{suffix}"
    dest = ctx.data_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.move(str(src), str(dest))
    elif not dest.exists():
        raise ValueError(f"the picture {path} hasn't arrived")
    content_type = {".png": "image/png", ".webp": "image/webp"}.get(suffix, "image/jpeg")
    return {"path": rel, "content_type": content_type}
