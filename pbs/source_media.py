"""Pictures from the sources a draft was written from: charts, graphs, diagrams, tables, screenshots and photos.

After a draft is written, `collect` looks at the card's top sources once: the pictures their feeds carried
(captured at parse time, `signals.images`) and the ones on the article page (og:image, figures with their
captions, images inside the article). It downloads them (size-capped, resized with Pillow), asks the vision model
what each one is and for alt text, drops logos, ads and site furniture, and attaches up to `media.per_card` to the
post, charts and diagrams first. A couple more stay in the card's pool ("Also in the sources") for one tap.

Ankit decides on the desk what goes with the post (the `card.media` event): what he keeps, removes and posts is
logged per kind, so the order, and whether a kind is attached at all, follows what he keeps (`preferences`). The
publisher is credited in the first comment (`credit_line`), and the line follows the pictures as they change.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import io
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel

from . import log, prompting, timeutil
from .context import Ctx
from .llm.base import LLMRequest
from .scout.fetch import FetchJob, fetch_all, no_sleep

SOURCES_DIR = "media/sources"
UPLOADS_DIR = "media/uploads"
KINDS = ("chart", "graph", "diagram", "table", "screenshot", "photo", "illustration", "logo", "ad", "other")
DATA_KINDS = frozenset({"chart", "graph", "diagram", "table"})
DROP_KINDS = frozenset({"logo", "ad"})
# Before he has decided enough of a kind: how likely he is to keep it (charts first, then diagrams...).
PRIOR = {"chart": 0.7, "graph": 0.7, "diagram": 0.65, "table": 0.6, "screenshot": 0.5, "illustration": 0.4,
         "photo": 0.4, "other": 0.3}
# A reply or a quote-post carries the original post (and its media); a quote card is a picture of its own.
SKIP_FORMATS = frozenset({"x_reply", "x_quote"})
VISION_KEY = "source_media_vision"
MAX_CANDIDATES = 8
UA = "Mozilla/5.0 (compatible; PBS/0.2; personal research digest)"
_JUNK = frozenset({
    "logo", "logos", "icon", "icons", "favicon", "avatar", "avatars", "sprite", "sprites", "badge", "badges", "pixel",
    "emoji", "emojis", "gravatar", "ads", "advert", "adverts", "advertisement", "placeholder", "spacer", "author",
    "authors", "headshot", "headshots", "button", "buttons", "share", "social", "1x1", "blank", "transparent",
    "tracking", "tracker", "loader", "spinner", "default", "profile",
})
_KIND_HINTS = (
    ("chart", re.compile(r"\b(chart|charts|graph|plot|benchmark|leaderboard|accuracy|growth|trend|percent|survey|"
                         r"scores?|results?|data)\b|%")),
    ("diagram", re.compile(r"\b(diagram|architecture|flow|flowchart|pipeline|framework|overview|schematic|"
                           r"workflow|fig\.?|figure)\b")),
    ("table", re.compile(r"\btable\b")),
    ("screenshot", re.compile(r"\b(screenshot|screen shot|screen|ui|dashboard|interface|demo)\b")),
)


# --- where the pictures are ---------------------------------------------------------------------------------------

@dataclass
class Candidate:
    url: str
    source_url: str
    publisher: str | None = None
    title: str | None = None
    caption: str | None = None
    alt: str | None = None
    via: str = "page"  # feed, og, figure or article
    data: bytes = b""
    prepared: dict[str, Any] = field(default_factory=dict)


def junk(url: str, width: Any = None, height: Any = None) -> bool:
    """Site furniture, not a picture from the story: logos, icons, avatars, tracking pixels, SVG and GIF."""
    if not url or not url.startswith(("http://", "https://")):
        return True
    path = urlsplit(url).path.lower()
    if path.endswith((".svg", ".gif", ".ico", ".bmp")):
        return True
    if _JUNK & set(re.split(r"[^a-z0-9]+", path)):
        return True
    for v in (width, height):
        try:
            if v is not None and str(v).strip() and int(float(str(v).strip().rstrip("px"))) < 300:
                return True
        except ValueError:
            continue
    return False


def best_srcset(srcset: str | None) -> str | None:
    """The largest picture a srcset offers ("a.jpg 480w, b.jpg 1200w" -> b.jpg)."""
    best, size = None, -1.0
    for part in (srcset or "").split(","):
        bits = part.strip().split()
        if not bits:
            continue
        n = 1.0
        if len(bits) > 1:
            m = re.match(r"([\d.]+)([wx])", bits[1])
            n = float(m.group(1)) * (1 if m.group(2) == "w" else 1000) if m else 1.0
        if n > size:
            best, size = bits[0], n
    return best


class _PageImages(HTMLParser):
    """og:image / twitter:image, <figure> images with their <figcaption>, and images inside <article> or <main>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: list[dict[str, str | None]] = []
        self.figures: list[dict[str, str | None]] = []
        self.article: list[dict[str, str | None]] = []
        self.base: str | None = None
        self._depth = 0
        self._figure: list[dict[str, str | None]] | None = None
        self._caption: list[str] | None = None
        self._picture_src: str | None = None
        self._og_alt: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "base" and a.get("href") and not self.base:
            self.base = a["href"]
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src"):
                if a.get("content"):
                    self.meta.append({"url": a["content"], "alt": None})
            elif key in ("og:image:alt", "twitter:image:alt"):
                self._og_alt = a.get("content") or None
        elif tag in ("article", "main"):
            self._depth += 1
        elif tag == "figure":
            self._figure = []
        elif tag == "figcaption" and self._figure is not None:
            self._caption = []
        elif tag == "picture":
            self._picture_src = None
        elif tag == "source" and (a.get("srcset") or a.get("data-srcset")):
            self._picture_src = best_srcset(a.get("srcset") or a.get("data-srcset"))
        elif tag == "img":
            src = (best_srcset(a.get("srcset") or a.get("data-srcset")) or a.get("data-src")
                   or a.get("data-lazy-src") or a.get("data-original") or a.get("src") or self._picture_src)
            if not src or src.startswith("data:"):
                return
            img = {"url": src, "alt": (a.get("alt") or "").strip() or None, "width": a.get("width"),
                   "height": a.get("height")}
            if self._figure is not None:
                self._figure.append(img)
            elif self._depth > 0:
                self.article.append(img)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("article", "main"):
            self._depth = max(0, self._depth - 1)
        elif tag == "figcaption" and self._caption is not None and self._figure is not None:
            text = re.sub(r"\s+", " ", "".join(self._caption)).strip()
            for img in self._figure:
                img["caption"] = text[:300] or None
            self._caption = None
        elif tag == "figure" and self._figure is not None:
            self.figures.extend(self._figure)
            self._figure = None
        elif tag == "picture":
            self._picture_src = None

    def handle_data(self, data: str) -> None:
        if self._caption is not None:
            self._caption.append(data)

    def results(self) -> list[dict[str, Any]]:
        if self.meta and self._og_alt:
            self.meta[0]["alt"] = self._og_alt
        return ([{**m, "via": "og"} for m in self.meta[:1]] + [{**f, "via": "figure"} for f in self.figures]
                + [{**x, "via": "article"} for x in self.article])


