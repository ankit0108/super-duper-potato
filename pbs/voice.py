"""Voice profile learned from Ankit's edits (FR-22).

Daily, in code: length he actually posts, sentence length, emoji/hashtag/line-break habits, and phrases he
repeatedly cuts (added to the avoid list after two cuts). Weekly, the model turns diffs into style rules.
"""

from __future__ import annotations

import datetime as dt
import re
import statistics
from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from . import log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import BudgetExhausted, LLMRequest

FLUFF = {"really", "very", "just", "truly", "incredibly", "extremely", "crucial", "essential", "landscape",
         "leverage", "leveraging", "robust", "seamless", "seamlessly", "powerful", "exciting", "innovative",
         "journey", "unlock", "unleash", "dive", "deep-dive", "transformative", "groundbreaking", "delve"}
_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "it", "that", "this", "with", "as",
         "be", "are", "was", "at", "by", "from", "we", "you", "i", ",", ".", ":", ";", "-", "—", "'", "’"}


def _ngrams(phrase: str, n_max: int = 4) -> set[str]:
    toks = [t for t in phrase.casefold().split() if t]
    grams: set[str] = set()
    for n in range(1, n_max + 1):
        for i in range(len(toks) - n + 1):
            gram = toks[i:i + n]
            if gram[0] in _STOP or gram[-1] in _STOP:
                continue
            if n == 1 and gram[0] not in FLUFF:
                continue
            grams.add(" ".join(gram))
    return grams


def _grams_of(phrases: list[str] | None) -> set[str]:
    """Distinct n-grams across one post's removed (or added) phrases, so each post counts once."""
    grams: set[str] = set()
    for phrase in phrases or []:
        grams |= _ngrams(phrase)
    return grams


def compute_stats(ctx: Ctx, days: int = 60) -> dict[str, Any]:
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=days))
    out: dict[str, Any] = {}
    for platform in ("linkedin", "x"):
        posts = ctx.store.select("posts", "platform = ? AND posted_at >= ?", (platform, since), order="posted_at")
        if not posts:
            continue
        finals = [p["final_text"] or "" for p in posts]
        stats_rows = [p.get("edit_stats") or {} for p in posts]
        draft_chars = [s.get("draft_chars") for s in stats_rows if s.get("draft_chars")]
        final_chars = [len(f) for f in finals if f]
        sentences = [len(s.split()) for f in finals for s in textutil.split_sentences(f)]
        words = sum(textutil.word_count(f) for f in finals) or 1
        cut: Counter[str] = Counter()
        added: Counter[str] = Counter()
        for s in stats_rows:
            cut.update(_grams_of(s.get("removed")))
            added.update(_grams_of(s.get("added")))
        ratios = [p["edit_ratio"] for p in posts if p.get("edit_ratio") is not None]
        out[platform] = {
            "posts": len(posts),
            "final_length_median": int(statistics.median(final_chars)) if final_chars else None,
            "draft_length_median": int(statistics.median(draft_chars)) if draft_chars else None,
            "length_ratio": round(statistics.median(final_chars) / statistics.median(draft_chars), 2)
            if final_chars and draft_chars else None,
            "sentence_words_median": statistics.median(sentences) if sentences else None,
            "emoji_per_post": round(sum(len(_EMOJI.findall(f)) for f in finals) / len(finals), 2),
            "hashtags_per_post": round(sum(f.count("#") for f in finals) / len(finals), 2),
            "line_breaks_per_100_words": round(100 * sum(f.count("\n") for f in finals) / words, 1),
            "edit_ratio_median": round(statistics.median(ratios), 3) if ratios else None,
            "cut": [{"phrase": k, "count": v} for k, v in cut.most_common(25) if v >= 2 and added[k] == 0],
            "added": [{"phrase": k, "count": v} for k, v in added.most_common(15) if v >= 2],
        }
    return out


def deterministic_rules(stats: dict[str, Any]) -> list[str]:
    rules: list[str] = []
    for platform, s in stats.items():
        label = "LinkedIn" if platform == "linkedin" else "X"
        if s.get("posts", 0) < 3:
            continue
        if s.get("length_ratio") and s["length_ratio"] < 0.85 and s.get("final_length_median"):
            rules.append(f"On {label} he cuts drafts to about {int(s['length_ratio'] * 100)}% of their length: "
                         f"aim for about {s['final_length_median']} characters.")
        if s.get("emoji_per_post") == 0:
            rules.append(f"No emoji on {label}.")
        if s.get("hashtags_per_post") == 0:
            rules.append(f"No hashtags on {label}.")
        if s.get("sentence_words_median") and s["sentence_words_median"] <= 12:
            rules.append(f"Keep {label} sentences short (about {int(s['sentence_words_median'])} words).")
    return rules


