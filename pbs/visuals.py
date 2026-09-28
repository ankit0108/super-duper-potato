"""Visuals for a post: a carousel, flowchart, comparison, numbered list, big number or quote card.

The model writes the content, from the post and its sources only; the desk draws it as SVG in a fixed style and
exports PNG images or a PDF carousel. There is no image model, so every word and figure on a visual can be checked
like a draft: blocklist terms stop it, and figures the sources don't contain are flagged.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import draft, guardrails, log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import LLMRequest

KINDS = ("carousel", "flow", "compare", "list", "stat", "quote")
KIND_LABEL = {"carousel": "carousel", "flow": "flowchart", "compare": "comparison", "list": "numbered list",
              "stat": "big number", "quote": "quote card"}
# Fewest and most items per kind, and length caps for item titles and bodies (what fits the drawing).
LIMITS = {"carousel": (3, 8), "flow": (3, 7), "compare": (2, 2), "list": (3, 7), "stat": (1, 1), "quote": (1, 1)}
TITLE_MAX = {"carousel": 70, "flow": 40, "compare": 30, "list": 60, "stat": 16, "quote": 60}
BODY_MAX = {"carousel": 240, "flow": 100, "compare": 70, "list": 120, "stat": 140, "quote": 240}
COMPARE_POINTS = 5

KIND_RULES = {
    "carousel": ("a document carousel: 4 to 8 slides after the cover (the cover is \"title\" and \"subtitle\"). "
                 "Each slide: a heading of at most 60 characters and one to three short sentences (at most 220 "
                 "characters). One idea per slide; the last slide is the takeaway."),
    "flow": ("a flowchart of a process: 3 to 7 steps in order. Each step: a label of at most 35 characters and "
             "one short line of at most 90 characters."),
    "compare": ("a two-column comparison (before and after, demo and production, myth and reality): exactly 2 "
                "items. Each: a column heading of at most 25 characters and 3 to 5 points in \"body\", one per "
                "line, each at most 60 characters."),
    "list": ("a numbered list: 3 to 7 items. Each: a heading of at most 50 characters and one line of at most "
             "110 characters."),
    "stat": ("one big number: exactly 1 item. Its title is the figure exactly as the sources give it (like 41%), "
             "its body says what it measures, at most 120 characters."),
    "quote": ("a quote card: exactly 1 item. Its body is a sentence quoted word for word from the sources (at "
              "most 220 characters), its title says who said it."),
}
# X attaches at most four images to a post: a cover and three slides.
X_CAROUSEL_RULE = ("a carousel of images: exactly 3 slides after the cover (X shows at most four images; the cover is "
                   "\"title\" and \"subtitle\"). Each slide: a heading of at most 50 characters and one or two short "
                   "sentences (at most 160 characters). The last slide is the takeaway.")
X_CAROUSEL_SLIDES = 3
AUTO_RULE = ("Pick the kind that suits the post best: carousel for a framework or several points (best on "
             "LinkedIn); flow for a process or pipeline; compare for a contrast; list for tips or lessons; stat "
             "when one figure carries the post; quote when a line from a source carries it.")


class _ItemOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = ""
    body: str = ""

    @field_validator("title", "body", mode="before")
    @classmethod
    def _text(cls, v: Any) -> str:
        if isinstance(v, list):
            return "\n".join(str(x) for x in v)
        return "" if v is None else str(v)


class VisualOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str = ""
    title: str = ""
    subtitle: str | None = None
    items: list[_ItemOut] = Field(default_factory=list)
    caption: str | None = None
    alt_text: str = ""
    sources: list[int] = Field(default_factory=list)

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, v: Any) -> Any:
        out = []
        for it in v or []:
            if isinstance(it, str) and it.strip():
                out.append({"title": it})
            elif isinstance(it, dict):
                if not it.get("body") and it.get("points"):  # a comparison column written as a list of points
                    it = {**it, "body": it["points"]}
                out.append(it)
        return out

    @field_validator("sources", mode="before")
    @classmethod
    def _sources(cls, v: Any) -> Any:
        return [int(x) for x in v or [] if isinstance(x, int) or (isinstance(x, str) and x.strip().isdigit())]


def _line(text: str | None, limit: int) -> str:
    return textutil.truncate(draft.clean_text(text).replace("\n", " "), limit)


def _points(text: str | None, limit: int) -> str:
    lines = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", ln) for ln in draft.clean_text(text).split("\n")]
    return "\n".join(textutil.truncate(ln, limit) for ln in lines if ln.strip())


def clean(out: VisualOut, want: str, n_sources: int, platform: str = "linkedin") -> dict[str, Any]:
    """Fit the model's visual to what the desk can draw: known kind, item counts and lengths. Raises ValueError
    when there isn't enough to draw."""
    kind = want if want in KINDS else (out.kind if out.kind in KINDS else "carousel")
    fewest, most = LIMITS[kind]
    if kind == "carousel" and platform == "x":
        most = X_CAROUSEL_SLIDES
    items: list[dict[str, str]] = []
    for it in out.items:
        title = _line(it.title, TITLE_MAX[kind])
        if kind == "compare":
            body = "\n".join(_points(it.body, BODY_MAX[kind]).split("\n")[:COMPARE_POINTS])
        else:
            body = _line(it.body, BODY_MAX[kind])
        if title or body:
            items.append({"title": title, "body": body})
    items = items[:most]
    if len(items) < fewest:
        raise ValueError(f"a {kind} needs at least {fewest} items, got {len(items)}")
    title = _line(out.title, 90)
    return {
        "kind": kind,
        "title": title,
        "subtitle": _line(out.subtitle, 140) or None,
        "items": items,
        "caption": _line(out.caption, 160) or None,
        "alt_text": textutil.truncate(draft.clean_text(out.alt_text), 600),
        "sources": sorted({i for i in out.sources if 0 <= i < n_sources}),
    }