def page_images(html: str, page_url: str) -> list[dict[str, Any]]:
    """The pictures on an article page, best first, with absolute URLs and site furniture left out."""
    parser = _PageImages()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 - a broken page gives what was read before it broke
        pass
    base = urljoin(page_url, parser.base) if parser.base else page_url
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for img in parser.results():
        url = urljoin(base, img["url"].strip())
        if url in seen or junk(url, img.get("width"), img.get("height")):
            continue
        # An image in the article with no words about it is often furniture (a share card, an ad slot).
        if img["via"] == "article" and not img.get("alt") and not img.get("width"):
            continue
        seen.add(url)
        out.append({"url": url, "alt": img.get("alt"), "caption": img.get("caption"), "via": img["via"]})
    return out[:MAX_CANDIDATES]


def page_url(url: str) -> str | None:
    """The page to read for a source, or None when there's nothing to read (a Google News redirect)."""
    host = (urlsplit(url).hostname or "").lower()
    if not url.startswith(("http://", "https://")) or host in ("news.google.com",):
        return None
    m = re.match(r"https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", url)
    if m:
        return f"https://arxiv.org/html/{m.group(1)}"  # the paper's figures, as web pages
    if host in ("www.youtube.com", "youtube.com", "youtu.be", "x.com", "twitter.com", "www.linkedin.com"):
        return None  # pages built by script; the feed's thumbnail is what there is
    return url


