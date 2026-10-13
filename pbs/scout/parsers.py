"""Turn fetched bytes into raw items: {url, title, summary, published_at, lang, publisher, signals}."""

from __future__ import annotations

import calendar
import datetime as dt
import json
import re
from typing import Any

import feedparser

from .. import textutil, timeutil

RawItem = dict[str, Any]

_OTD_KEYWORDS = {
    "bihar": ("bihar", "patna", "magadh", "nalanda", "pataliputra", "champaran", "gaya", "bhagalpur", "muzaffarpur"),
    "india": ("india", "indian", "delhi", "mumbai", "bombay", "calcutta", "kolkata", "madras", "gandhi", "nehru",
              "british raj", "mughal", "isro", "pakistan", "bangladesh", "nepal", "sri lanka", "partition"),
    "world": ("computer", "internet", "software", "artificial intelligence", "satellite", "spaceflight", "moon",
              "united nations", "world war", "treaty", "independence"),
}


def parse(source: dict[str, Any], content: bytes, local_date: str | None = None) -> list[RawItem]:
    kind = source.get("kind")
    if kind in ("rss", "gnews", "arxiv", "reddit"):
        return _parse_feed(source, content)
    if kind == "hf_papers":
        return _parse_hf(content)
    if kind in ("hn_front", "hn_show"):
        return _parse_hn(source, content)
    if kind == "wikipedia_otd":
        return _parse_otd(content, local_date)
    if kind == "wikipedia_pool":
        return _parse_pool(content)
    if kind == "wikiquote_pool":
        return _parse_quotes(source, content, local_date)
    return []


def _struct_to_iso(st: Any) -> str | None:
    if not st:
        return None
    try:
        return timeutil.iso(dt.datetime.fromtimestamp(calendar.timegm(st), tz=dt.UTC))
    except (OverflowError, ValueError, TypeError):
        return None


def _parse_feed(source: dict[str, Any], content: bytes) -> list[RawItem]:
    feed = feedparser.parse(content)
    items: list[RawItem] = []
    kind = source.get("kind")
    for entry in feed.entries:
        title = textutil.strip_html(entry.get("title"))
        link = entry.get("link") or ""
        if not title or not link:
            continue
        summary = entry.get("summary") or entry.get("description") or ""
        if not summary and entry.get("content"):
            summary = entry["content"][0].get("value", "")
        summary = textutil.strip_html(summary)
        publisher = source.get("name")
        if kind == "gnews":
            src = entry.get("source") or {}
            publisher = src.get("title") or publisher
            title = textutil.strip_publisher_suffix(title)
            # Google News summaries repeat the headline and publisher; drop them.
            if textutil.title_key(summary).startswith(textutil.title_key(title)[:40]):
                summary = ""
        if kind == "reddit":
            summary = re.sub(r"submitted by\s+/u/\S+.*$", "", summary).strip()
        if kind == "arxiv":
            title = textutil.normalize_ws(title)
            link = link.replace("http://", "https://")
        published = _struct_to_iso(entry.get("published_parsed") or entry.get("updated_parsed"))
        lang = source.get("lang") or textutil.detect_lang(title)
        items.append({
            "url": link,
            "title": title,
            "summary": textutil.truncate(summary, 700),
            "published_at": published,
            "lang": lang if lang in ("en", "hi") else textutil.detect_lang(title),
            "publisher": publisher,
            "signals": {},
        })
    return items


def _parse_hf(content: bytes) -> list[RawItem]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    items: list[RawItem] = []
    rows = data if isinstance(data, list) else data.get("papers", [])
    for rank, row in enumerate(rows, 1):
        paper = row.get("paper") or row
        pid = paper.get("id")
        title = textutil.normalize_ws(paper.get("title") or row.get("title"))
        if not pid or not title:
            continue
        items.append({
            "url": f"https://huggingface.co/papers/{pid}",
            "title": title,
            "summary": textutil.truncate(paper.get("summary") or paper.get("ai_summary") or "", 700),
            "published_at": timeutil.iso(timeutil.parse(row.get("publishedAt") or paper.get("publishedAt"))),
            "lang": "en",
            "publisher": "Hugging Face papers",
            "signals": {"hf_upvotes": int(paper.get("upvotes") or 0), "hf_rank": rank,
                        "arxiv_url": f"https://arxiv.org/abs/{pid}"},
        })
    return items


def _parse_hn(source: dict[str, Any], content: bytes) -> list[RawItem]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    # The front page and Show HN keep only stories people noticed; a search keeps anything on topic.
    min_points = {"hn_front": 60, "hn_show": 30}.get(source.get("kind") or "", 5)
    items: list[RawItem] = []
    for hit in data.get("hits", []):
        title = textutil.normalize_ws(hit.get("title") or hit.get("story_title"))
        points = int(hit.get("points") or 0)
        if not title or points < min_points:
            continue
        hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        items.append({
            "url": hit.get("url") or hn_url,
            "title": title,
            "summary": textutil.truncate(textutil.strip_html(hit.get("story_text") or ""), 500),
            "published_at": timeutil.iso(timeutil.parse(hit.get("created_at"))),
            "lang": "en",
            "publisher": textutil.url_host(hit.get("url")) or "Hacker News",
            "signals": {"hn_points": points, "hn_comments": int(hit.get("num_comments") or 0), "hn_url": hn_url},
        })
    return items