class _VoiceOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rules: list[str] = Field(default_factory=list)
    summary: str = ""


def llm_rules(ctx: Ctx, stats: dict[str, Any]) -> tuple[list[str], str] | None:
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=21))
    posts = ctx.store.select("posts", "posted_at >= ? AND edit_ratio IS NOT NULL", (since,), order="posted_at DESC",
                             limit=8)
    if len(posts) < 3:
        return None
    pairs = []
    for p in posts:
        card = ctx.store.get("cards", p["card_id"]) or {}
        d = card.get("draft") or {}
        base = "\n\n".join(d.get("posts") or []) or d.get("text") or ""
        pairs.append({"platform": p["platform"], "draft": textutil.truncate(base, 900),
                      "posted": textutil.truncate(p["final_text"], 900), "edit_ratio": p["edit_ratio"]})
    prompt = prompting.render("voice", display_name=ctx.settings.display_name,
                              input_json={"stats": stats, "pairs": pairs})
    req = LLMRequest(task="voice", system="You analyse writing edits precisely and briefly.", prompt=prompt,
                     max_output_tokens=1500, personal=True, prompt_version=prompting.version("voice"))
    try:
        out, _ = ctx.llm.call_json(req, _VoiceOut)
    except (BudgetExhausted, ValueError) as exc:
        log.info(f"voice: model rules skipped ({type(exc).__name__})")
        return None
    rules = [textutil.truncate(r, 200) for r in out.rules if r.strip()][:6]
    return rules, textutil.truncate(out.summary, 400)


def update_voice(ctx: Ctx, weekly: bool = False) -> dict[str, Any] | None:
    stats = compute_stats(ctx)
    if not stats:
        return None
    prev_rows = ctx.store.select("voice_profiles", order="version DESC", limit=1)
    prev = prev_rows[0] if prev_rows else None
    avoid = set((prev or {}).get("avoid") or [])
    for s in stats.values():
        for c in s.get("cut", []):
            avoid.add(c["phrase"])
    det_rules = deterministic_rules(stats)
    prev_det = deterministic_rules((prev or {}).get("stats") or {})
    model_rules: list[str] = [r for r in (prev or {}).get("rules") or [] if r not in prev_det]
    summary = (prev or {}).get("summary")
    if weekly:
        res = llm_rules(ctx, stats)
        if res:
            model_rules, summary = res
    rules = det_rules + [r for r in model_rules if r not in det_rules]
    newest_post = ctx.store.scalar("SELECT MAX(posted_at) FROM posts")
    changed = (prev is None or sorted(avoid) != sorted(prev.get("avoid") or []) or rules != prev.get("rules")
               or _length_shift(stats, (prev or {}).get("stats") or {}))
    if not changed:
        return prev
    version = int(prev["version"]) + 1 if prev else 1
    examples = {pl: [p["id"] for p in ctx.store.select("posts", "platform = ?", (pl,), order="posted_at DESC", limit=2)]
                for pl in ("linkedin", "x")}
    row = {"id": f"vp_v{version:03d}", "version": version, "created_at": timeutil.now_iso(), "stats": stats,
           "rules": rules, "avoid": sorted(avoid), "cut_phrases": [c for s in stats.values() for c in s.get("cut", [])],
           "added_phrases": [c for s in stats.values() for c in s.get("added", [])], "examples": examples,
           "summary": summary or f"Learned from {sum(s['posts'] for s in stats.values())} posts (latest {newest_post})."}
    ctx.store.upsert("voice_profiles", row)
    log.info(f"voice: profile v{version} ({len(rules)} rules, {len(avoid)} avoided phrases)")
    return row


def _length_shift(new: dict[str, Any], old: dict[str, Any]) -> bool:
    for platform, s in new.items():
        a, b = s.get("final_length_median"), (old.get(platform) or {}).get("final_length_median")
        if a and (not b or abs(a - b) / b > 0.15):
            return True
    return False