def feed_images(ctx: Ctx, url: str) -> list[dict[str, Any]]:
    rows = ctx.store.select("items", "url = ?", (url,), limit=1)
    imgs = ((rows[0].get("signals") or {}).get("images") or []) if rows else []
    return [{"url": i["url"], "alt": i.get("alt"), "caption": None, "via": "feed"} for i in imgs
            if isinstance(i, dict) and i.get("url") and not junk(i["url"])]


# --- picking cards --------------------------------------------------------------------------------------------------

def eligible(card: dict[str, Any]) -> bool:
    return (card.get("format") not in SKIP_FORMATS and card.get("post_type") != "quote"
            and bool(card.get("draft")) and any((s.get("url") or "").startswith("http")
                                                for s in card.get("sources") or []))


def _due_cards(ctx: Ctx, limit: int) -> list[dict[str, Any]]:
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=ctx.settings.media.max_age_days))
    # Saved cards are suggested or editing too (saving is a flag, not a status).
    rows = ctx.store.select("cards", "source_media IS NULL AND created_at >= ? AND status IN "
                            "('suggested', 'editing')", (since,))
    rows.sort(key=lambda c: (c.get("rank") or 99, c.get("created_at") or ""))
    return rows[:limit]


# --- downloading and preparing ------------------------------------------------------------------------------------

def prepare(data: bytes, max_side: int) -> dict[str, Any] | None:
    """A picture fit to post: JPEG, PNG or WebP, big enough, not a strip; resized to max_side on the long edge.
    WebP becomes JPEG (LinkedIn doesn't take WebP); a PNG stays PNG when that's small (charts keep sharp text)."""
    from PIL import Image, ImageOps

    try:
        im = Image.open(io.BytesIO(data))
        fmt = im.format
        w, h = im.size
        if fmt not in ("JPEG", "PNG", "WEBP") or w * h > 40_000_000:
            return None
        if max(w, h) < 400 or min(w, h) < 250 or max(w, h) / max(1, min(w, h)) > 3:
            return None
        im.seek(0)
        im = ImageOps.exif_transpose(im)
        im.load()
    except Exception:  # noqa: BLE001 - a broken or cut-off file is no picture
        return None
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    out = io.BytesIO()
    if fmt == "PNG":
        png = im if im.mode in ("RGB", "RGBA", "L", "LA", "P") else im.convert("RGBA")
        png.save(out, "PNG", optimize=True)
        if out.tell() <= 700_000:
            return {"data": out.getvalue(), "content_type": "image/png", "ext": "png", "width": im.size[0],
                    "height": im.size[1]}
        out = io.BytesIO()
    if alpha:
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im.convert("RGBA"), mask=im.convert("RGBA").getchannel("A"))
        im = flat
    im.convert("RGB").save(out, "JPEG", quality=86, optimize=True, progressive=True)
    return {"data": out.getvalue(), "content_type": "image/jpeg", "ext": "jpg", "width": im.size[0],
            "height": im.size[1]}


def _fetch(ctx: Ctx, jobs: list[FetchJob], max_bytes: int) -> dict[str, Any]:
    if not jobs:
        return {}
    m = ctx.settings.media
    results = asyncio.run(fetch_all(jobs, user_agent=UA, timeout=m.timeout_seconds, concurrency=8,
                                    transport=ctx.transport, max_bytes=max_bytes,
                                    **({"sleep": no_sleep} if ctx.transport is not None else {})))
    return {r.key: r for r in results}


# --- what each picture is -------------------------------------------------------------------------------------------