def visual_text(visual: dict[str, Any], with_alt: bool = True) -> str:
    parts = [visual.get("title") or "", visual.get("subtitle") or "", visual.get("caption") or ""]
    for it in visual.get("items") or []:
        parts += [it.get("title") or "", it.get("body") or ""]
    if with_alt:
        parts.append(visual.get("alt_text") or "")
    return "\n".join(p for p in parts if p)


def default_alt(visual: dict[str, Any]) -> str:
    """A plain description when the model gave none: what it shows, then its text in reading order."""
    items = visual.get("items") or []
    lead = f"{KIND_LABEL[visual['kind']].capitalize()}: {visual.get('title') or ''}".rstrip(": ")
    body = "; ".join(" ".join(p for p in (it.get("title"), (it.get("body") or "").replace("\n", ", ")) if p)
                     for it in items)
    return textutil.truncate(f"{lead}. {body}", 600)


def post_text(card: dict[str, Any]) -> str:
    current = card.get("working") or card.get("draft") or {}
    posts = [p for p in current.get("posts") or [] if p and p.strip()]
    return "\n\n".join(posts) if posts else (current.get("text") or "")


def make_visual(ctx: Ctx, card: dict[str, Any], work: dict[str, Any]) -> dict[str, Any]:
    """Write the visual for the card's current text (his edits included) and keep it if it passes the checks."""
    want = work.get("visual_kind") or "auto"
    text = post_text(card)
    if not text.strip():
        raise ValueError("no draft to draw from")
    sources = card.get("sources") or []
    rules = {**KIND_RULES, **({"carousel": X_CAROUSEL_RULE} if card["platform"] == "x" else {})}
    rule = (f"Make {rules[want]}" if want in KINDS else
            AUTO_RULE + " What each kind needs:\n" + "\n".join(f"- {k}: {v}" for k, v in rules.items()))
    size = ("1080×1350, portrait (a LinkedIn image or document)" if card["platform"] == "linkedin"
            else "1600×900, landscape (an image on X)")
    material = {
        "post": text,
        "topic": card.get("title"),
        "angle": card.get("angle"),
        "sources": [{"index": i, "title": s.get("title"), "publisher": s.get("publisher"),
                     "date": (s.get("published_at") or "")[:10] or None, "summary": s.get("summary")}
                    for i, s in enumerate(sources)],
    }
    prompt = prompting.render("visual", display_name=ctx.settings.display_name,
                              platform_label=draft.PLATFORM_LABEL[card["platform"]], kind_rule=rule, size=size,
                              note=(work.get("note") or "").strip() or "(none)", input_json=material)
    personal = card.get("mode") == "interview" or bool(card.get("answers")) or bool(card.get("working"))
    req = LLMRequest(task="visual", system=draft._system(ctx), prompt=prompt, max_output_tokens=2000,
                     personal=personal, prompt_version=prompting.version("visual"))
    out, _ = ctx.llm.call_json(req, VisualOut)
    visual = clean(out, want, len(sources), card["platform"])
    visual["title"] = visual["title"] or textutil.truncate(card.get("title"), 90)
    visual["alt_text"] = visual["alt_text"] or default_alt(visual)
    now = timeutil.now_iso()
    card["work"] = None
    card["updated_at"] = now
    blocked = guardrails.find_terms(visual_text(visual), ctx.blocklist)
    if blocked:
        flags = dict(card.get("flags") or {})
        note = "The visual mentioned a term from your blocklist, so it wasn't kept. Ask for another one."
        flags["notes"] = [*[n for n in flags.get("notes") or [] if n != note], note]
        card["flags"] = flags
        draft.save_card(ctx, card)
        draft.log_interaction(ctx, "visual_blocked", card, kind=visual["kind"])
        ctx.run.note(f"Visual for card {card['id']} blocked (blocklist match)")
        return card
    # A source line may name the publisher and date, so those count as evidence too.
    cited = " ".join(f"{s.get('publisher') or ''} {(s.get('published_at') or '')[:10]}" for s in sources)
    evidence = f"{draft.evidence_text(card)}\n{text}\n{cited}"
    visual["unsourced"] = guardrails.unsourced_numbers(visual_text(visual, with_alt=False), evidence)
    visual["created_at"] = now
    card["visual"] = visual
    if (card.get("working") or {}).get("visual"):
        card["working"] = {**card["working"], "visual": None}  # a new visual replaces his edits of the old one
    draft.save_card(ctx, card)
    draft.log_interaction(ctx, "visual_created", card, kind=visual["kind"], requested=want,
                          items=len(visual["items"]), unsourced=len(visual["unsourced"]))
    log.info(f"visuals: {visual['kind']} with {len(visual['items'])} items for a {card['platform']} card")
    return card
