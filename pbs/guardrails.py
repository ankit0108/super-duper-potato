"""Deterministic guardrails. They run in code before anything reaches the desk.

A blocked draft is flagged, never quietly reworded. Everything else (first-person claims in external
mode, unsourced numbers, sensitive events, bait and cliché phrases, length) is flagged for review.
The blocklist lives in the PBS_BLOCKLIST secret and is also used to redact every LLM input.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from . import textutil

REDACTED = "[redacted]"


# ---------------------------------------------------------------------------
# Blocklist
# ---------------------------------------------------------------------------


def load_blocklist(env: str = "PBS_BLOCKLIST") -> list[str]:
    raw = os.environ.get(env, "")
    return parse_terms(raw)


def parse_terms(raw: str) -> list[str]:
    terms: list[str] = []
    for part in re.split(r"[\n,;]+", raw or ""):
        term = part.strip()
        if not term or term.startswith("#") or len(term) < 2:
            continue
        if term.casefold() not in {t.casefold() for t in terms}:
            terms.append(term)
    return sorted(terms, key=len, reverse=True)


@lru_cache(maxsize=512)
def _term_regex(term: str) -> re.Pattern[str]:
    pieces = [re.escape(p) for p in re.split(r"[\s\-_.]+", term.strip()) if p]
    body = r"[\s\-_.]*".join(pieces)
    return re.compile(rf"(?<![\w]){body}(?:['’]s|s|es)?(?![\w])", re.IGNORECASE)


def find_terms(text: str | None, terms: Iterable[str]) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for term in terms:
        if _term_regex(term).search(text) and term not in found:
            found.append(term)
    return found


def redact(text: str | None, terms: Iterable[str]) -> str:
    out = text or ""
    for term in terms:
        out = _term_regex(term).sub(REDACTED, out)
    return out


# ---------------------------------------------------------------------------
# Fabrication signals
# ---------------------------------------------------------------------------

_FIRST_PERSON = [re.compile(p, re.IGNORECASE) for p in [
    r"\bI(?:'ve| have|'d| had)? (?:built|shipped|deployed|led|ran|run|saw|seen|found|noticed|learned|learnt|tried|"
    r"tested|measured|worked|used|implemented|designed|migrated|automated|launched|wrote|created|helped|spent|"
    r"watched|interviewed|audited|reviewed)\b",
    r"\bwe(?:'ve| have|'d| had)? (?:built|shipped|deployed|saw|seen|found|noticed|learned|tried|tested|measured|"
    r"rolled out|implemented|migrated|automated|launched|moved|cut|reduced|saved|replaced|hired|lost|won)\b",
    r"\b(?:my|our) (?:team|client|clients|company|employer|org|organisation|organization|project|bank|firm|"
    r"customer|customers|stakeholders?|manager|boss|colleagues?|department|platform|pilot|rollout)\b",
    r"\bin my (?:experience|work|role|job|day job|last role)\b",
    r"\bat (?:my|our) (?:company|work|job|firm|bank|client|shop)\b",
    r"\blast (?:week|month|year|quarter),? (?:I|we)\b",
    r"\bwhen I (?:was|worked|built|led|joined)\b",
    r"\b(?:years|months) ago,? (?:I|we)\b",
]]

_OPINION = [re.compile(p, re.IGNORECASE) for p in [
    r"\bI (?:think|believe|reckon|feel|suspect|expect|predict|bet)\b",
    r"\bmy (?:take|view|opinion|bet|prediction|stance)\b",
    r"\bin my (?:view|opinion)\b",
    r"\bI'd (?:argue|say|bet)\b",
    r"\bI'm (?:convinced|bullish|bearish|skeptical|sceptical|worried)\b",
]]


def _sentences_matching(text: str, patterns: list[re.Pattern[str]]) -> list[str]:
    hits: list[str] = []
    for sentence in textutil.split_sentences(text):
        if any(p.search(sentence) for p in patterns):
            snippet = textutil.truncate(sentence, 160)
            if snippet not in hits:
                hits.append(snippet)
    return hits


def first_person_claims(text: str | None) -> list[str]:
    return _sentences_matching(text or "", _FIRST_PERSON)


def opinion_framing(text: str | None) -> list[str]:
    return _sentences_matching(text or "", _OPINION)


def unsourced_numbers(text: str | None, evidence: str | None) -> list[str]:
    """Figures in the draft that don't appear anywhere in the source material or answers."""
    ev = textutil.normalize_numbers(evidence or "").casefold()
    missing: list[str] = []
    for token in textutil.numeric_claims(text):
        core = textutil.number_core(token)
        if core and core not in ev and token not in missing:
            missing.append(token)
    return missing