class _VisionImage(BaseModel):
    index: int
    kind: str = "other"
    alt: str = ""
    about_story: bool = True


class _VisionOut(BaseModel):
    images: list[_VisionImage] = []


def guess_kind(c: Candidate) -> str:
    """Without the vision model: the caption, alt text and file name say what a picture is, roughly."""
    text = " ".join(filter(None, [c.caption, c.alt, urlsplit(c.url).path.replace("-", " ").replace("_", " ")]))
    text = text.lower()
    for kind, rx in _KIND_HINTS:
        if rx.search(text):
            return kind
    if "arxiv.org/html" in c.url:
        return "diagram"
    return "photo" if (c.prepared.get("content_type") == "image/jpeg" and c.via in ("og", "feed")) else "other"


def _vision_used(ctx: Ctx) -> int:
    row = ctx.store.get_setting(VISION_KEY) or {}
    return int(row.get("n") or 0) if row.get("day") == ctx.local_date_str() else 0


def _vision_ok(ctx: Ctx) -> bool:
    m = ctx.settings.media
    if not m.vision or _vision_used(ctx) >= m.vision_per_day:
        return False
    reserve = ctx.settings.agents.reserve
    try:
        return ctx.llm.remaining("media_vision") > 0 and ctx.llm.remaining("draft") > reserve
    except Exception:  # noqa: BLE001 - no router, no vision
        return False


def classify(ctx: Ctx, card: dict[str, Any], cands: list[Candidate]) -> tuple[list[dict[str, Any]], bool]:
    """Kind, alt text and whether it's about the story, for each picture: by the vision model when the budget
    allows, else by the caption and file name. Returns (one dict per candidate, whether the model was used)."""
    guesses = [{"kind": guess_kind(c), "alt": (c.caption or c.alt or "")[:200], "about_story": True} for c in cands]
    if not cands or not _vision_ok(ctx):
        return guesses, False
    pictures = [{"index": i, "source": c.title, "publisher": c.publisher, "caption": c.caption, "page_alt": c.alt,
                 "found_in": c.via} for i, c in enumerate(cands)]
    prompt = prompting.render("media_vision", input_json={"story": card.get("title"), "pictures": pictures})
    req = LLMRequest(task="media_vision", system="You describe pictures exactly. Never guess numbers you can't read.",
                     prompt=prompt, images=[(c.prepared["data"], c.prepared["content_type"]) for c in cands],
                     max_output_tokens=1500, prompt_version=prompting.version("media_vision"))
    try:
        out, _ = ctx.llm.call_json(req, _VisionOut)
    except Exception as exc:  # noqa: BLE001 - the pictures still go in, described by their captions
        log.info(f"pictures: vision unavailable for {card['id']} ({type(exc).__name__})")
        return guesses, False
    finally:
        ctx.store.set_setting(VISION_KEY, {"day": ctx.local_date_str(), "n": _vision_used(ctx) + 1})
    for v in out.images:
        if 0 <= v.index < len(guesses):
            kind = v.kind.strip().lower()
            guesses[v.index] = {"kind": kind if kind in KINDS else "other",
                                "alt": re.sub(r"\s+", " ", v.alt).strip()[:200] or guesses[v.index]["alt"],
                                "about_story": v.about_story}
    return guesses, True


# --- what he keeps --------------------------------------------------------------------------------------------------

def preferences(ctx: Ctx, days: int = 90) -> dict[str, dict[str, Any]]:
    """Per kind of picture, over `days`: how many PBS attached, he removed, he added back or uploaded, and posted;
    his keep rate (posted / (posted + removed)); and whether the kind is no longer attached by itself."""
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=days))
    m = ctx.settings.media
    out: dict[str, dict[str, Any]] = {}

    def row(kind: str) -> dict[str, Any]:
        return out.setdefault(kind or "other", {"attached": 0, "removed": 0, "added": 0, "posted": 0})

    rows = ctx.store.select("interactions", "type IN ('media_attached', 'media_removed', 'media_added', "
                            "'media_posted') AND at >= ?", (since,))
    for i in rows:
        data = i.get("data") or {}
        key = {"media_attached": "attached", "media_removed": "removed", "media_added": "added",
               "media_posted": "posted"}[i["type"]]
        for kind in data.get("kinds") or ([data["kind"]] if data.get("kind") else []):
            row(kind)[key] += 1
    for r in out.values():
        decided = r["posted"] + r["removed"]
        r["rate"] = round(r["posted"] / decided, 2) if decided else None
        r["dropped"] = r["removed"] >= m.drop_after and (r["rate"] or 0) <= m.drop_rate
    return out


