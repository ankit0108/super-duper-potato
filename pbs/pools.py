"""Material that isn't news: premises for funny posts, themes for a thought, and quotes.

Three pools in pbs/defaults, each a few entries a day in turn, so the whole pool comes round in time:
- humor_pools.yaml: premises for a relatable funny post (tech and work on both platforms, life on X only);
- thought_pools.yaml: themes for one sharp thought (X);
- quote_pools.yaml: quotes worth sharing (X), each used only once its words are found on the author's Wikiquote
  page (outside the misattributed, disputed and "about" sections), so a misattributed quote never reaches a card.

Premises and themes become candidates directly (rank.pool_candidates). Quotes need the Wikiquote check, so they're
fetched by a `wikiquote_pool` source like any other (scout.sources.fetch_url, scout.parsers).
"""

from __future__ import annotations

import datetime as dt
import html
import random
import re
import unicodedata
from functools import cache
from importlib import resources
from typing import Any

import yaml

from . import ids, textutil, timeutil

QUOTE_MAX_CHARS = 180  # room on X for the attribution and a line of one's own


def _yaml(name: str) -> dict[str, Any]:
    return yaml.safe_load(resources.files("pbs.defaults").joinpath(name).read_text(encoding="utf-8")) or {}


def _interleave(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Every group spread evenly through the pool (each entry at its share of its group's length), so a day's batch
    mixes themes from the first entry to the last. The order within a group is shuffled once, the same way every
    run, so an author's quotes or a theme's premises don't come up on the same day."""
    keyed: list[tuple[float, int, dict[str, Any]]] = []
    for gi, group in enumerate(groups):
        shuffled = list(group)
        random.Random(f"pool:{gi}:{len(group)}").shuffle(shuffled)
        keyed.extend(((i + 0.5) / len(shuffled), gi, e) for i, e in enumerate(shuffled))
    return [e for _, _, e in sorted(keyed, key=lambda k: (k[0], k[1]))]


@cache
def humor() -> list[dict[str, Any]]:
    """Premises: [{id, text, group, platforms}] in batch order."""
    groups = []
    for name, spec in _yaml("humor_pools.yaml").items():
        platforms = tuple((spec or {}).get("platforms") or ("x",))
        groups.append([{"id": f"pool:humor:{ids.short_hash(t, 10)}", "text": textutil.normalize_ws(t),
                        "group": name, "platforms": platforms} for t in (spec or {}).get("premises") or []])
    return _interleave(groups)


@cache
def thoughts() -> list[dict[str, Any]]:
    """Themes: [{id, text, group, platforms}] in batch order."""
    groups = [[{"id": f"pool:thought:{ids.short_hash(t, 10)}", "text": textutil.normalize_ws(t), "group": name,
                "platforms": ("x",)} for t in themes or []] for name, themes in _yaml("thought_pools.yaml").items()]
    return _interleave(groups)


@cache
def quotes() -> list[dict[str, Any]]:
    """Quotes: [{id, text, by, page, group}] in batch order. `page` is the Wikiquote page (default: `by`)."""
    groups = []
    for name, entries in _yaml("quote_pools.yaml").items():
        group = []
        for e in entries or []:
            text = textutil.normalize_ws(e.get("text"))
            if not text or not e.get("by") or len(text) > QUOTE_MAX_CHARS:
                continue
            group.append({"id": ids.short_hash(f"{e['by']}|{text}", 10), "text": text, "by": e["by"],
                          "page": e.get("page") or e["by"], "group": name})
        groups.append(group)
    return _interleave(groups)


def todays(pool: list[dict[str, Any]], local_date: str | None, n: int,
           skip: set[str] | frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """The day's batch: the next `n` entries not in `skip`, starting where the date puts it in the pool."""
    if not pool or n <= 0:
        return []
    day = dt.date.fromisoformat(local_date) if local_date else timeutil.now().date()
    start = (day.toordinal() * n) % len(pool)
    out: list[dict[str, Any]] = []
    for k in range(len(pool)):
        entry = pool[(start + k) % len(pool)]
        if entry["id"] not in skip:
            out.append(entry)
            if len(out) >= n:
                break
    return out


# ---------------------------------------------------------------------------
# Wikiquote: is the quote on the author's page?
# ---------------------------------------------------------------------------

# Sections whose quotes aren't the author's own words, or aren't sourced: never used to verify a quote.
_NOT_THEIRS = re.compile(r"^(?:misattribut|disputed|attributed|unsourced|about\b|quotes?\s+about|quotations?\s+about|"
                         r"sayings?\s+about|quotes?\s+(?:by|from)\s+others|said\s+about|see\s+also|external\s+links)", re.I)
_HEADING = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$")
_KEEP_LAST = re.compile(r"\{\{\s*(?:w|wikipedia|wp|nowrap|small|sic|lang|lang-\w+)\s*\|(?:[^{}|]*\|)*([^{}|]*)\}\}", re.I)


def sourced_wikitext(wikitext: str) -> str:
    """The page without the sections that aren't the author's own, sourced words."""
    out: list[str] = []
    skip_level = 0
    for line in (wikitext or "").splitlines():
        m = _HEADING.match(line.strip())
        if m:
            level = len(m.group(1))
            if skip_level and level <= skip_level:
                skip_level = 0
            if not skip_level and _NOT_THEIRS.match(m.group(2)):
                skip_level = level
            continue
        if not skip_level:
            out.append(line)
    return "\n".join(out)


def wiki_plain(wikitext: str) -> str:
    """Wikitext as plain text: links, bold and italics, references, templates and tags removed."""
    text = re.sub(r"<!--.*?-->", " ", wikitext or "", flags=re.S)
    text = re.sub(r"<ref[^>/]*/>", " ", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", " ", text, flags=re.S)
    for _ in range(6):
        new = _KEEP_LAST.sub(r"\1", text)
        new = re.sub(r"\{\{[^{}]*\}\}", " ", new)
        if new == text:
            break
        text = new
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("'''", "").replace("''", "")
    return html.unescape(text)


def words(text: str) -> str:
    """Lower-case words only, so punctuation, dashes, quote marks and line breaks don't matter."""
    t = unicodedata.normalize("NFKC", text or "").casefold().replace("’", "'").replace("‘", "'")
    return " ".join(re.findall(r"\w+", t))


def found_in(quote: str, wikitext: str) -> bool:
    """Whether the quote's words appear, in order and together, in the page's sourced sections."""
    needle = words(quote)
    return bool(needle) and f" {needle} " in f" {words(wiki_plain(sourced_wikitext(wikitext)))} "


def lead_sentence(wikitext: str) -> str:
    """Who the page is about, from its first lines (before any section): "… was an American computer scientist."""
    head = re.split(r"(?m)^=", wikitext or "", maxsplit=1)[0]
    lines = [ln for ln in head.splitlines() if ln.strip() and not ln.lstrip().startswith(("*", "{", "|", "[[File",
                                                                                        "[[Image", "#", ":"))]
    plain = textutil.normalize_ws(wiki_plain(" ".join(lines)))
    plain = re.sub(r"\(\s*[;,]?\s*\)", "", plain)
    sentences = textutil.split_sentences(plain)
    return textutil.truncate(sentences[0], 300) if sentences else ""
