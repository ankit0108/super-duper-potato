"""Hashtags: suggested with every draft, chosen on the card, and learned from what he keeps.

The draft's text never carries them: they're a separate list that the desk shows as chips and appends when he
copies, opens the app or marks the post as posted. The posted text is compared with the draft without them,
so keeping or dropping tags doesn't count as editing the post.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_WORDS = re.compile(r"[^\W_]+")
_TRAILING = re.compile(r"(?:[ \t]+#[^\s#]+)+[ \t]*$")


def normalize(raw: str) -> str | None:
    """'#AI agents', 'ai agents' or 'AIAgents' -> '#AIAgents'; None for numbers, blanks and very long tags."""
    words = _WORDS.findall(str(raw).strip().lstrip("#"))
    if not words:
        return None
    tag = words[0] if len(words) == 1 else "".join(w[:1].upper() + w[1:] for w in words)
    if tag.isdigit() or len(tag) > 30:
        return None
    return "#" + tag


def clean(raw: Iterable[Any], limit: int, avoid: Iterable[str] = (), blocklist: Iterable[str] = ()) -> list[str]:
    """Normalized, deduplicated tags without the avoided ones or any that contain a blocklist term."""
    avoid_keys = {str(a).lstrip("#").casefold() for a in avoid}
    blocked = [re.sub(r"[\W_]+", "", t).casefold() for t in blocklist]
    out: list[str] = []
    seen: set[str] = set()
    for r in raw:
        tag = normalize(str(r)) if isinstance(r, (str, int)) else None
        if not tag:
            continue
        key = tag[1:].casefold()
        if key in seen or key in avoid_keys or any(b and b in key for b in blocked):
            continue
        seen.add(key)
        out.append(tag)
    return out[:max(0, limit)]


def mostly_removed(stats: dict[str, Any] | None) -> bool:
    """He removes nearly all suggested tags on a platform (judged on at least four posts that were offered some):
    the drafter suggests none there until that changes."""
    stats = stats or {}
    return stats.get("offered_posts", 0) >= 4 and (stats.get("keep_rate") or 0) < 0.2


def split_trailing(text: str | None) -> tuple[str, list[str]]:
    """A post that ends in hashtags (on their own lines or after the last sentence) -> (body, tags).
    Only tokens that are real tags are taken: "ranked #1" stays in the body."""
    body = (text or "").rstrip()
    tags: list[str] = []
    while True:
        lines = body.split("\n")
        last = lines[-1].strip()
        words = last.split()
        if len(lines) > 1 and words and all(w.startswith("#") and normalize(w) for w in words):
            tags = words + tags
            body = "\n".join(lines[:-1]).rstrip()
            continue
        m = _TRAILING.search(body)
        if m and body[:m.start()].strip() and all(normalize(w) for w in m.group(0).split()):
            tags = m.group(0).split() + tags
            body = body[:m.start()].rstrip()
            continue
        return body, tags


def strip_from_posts(posts: list[str]) -> tuple[list[str], list[str]]:
    """Tags a thread carries at the end of its first or last post."""
    out = list(posts)
    tags: list[str] = []
    for i in {0, len(out) - 1} if out else set():
        out[i], found = split_trailing(out[i])
        tags += found
    return out, tags