def summary(ctx: Ctx) -> dict[str, Any]:
    """For the weekly review: what he kept of each kind ("kept 9 of 12 charts")."""
    prefs = preferences(ctx)
    return {kind: {"posted": r["posted"], "removed": r["removed"], "rate": r["rate"], "no_longer_attached":
                   r["dropped"]} for kind, r in sorted(prefs.items()) if r["posted"] or r["removed"]}


def _order(items: list[dict[str, Any]], prefs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    def key(pair: tuple[int, dict[str, Any]]) -> tuple[int, float, int]:
        i, a = pair
        p = prefs.get(a.get("kind") or "other") or {}
        decided = int(p.get("posted") or 0) + int(p.get("removed") or 0)
        rate = p["rate"] if decided >= 3 and p.get("rate") is not None else PRIOR.get(a.get("kind") or "other", 0.3)
        return (1 if p.get("dropped") else 0, -rate, i)

    return [a for _, a in sorted(enumerate(items), key=key)]


# --- the credit line ------------------------------------------------------------------------------------------------

def credit_line(attachments: list[dict[str, Any]]) -> str | None:
    """"Chart: Epoch AI", "Images: The Verge, Epoch AI": who the source pictures going with the post belong to."""
    src = [a for a in attachments or [] if a.get("origin") == "source" and a.get("publisher")]
    if not src:
        return None
    pubs: list[str] = []
    for a in src:
        if a["publisher"] not in pubs:
            pubs.append(a["publisher"])
    kinds = {a.get("kind") or "other" for a in src}
    one = len(src) == 1
    if kinds <= {"chart", "graph"}:
        word = "Chart" if one else "Charts"
    elif kinds <= {"diagram"}:
        word = "Diagram" if one else "Diagrams"
    elif kinds <= DATA_KINDS:
        word = "Figure" if one else "Figures"
    else:
        word = "Image" if one else "Images"
    return f"{word}: {', '.join(pubs)}"


def apply_credit(card: dict[str, Any]) -> None:
    """Put the credit line at the end of the first comment, replacing the one written for the earlier pictures."""
    d = card.get("draft")
    if not isinstance(d, dict) or card.get("format") == "x_reply":
        return
    old = d.get("media_credit")
    lines = (d.get("first_comment") or "").split("\n")
    if old:
        lines = [ln for ln in lines if ln.strip() != old]
    text = "\n".join(lines).rstrip()
    new = credit_line(card.get("attachments") or [])
    if new:
        text = f"{text}\n{new}" if text else new
    d["first_comment"] = text or None
    d["media_credit"] = new


# --- the step -------------------------------------------------------------------------------------------------------

def _candidates(ctx: Ctx, card: dict[str, Any], pages: dict[str, Any]) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()
    for s in (card.get("sources") or [])[:ctx.settings.media.max_sources]:
        url = s.get("url") or ""
        found = feed_images(ctx, url)
        res = pages.get(url)
        if res is not None and res.ok and res.content:
            found += page_images(res.content.decode("utf-8", "replace"), res.url or url)
        for f in found:
            if f["url"] in seen:
                continue
            seen.add(f["url"])
            out.append(Candidate(url=f["url"], source_url=url, publisher=s.get("publisher"), title=s.get("title"),
                                 caption=f.get("caption"), alt=f.get("alt"), via=f["via"]))
    return out[:MAX_CANDIDATES]


def _save(ctx: Ctx, card_id: str, n: int, c: Candidate, info: dict[str, Any]) -> dict[str, Any]:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", card_id)[:64] or "misc"
    rel = f"{SOURCES_DIR}/{safe}/{n}.{c.prepared['ext']}"
    target = ctx.data_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(c.prepared["data"])
    return {"path": rel, "content_type": c.prepared["content_type"], "width": c.prepared["width"],
            "height": c.prepared["height"], "origin": "source", "source_url": c.source_url,
            "publisher": c.publisher, "caption": c.caption, "alt": info["alt"] or None, "kind": info["kind"]}


def collect(ctx: Ctx, limit: int | None = None) -> dict[str, int]:
    """Look once at the pictures in the sources of new drafts, and attach them. Returns counts for the run log."""
    from . import draft

    m = ctx.settings.media
    stats = {"cards": 0, "found": 0, "attached": 0, "vision": 0}
    if not m.enabled:
        return stats
    cards = _due_cards(ctx, m.max_cards_per_run if limit is None else limit)
    todo = [c for c in cards if eligible(c) and not c.get("attachments")]
    for c in cards:
        if c not in todo:
            # Nothing to look for (a reply, a quote card, a Studio post with its own pictures): looked at all the same.
            c["source_media"] = list(c.get("attachments") or [])
            draft.save_card(ctx, c)
    if not todo:
        return stats
    page_jobs: dict[str, FetchJob] = {}
    for c in todo:
        for s in (c.get("sources") or [])[:m.max_sources]:
            url = s.get("url") or ""
            target = page_url(url)
            if target and url not in page_jobs:
                page_jobs[url] = FetchJob(key=url, url=target)
    pages = _fetch(ctx, list(page_jobs.values()), m.page_bytes)
    found = {c["id"]: _candidates(ctx, c, pages) for c in todo}
    image_jobs = {cand.url: FetchJob(key=cand.url, url=cand.url) for cands in found.values() for cand in cands}
    images = _fetch(ctx, list(image_jobs.values()), m.image_bytes)
    prefs = preferences(ctx)
    for card in todo:
        stats["cards"] += 1
        kept: list[Candidate] = []
        hashes: set[str] = set()
        for cand in found[card["id"]]:
            res = images.get(cand.url)
            if res is None or not res.ok or not res.content or len(res.content) >= m.image_bytes:
                continue
            digest = hashlib.sha256(res.content).hexdigest()
            if digest in hashes:
                continue
            prepared = prepare(res.content, m.max_side)
            if not prepared:
                continue
            hashes.add(digest)
            cand.prepared = prepared
            kept.append(cand)
        infos, used = classify(ctx, card, kept[:6])
        stats["vision"] += 1 if used else 0
        pool = [(c, info) for c, info in zip(kept[:6], infos, strict=True)
                if info["kind"] not in DROP_KINDS and info["about_story"]]
        ordered = _order([{**info, "_i": i} for i, (_c, info) in enumerate(pool)], prefs)
        attach = [a for a in ordered if not (prefs.get(a["kind"]) or {}).get("dropped")][:m.per_card]
        extra = [a for a in ordered if a not in attach][:m.extra]
        saved: dict[int, dict[str, Any]] = {}
        for n, a in enumerate([*attach, *extra], start=1):
            c, info = pool[a["_i"]]
            saved[a["_i"]] = _save(ctx, card["id"], n, c, info)
        card["attachments"] = [saved[a["_i"]] for a in attach]
        card["source_media"] = [saved[a["_i"]] for a in [*attach, *extra]]
        apply_credit(card)
        draft.save_card(ctx, card)
        stats["found"] += len(card["source_media"])
        stats["attached"] += len(card["attachments"])
        if card["attachments"]:
            draft.log_interaction(ctx, "media_attached", card, kinds=[a["kind"] for a in card["attachments"]],
                                  publishers=sorted({a.get("publisher") or "" for a in card["attachments"]} - {""}))
    log.info(f"pictures: looked at {stats['cards']} card(s), kept {stats['found']} picture(s), attached "
             f"{stats['attached']}, vision {stats['vision']}")
    return stats