def _parse_otd(content: bytes, local_date: str | None) -> list[RawItem]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    published = timeutil.iso(timeutil.parse(local_date)) if local_date else timeutil.now_iso()
    picked: list[RawItem] = []
    for event in data.get("events", []):
        text = textutil.normalize_ws(event.get("text"))
        pages = event.get("pages") or []
        blob = (text + " " + " ".join((p.get("extract") or "") for p in pages[:2])).casefold()
        tier = next((t for t, words in _OTD_KEYWORDS.items() if any(w in blob for w in words)), None)
        if not tier or not text:
            continue
        page = pages[0] if pages else {}
        url = ((page.get("content_urls") or {}).get("desktop") or {}).get("page")
        if not url:
            continue
        year = event.get("year")
        picked.append({
            "url": url,
            "title": textutil.truncate(f"On this day in {year}: {text}", 220),
            "summary": textutil.truncate(page.get("extract") or "", 600),
            "published_at": published,
            "lang": "en",
            "publisher": "Wikipedia",
            "signals": {"otd_year": year, "otd_tier": tier},
        })
    order = {"bihar": 0, "india": 1, "world": 2}
    picked.sort(key=lambda it: order[it["signals"]["otd_tier"]])
    return picked[:8]


def _parse_pool(content: bytes) -> list[RawItem]:
    """A story pool's batch (sources.pool_titles): each article's lead section, as an evergreen item. It has no
    publication date: it isn't news, and the drafter mustn't present it as today's."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    pages = (data.get("query") or {}).get("pages") if isinstance(data, dict) else None
    if isinstance(pages, dict):  # formatversion=1 keys pages by id
        pages = list(pages.values())
    items: list[RawItem] = []
    for page in pages or []:
        if not isinstance(page, dict) or page.get("missing") or page.get("invalid"):
            continue
        title = textutil.normalize_ws(page.get("title"))
        extract = textutil.normalize_ws(page.get("extract"))
        if not title or len(extract) < 120:
            continue
        url = page.get("fullurl") or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        desc = textutil.normalize_ws(page.get("description"))
        if desc and not desc.casefold().startswith(("wikimedia", "topics referred to")):
            title = f"{title}: {desc}"
        items.append({
            "url": url,
            "title": textutil.truncate(title, 220),
            "summary": textutil.truncate(extract, 1500),
            "published_at": None,
            "lang": "en",
            "publisher": "Wikipedia",
            "signals": {"evergreen": 1},
        })
    return items


def _parse_quotes(source: dict[str, Any], content: bytes, local_date: str | None) -> list[RawItem]:
    """The day's quotes (sources.todays_quotes) found word for word on their author's Wikiquote page, outside the
    misattributed, disputed and "about" sections. A quote that isn't there is left out and counted in the log, so
    a misattributed or misremembered quote never reaches a card."""
    from .. import log, pools
    from .sources import todays_quotes

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    query = (data.get("query") or {}) if isinstance(data, dict) else {}
    # A page asked for by another name: the pool's title -> the page's title.
    renamed = {r.get("from"): r.get("to") for r in [*(query.get("normalized") or []), *(query.get("redirects") or [])]
               if isinstance(r, dict)}
    pages: dict[str, dict[str, Any]] = {}
    raw_pages = query.get("pages") or []
    for page in raw_pages.values() if isinstance(raw_pages, dict) else raw_pages:
        if isinstance(page, dict) and page.get("title") and not page.get("missing"):
            pages[page["title"]] = page
    quotes = todays_quotes(local_date, int(source.get("max_items") or 6))
    items: list[RawItem] = []
    missing: list[str] = []
    for q in quotes:
        title = q["page"]
        for _ in range(3):
            title = renamed.get(title, title)
        page = pages.get(title)
        wikitext = _page_text(page) if page else ""
        if not wikitext or not pools.found_in(q["text"], wikitext):
            missing.append(q["id"])
            continue
        url = page.get("fullurl") or f"https://en.wikiquote.org/wiki/{title.replace(' ', '_')}"
        who = pools.lead_sentence(wikitext)
        items.append({
            "url": url,
            # Each quote is its own item, though several can share an author's page.
            "canonical": f"{textutil.canonical_url(url)}#q-{q['id']}",
            "title": textutil.truncate(f"\u201c{q['text']}\u201d \u2014 {q['by']}", 240),
            "summary": textutil.truncate(
                f"{q['by']}: \u201c{q['text']}\u201d (word for word on Wikiquote's page for {title}). {who}".strip(), 900),
            "published_at": None,
            "lang": "en",
            "publisher": "Wikiquote",
            "signals": {"evergreen": 1, "quote": 1, "x_only": 1, "solo": 1},
        })
    log.info(f"quotes: {len(items)} verified, {len(missing)} not found on Wikiquote"
             + (f" ({', '.join(missing)})" if missing else ""))
    return items


def _page_text(page: dict[str, Any]) -> str:
    revs = page.get("revisions") or []
    if not revs or not isinstance(revs[0], dict):
        return ""
    rev = revs[0]
    main = ((rev.get("slots") or {}).get("main") or {}) if isinstance(rev.get("slots"), dict) else {}
    return str(main.get("content") or main.get("*") or rev.get("content") or rev.get("*") or "")