# ---------------------------------------------------------------------------
# Sensitive events
# ---------------------------------------------------------------------------

SENSITIVE_EN = [
    "killed", "kills", "dead", "deaths", "death toll", "died", "massacre", "riot", "riots", "communal", "lynch",
    "lynching", "blast", "bomb", "bombing", "terror", "terrorist", "shooting", "gunman", "stampede", "rape", "raped",
    "murder", "murdered", "suicide", "tragedy", "derailment", "derailed", "genocide", "hostage", "abducted",
    "kidnapped", "casualties", "clashes", "curfew", "mob violence", "violence", "air strike", "airstrike",
    "missile strike", "plane crash", "bus accident", "drowned",
]
SENSITIVE_HI = [
    "मौत", "मृत्यु", "हत्या", "दंगा", "दंगे", "हमला", "विस्फोट", "धमाका", "बलात्कार", "आतंकी", "आतंकवादी", "भगदड़",
    "सांप्रदायिक", "हिंसा", "मारे गए", "मारे गये", "लिंचिंग", "डूबने",
]
_SENSITIVE_RE = re.compile(
    r"(?<![\w])(?:" + "|".join(re.escape(w) for w in sorted(SENSITIVE_EN + SENSITIVE_HI, key=len, reverse=True))
    + r")(?![\w])",
    re.IGNORECASE,
)


def sensitive_check(title: str | None, body: str | None = None) -> tuple[bool, str | None]:
    title_hits = {m.group(0).casefold() for m in _SENSITIVE_RE.finditer(title or "")}
    body_hits = {m.group(0).casefold() for m in _SENSITIVE_RE.finditer(body or "")}
    if title_hits or len(body_hits) >= 2:
        words = sorted(title_hits | body_hits)[:4]
        return True, "mentions " + ", ".join(words)
    return False, None


# ---------------------------------------------------------------------------
# Phrases and length
# ---------------------------------------------------------------------------


def phrase_hits(text: str | None, phrases: Iterable[str]) -> list[str]:
    low = (text or "").casefold()
    hits: list[str] = []
    for phrase in phrases:
        p = phrase.casefold().strip()
        if not p:
            continue
        if re.search(r"^\W|\W$", p):
            found = p in low
        else:
            found = re.search(rf"(?<![\w]){re.escape(p)}(?![\w])", low) is not None
        if found and phrase not in hits:
            hits.append(phrase)
    return hits


# ---------------------------------------------------------------------------
# AI tells: patterns that make a post read as machine-written. Mirrored in web/src/lib/guard.ts (aiTells); both
# are tested against tests/vectors/ai_tells.json, so the desk's live check and the pipeline agree.
# ---------------------------------------------------------------------------

AI_TELL_LABELS = {
    "contrast": "contrast framing (\"it's not X, it's Y\")",
    "reveal": "a labelled reveal (\"Here's why\", \"The result?\")",
    "opener": "a stock opener (\"In today's…\", \"Imagine…\")",
    "closer": "a summary closer (\"In short\", \"The bottom line\")",
    "dashes": "em dashes",
    "emoji_bullets": "emoji bullets",
    "staccato": "staccato negations (\"Not X. Not Y.\")",
    "questions": "stacked rhetorical questions",
    "filler": "filler phrases",
    "rhythm": "every sentence about the same length",
}
_I = re.IGNORECASE
_NEG = r"(?:'s\s+not|\s+is\s+not|\s+isn't)"
_TELL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("contrast", re.compile(r"\b(?:it|this|that)" + _NEG + r"\s+(?:just\s+|only\s+|really\s+|simply\s+)?(?:about\s+)?"
                            r"[^.!?\n]{1,80}?(?:[,;:—–]|\s-\s)\s*(?:it|this|that)(?:'s|\s+is)\b", _I)),
    ("contrast", re.compile(r"\b(?:it|this|that)" + _NEG + r"\s+[^.!?\n]{1,80}[.!]\s+(?:it|this|that)(?:'s|\s+is)\s", _I)),
    ("contrast", re.compile(r"\bnot\s+(?:just|only|merely|simply)\s+[^.!?;\n]{1,80}?,?\s+but\s+(?:also\s+)?\w", _I)),
    ("reveal", re.compile(r"(?:^|[.!?]\s+|\n)(?:the|my|our|your)\s+(?:real\s+|big\s+|hard\s+)?(?:result|answer|catch|kicker|"
                          r"takeaway|truth|reality|lesson|twist|secret|problem|fix|upshot|verdict|difference|reason)\s*\?", _I)),
    ("reveal", re.compile(r"\bhere(?:'s|\s+is)\s+(?:the\s+(?:thing|catch|kicker|twist|deal|truth|problem|secret|reality|part)|"
                          r"why|what|how|where)\b", _I)),
    ("reveal", re.compile(r"\blet's\s+(?:dive|unpack|break\s+(?:it|this|that)\s+down|explore|talk\s+about)\b", _I)),
    ("reveal", re.compile(r"\b(?:spoiler(?:\s+alert)?|plot\s+twist|the\s+kicker|hot\s+take|pro\s+tip)\s*[:!]", _I)),
    ("staccato", re.compile(r"(?:^|[.!?]\s+|\n)not\s+[^.!?\n]{1,40}[.!]\s+not\s+[^.!?\n]{1,40}[.!]", _I)),
    ("filler", re.compile(r"\b(?:it(?:'s|\s+is)\s+(?:worth\s+noting|important\s+to\s+note|no\s+secret)|"
                          r"plays?\s+a\s+(?:crucial|pivotal|vital|key)\s+role|in\s+the\s+realm\s+of|when\s+it\s+comes\s+to|"
                          r"navigat(?:e|es|ing)\s+the\s+(?:complexit\w*|landscape|world|challenges)|a\s+(?:myriad|plethora)\s+of|"
                          r"in\s+essence|needless\s+to\s+say|it\s+goes\s+without\s+saying|at\s+its\s+core|"
                          r"first\s+and\s+foremost|ever-evolving|fast-paced\s+world|the\s+(?:ever-changing\s+)?landscape\s+of)\b",
                          _I)),
]
_OPENER = re.compile(r"^\s*(?:in\s+today's\b|in\s+a\s+world\s+(?:where|of|that)\b|imagine\b|picture\s+this\b|"
                     r"ever\s+wondered\b|have\s+you\s+ever\s+(?:wondered|thought)\b|let's\s+talk\s+about\b|"
                     r"we\s+all\s+know\b|in\s+the\s+(?:ever-?changing|fast-?paced|rapidly\s+evolving)\b)", _I)
