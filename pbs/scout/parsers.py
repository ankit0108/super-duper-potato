"""Turn fetched bytes into raw items: {url, title, summary, published_at, lang, publisher, signals}."""

from __future__ import annotations

import calendar
import datetime as dt
import html
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


# Sources that bring trending words, not stories (trends24 for X, Bluesky): they lift matching topics instead of
# becoming items of their own (scouting.save_terms, rank.prescore).
TERM_KINDS = ("trends24", "bsky_trends")


def parse(source: dict[str, Any], content: bytes, local_date: str | None = None) -> list[RawItem]:
    kind = source.get("kind")
    if kind in ("rss", "gnews", "arxiv", "reddit"):
        return _parse_feed(source, content)
    if kind == "hf_papers":
        return _parse_hf(content)
    if kind in ("hn_front", "hn_show", "hn_ask"):
        return _parse_hn(source, content)
    if kind == "reddit_json":
        return _parse_reddit(source, content)
    if kind == "mastodon_links":
        return _parse_mastodon_links(content)
    if kind == "gtrends":
        return _parse_gtrends(source, content)
    if kind == "trends24":
        return _parse_trends24(content)
    if kind == "bsky_trends":
        return _parse_bsky_trends(content)
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
    min_points = {"hn_front": 60, "hn_show": 30, "hn_ask": 40}.get(source.get("kind") or "", 5)
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


def _json(content: bytes) -> Any:
    try:
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


_PICTURE_HOSTS = ("i.redd.it", "v.redd.it", "i.imgur.com", "imgur.com", "reddit.com/gallery")


def _parse_reddit(source: dict[str, Any], content: bytes) -> list[RawItem]:
    """A subreddit's top posts of the day (`/top.json?t=day`), with the score and the comment count, so what
    people are actually talking about ranks higher. Picture posts keep only a title we can't see behind, so
    they're kept only when the title says enough on its own."""
    data = _json(content)
    children = ((data or {}).get("data") or {}).get("children") if isinstance(data, dict) else None
    min_score = int((source.get("extra") or {}).get("min_score") or 100)
    sub = ""
    items: list[RawItem] = []
    for child in children or []:
        d = (child or {}).get("data") or {}
        title = textutil.normalize_ws(d.get("title"))
        score = int(d.get("score") or 0)
        if not title or d.get("over_18") or d.get("stickied") or score < min_score:
            continue
        sub = d.get("subreddit_name_prefixed") or sub
        thread = f"https://www.reddit.com{d.get('permalink') or ''}"
        link = str(d.get("url_overridden_by_dest") or d.get("url") or "")
        picture = d.get("post_hint") in ("image", "hosted:video") or any(h in link for h in _PICTURE_HOSTS)
        if picture and len(title.split()) < 6:
            continue
        external = bool(link) and not d.get("is_self") and not picture and "reddit.com" not in link
        body = textutil.strip_html(d.get("selftext") or "")
        if picture:
            body = f"A picture post on {sub}; only its title is known: {title}"
        created = d.get("created_utc")
        published = timeutil.iso(dt.datetime.fromtimestamp(float(created), tz=dt.UTC)) if created else None
        items.append({
            "url": link if external else thread,
            "title": title,
            "summary": textutil.truncate(body, 700),
            "published_at": published,
            "lang": "en",
            "publisher": (textutil.url_host(link) if external else None) or sub or source.get("name"),
            "signals": {"reddit_score": score, "reddit_comments": int(d.get("num_comments") or 0),
                        "discussion_url": thread},
        })
    return items


def _parse_mastodon_links(content: bytes) -> list[RawItem]:
    """Links people are sharing most on Mastodon (`/api/v1/trends/links`), with how many accounts shared each
    over the last two days."""
    data = _json(content)
    items: list[RawItem] = []
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict) or not row.get("url") or not row.get("title"):
            continue
        history = [h for h in (row.get("history") or []) if isinstance(h, dict)][:2]
        accounts = sum(int(h.get("accounts") or 0) for h in history)
        published = timeutil.iso(timeutil.parse(row.get("published_at"))) if row.get("published_at") else None
        items.append({
            "url": row["url"],
            "title": textutil.normalize_ws(textutil.strip_html(row["title"])),
            "summary": textutil.truncate(textutil.strip_html(row.get("description") or ""), 600),
            "published_at": published,
            "lang": row.get("language") if row.get("language") in ("en", "hi") else "en",
            "publisher": row.get("provider_name") or textutil.url_host(row["url"]),
            "signals": {"mastodon_accounts": accounts},
        })
    return items


def _tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}>(.*?)</{name}>", block, re.S)
    if not m:
        return ""
    raw = m.group(1).strip()
    if raw.startswith("<![CDATA["):
        raw = raw[9:].removesuffix("]]>")
    return textutil.normalize_ws(html.unescape(textutil.strip_html(raw)))


def _parse_gtrends(source: dict[str, Any], content: bytes) -> list[RawItem]:
    """Google Trends' daily searches (`trends.google.com/trending/rss?geo=…`): each trending search with the
    news story behind it, so a search spike arrives as the story people are looking up."""
    text = content.decode("utf-8", "replace")
    geo = (source.get("extra") or {}).get("geo") or source.get("gl") or ""
    items: list[RawItem] = []
    for block in re.findall(r"<item>(.*?)</item>", text, re.S):
        term = _tag(block, "title")
        news = re.search(r"<ht:news_item>(.*?)</ht:news_item>", block, re.S)
        story = news.group(1) if news else ""
        url = _tag(story, "ht:news_item_url")
        if not term or not url.startswith(("http://", "https://")):
            continue
        traffic = int(re.sub(r"\D", "", _tag(block, "ht:approx_traffic")) or 0)
        published = timeutil.iso(timeutil.parse(_tag(block, "pubDate"))) if _tag(block, "pubDate") else None
        items.append({
            "url": url,
            "title": _tag(story, "ht:news_item_title") or term,
            "summary": textutil.truncate(f"Trending on Google Search{f' in {geo}' if geo else ''}: \u201c{term}\u201d"
                                         f"{f' ({traffic:,}+ searches)' if traffic else ''}. "
                                         f"{_tag(story, 'ht:news_item_snippet')}", 600),
            "published_at": published,
            "lang": "en",
            "publisher": _tag(story, "ht:news_item_source") or "Google Trends",
            "signals": {"search_traffic": traffic, "trend_term": term},
        })
    return items


def _parse_trends24(content: bytes) -> list[RawItem]:
    """The latest hour's trending topics on X for a country, from trends24.in (best effort: it's a web page)."""
    text = content.decode("utf-8", "replace")
    start = text.find("trend-card__list")
    block = text[start:text.find("</ol>", start)] if start >= 0 else ""
    terms = [html.unescape(t).strip() for t in re.findall(r'class="trend-link"[^>]*>([^<]+)<', block)]
    return [{"term": t, "where": "x"} for t in dict.fromkeys(terms) if t][:30]


def _parse_bsky_trends(content: bytes) -> list[RawItem]:
    """Bluesky's trending topics (`app.bsky.unspecced.getTrendingTopics`)."""
    data = _json(content)
    rows = (data or {}).get("topics") if isinstance(data, dict) else None
    terms = [textutil.normalize_ws(r.get("displayName") or r.get("topic")) for r in rows or [] if isinstance(r, dict)]
    return [{"term": t, "where": "bluesky"} for t in dict.fromkeys(terms) if t][:30]


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
