"""The drafting style context: playbook rules, voice profile, hook preferences and example posts.

Everything learned about Ankit's taste reaches the drafter through here, and the versions used are
stamped on each card so the system report can compare them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from . import textutil
from .context import Ctx


@dataclass
class Style:
    rules: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    length_target: str = ""
    hook_prefs: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    playbook_version: str | None = None
    voice_version: str | None = None
    experiment: dict[str, Any] | None = None


def active_playbook(ctx: Ctx) -> dict[str, Any] | None:
    rows = ctx.store.select("playbook_versions", "status = 'active'", order="version DESC", limit=1)
    return rows[0] if rows else None


def latest_voice(ctx: Ctx) -> dict[str, Any] | None:
    rows = ctx.store.select("voice_profiles", order="version DESC", limit=1)
    return rows[0] if rows else None


DEFAULT_LENGTH = {
    "li_text": "120–220 words; short paragraphs of one to three sentences",
    "x_single": "one post, ideally under 240 characters",
    "x_thread": "3 to 5 posts",
    "x_quote": "under 200 characters",
    "x_reply": "under 180 characters",
}


def style_for(ctx: Ctx, platform: str, pillar: str, fmt: str) -> Style:
    st = Style()
    playbook = active_playbook(ctx)
    if playbook:
        st.playbook_version = f"v{playbook['version']}"
        for rule in playbook.get("rules") or []:
            if rule.get("platform") not in (None, platform):
                continue
            if rule.get("pillar") not in (None, pillar):
                continue
            st.rules.append(rule["text"])
    voice = latest_voice(ctx)
    voice_avoid: list[str] = []
    if voice:
        st.voice_version = f"v{voice['version']}"
        st.rules.extend(voice.get("rules") or [])
        voice_avoid = list(voice.get("avoid") or [])
        lengths = ((voice.get("stats") or {}).get(platform) or {}).get("final_length_median")
        if lengths and fmt in ("li_text", "x_single"):
            unit = "characters"
            st.length_target = f"around {int(lengths)} {unit} (the median length of what he actually posts)"
    st.avoid = sorted({*ctx.settings.voice.avoid_phrases, *voice_avoid}, key=str.lower)
    st.length_target = st.length_target or DEFAULT_LENGTH.get(fmt, "")
    st.hook_prefs = hook_preferences(ctx, platform)
    st.examples = recent_examples(ctx, platform, ctx.settings.voice.examples_per_prompt)
    return st


def hook_preferences(ctx: Ctx, platform: str) -> list[str]:
    """Hook types ordered by how often he keeps them (from posts), falling back to all types."""
    counts: Counter[str] = Counter()
    for post in ctx.store.select("posts", "platform = ?", (platform,), order="posted_at DESC", limit=40):
        used = (post.get("hook_used") or {}).get("type")
        if used:
            counts[used] += 1
    ordered = [t for t, _ in counts.most_common()]
    return ordered + [t for t in ctx.settings.hooks.types if t not in ordered]


def recent_examples(ctx: Ctx, platform: str, n: int) -> list[str]:
    if n <= 0:
        return []
    rows = ctx.store.select("posts", "platform = ?", (platform,), order="posted_at DESC", limit=n)
    out = []
    for post in rows:
        text = post.get("final_text") or "\n".join(post.get("final_posts") or [])
        if text.strip():
            out.append(textutil.truncate(text, 1200))
    return out


def render_rules(rules: list[str]) -> str:
    if not rules:
        return "- (No learned rules yet: write plainly and specifically.)"
    return "\n".join(f"- {r}" for r in rules[:20])


def render_examples(examples: list[str]) -> str:
    if not examples:
        return "(None yet. The voice profile learns from his edits once he starts posting.)"
    return "\n\n".join(f"Example {i}:\n{e}" for i, e in enumerate(examples, 1))