_CLOSER = re.compile(r"(?:^|\n|[.!?]\s+)(?:in\s+short|in\s+summary|to\s+sum\s+(?:it\s+)?up|the\s+bottom\s+line|"
                     r"bottom\s+line|ultimately|at\s+the\s+end\s+of\s+the\s+day|in\s+conclusion|the\s+takeaway|tl;?dr)\b", _I)
_EMOJI_LINE = re.compile("^\\s*[\u2190-\u21FF\u2600-\u27BF\u2B00-\u2BFF\U0001F300-\U0001FAFF]")


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence a match sits in (for showing it), cut to 140 characters."""
    left = max(text.rfind(c, 0, start) for c in ".!?\n")
    ends = [i for i in (text.find(c, end) for c in ".!?\n") if i != -1]
    right = min(ends) + 1 if ends else len(text)
    return textutil.truncate(text[left + 1:right].strip() or text[start:end].strip(), 140)


def ai_tells(text: str | None) -> list[dict[str, str]]:
    """Patterns that make a post read as written by AI, each with where it is: [{kind, text}] in reading order.
    The editor pass rewrites these sentences; the desk shows them as "Sounds like AI"."""
    body = (text or "").replace("\u2019", "'").replace("\u2018", "'")
    if not body.strip():
        return []
    found: list[tuple[int, str, str]] = []

    def add(pos: int, kind: str, snippet: str) -> None:
        if not any(k == kind and t == snippet for _, k, t in found):
            found.append((pos, kind, snippet))

    for kind, pattern in _TELL_PATTERNS:
        for m in pattern.finditer(body):
            add(m.start(), kind, _sentence_around(body, m.start() + (len(m.group(0)) - len(m.group(0).lstrip(".!?\n "))), m.end()))
    first = body.lstrip()
    if _OPENER.match(first):
        add(0, "opener", textutil.truncate(textutil.split_sentences(first.split("\n", 1)[0])[0], 140))
    last_para = re.split(r"\n\s*\n", body.strip())[-1]
    if (m := _CLOSER.search(last_para)) is not None:
        offset = body.rfind(last_para)
        add(offset + m.start(), "closer", _sentence_around(body, offset + m.start() + 1, offset + m.end()))
    dashes = body.count("—") + len(re.findall(r"\s–\s", body))
    if dashes > 1:
        add(body.find("—") if "—" in body else 0, "dashes", f"{dashes} em dashes")
    emoji_lines = [ln.strip() for ln in body.split("\n") if _EMOJI_LINE.match(ln)]
    if len(emoji_lines) >= 2:
        add(body.find(emoji_lines[0]), "emoji_bullets", textutil.truncate(emoji_lines[0], 140))
    sentences = textutil.split_sentences(body.replace("\n", " "))
    for a, b in zip(sentences, sentences[1:], strict=False):
        if a.endswith("?") and b.endswith("?"):
            add(body.find(a[:20]) if a[:20] in body else 0, "questions", textutil.truncate(f"{a} {b}", 140))
            break
    words = [len(s.split()) for s in sentences if len(s.split()) >= 3]
    if len(words) >= 5:
        mean = sum(words) / len(words)
        spread = (sum((w - mean) ** 2 for w in words) / len(words)) ** 0.5
        if mean >= 6 and spread / mean < 0.25:
            add(len(body), "rhythm", f"{len(words)} sentences of about {round(mean)} words each")
    return [{"kind": k, "text": t} for _, k, t in sorted(found, key=lambda f: f[0])]


def tell_kinds(text: str | None) -> list[str]:
    """The kinds of AI tell in a text, each once, sorted (what posts record and voice learning counts)."""
    return sorted({t["kind"] for t in ai_tells(text)})


def length_flags(platform: str, fmt: str, draft: dict[str, Any], settings: Any) -> list[str]:
    flags: list[str] = []
    if platform == "linkedin":
        li = settings.platforms.linkedin
        text = draft.get("text") or ""
        if len(text) > li.char_limit:
            flags.append(f"Post is {len(text)}/{li.char_limit} characters")
        head = textutil.opening(text, limit=1000)
        if len(head) > li.fold_chars:
            flags.append(f"Opening runs past the see-more fold ({len(head)} characters)")
        return flags
    limit = settings.x_char_limit()
    if fmt == "x_thread":
        posts = draft.get("posts") or []
        x = settings.platforms.x
        if posts and not (x.thread_min <= len(posts) <= x.thread_max):
            flags.append(f"Thread has {len(posts)} posts (aim for {x.thread_min}–{x.thread_max})")
        for i, post in enumerate(posts, 1):
            n = textutil.x_weighted_length(post)
            if n > limit:
                flags.append(f"Post {i} is {n}/{limit}")
    else:
        n = textutil.x_weighted_length(draft.get("text") or "")
        if n > limit:
            flags.append(f"Post is {n}/{limit}")
    return flags


# ---------------------------------------------------------------------------
# Whole-card check
# ---------------------------------------------------------------------------


@dataclass
class CardCheck:
    flags: dict[str, Any] = field(default_factory=dict)
    blocked: bool = False


def draft_text(draft: dict[str, Any] | None) -> str:
    if not draft:
        return ""
    parts = [draft.get("text") or "", *(draft.get("posts") or [])]
    reply = draft.get("reply") or {}
    if reply.get("context"):
        parts.append(reply["context"])
    return "\n\n".join(p for p in parts if p)


def check_card(card: dict[str, Any], *, settings: Any, blocklist: list[str], evidence: str,
               avoid_phrases: Iterable[str], bait_phrases: Iterable[str]) -> CardCheck:
    """Run every deterministic check on a drafted card. `evidence` = sources text (+ answers)."""
    draft = card.get("draft") or {}
    body = draft_text(draft)
    hooks_text = "\n".join(h.get("text", "") for h in (card.get("hooks") or []))
    extras = [draft.get("first_comment") or "", " ".join(t.lstrip("#") for t in card.get("hashtags") or [])]
    everything = "\n".join([body, hooks_text, card.get("angle") or "", card.get("title") or "", *extras])
    prev = card.get("flags") or {}
    # Anything not written from his own answers is analysis: experiences and opinions in it are flagged.
    external = card.get("mode") == "external" or card.get("draft_basis") == "sources" or not card.get("answers")
    flags: dict[str, Any] = {
        "blocked": find_terms(everything, blocklist),
        "unsourced": unsourced_numbers(body + "\n" + hooks_text, evidence),
        "first_person": first_person_claims(body) if external else [],
        "opinion": opinion_framing(body) if external else [],
        "avoid_phrases": phrase_hits(body + "\n" + hooks_text, avoid_phrases),
        "bait": phrase_hits(body, bait_phrases),
        "length": length_flags(card["platform"], card["format"], draft, settings),
        "ai_tells": ai_tells(body),
        "sensitive": bool(prev.get("sensitive")),
        "sensitive_reason": prev.get("sensitive_reason"),
        "stance_id": prev.get("stance_id"),
        "notes": list(prev.get("notes") or []),
    }
    return CardCheck(flags=flags, blocked=bool(flags["blocked"]))


def check_final(text: str, blocklist: list[str]) -> dict[str, Any]:
    """Check the text Ankit actually posted (reported, can't be un-posted)."""
    return {"blocked": find_terms(text, blocklist)}
