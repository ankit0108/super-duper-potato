"""Visuals for a post: a carousel, flowchart, comparison, numbered list, big number, quote card or AI image.

The model writes the content, from the post and its sources only; the desk draws it as SVG in a fixed style and
exports PNG images or a PDF carousel. An image model (images.py) only ever makes pictures: the illustration of an
"image" visual, or the background of a carousel cover, big number or quote card. It never draws words, so every
word and figure on a visual can still be checked like a draft: blocklist terms stop it, and figures the sources
don't contain are flagged.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import draft, guardrails, images, log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import LLMRequest

KINDS = ("carousel", "flow", "compare", "list", "stat", "quote", "image")
KIND_LABEL = {"carousel": "carousel", "flow": "flowchart", "compare": "comparison", "list": "numbered list",
              "stat": "big number", "quote": "quote card", "image": "AI image"}
# Fewest and most items per kind, and length caps for item titles and bodies (what fits the drawing).
LIMITS = {"carousel": (3, 8), "flow": (3, 7), "compare": (2, 2), "list": (3, 7), "stat": (1, 1), "quote": (1, 1),
          "image": (0, 0)}
TITLE_MAX = {"carousel": 70, "flow": 40, "compare": 30, "list": 60, "stat": 16, "quote": 60, "image": 70}
BODY_MAX = {"carousel": 240, "flow": 100, "compare": 70, "list": 120, "stat": 140, "quote": 240, "image": 0}
# Kinds that can have an AI image behind them (the text stays on top, drawn by the desk).
BACKGROUND_KINDS = ("carousel", "stat", "quote")
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
    "image": ("an AI illustration for the post, made by an image model from \"image_prompt\": \"items\" is []. "
              "\"title\" is an optional short headline drawn over the picture (at most 60 characters), or \"\"."),
}
IMAGE_RULES = {
    "image": ("\"image_prompt\": what the picture shows, in one or two sentences: a concrete scene or visual "
              "metaphor for the post's main point (objects, setting, composition, mood). It can't contain words, "
              "letters, numbers, labelled charts, logos or brand names, or real or named people; never mention "
              "{name}, his employer or any company."),
    "background": ("\"image_prompt\": a quiet background picture that suits the post (an abstract shape, texture or "
                   "simple scene tied to its subject), with calm empty space where the words will sit. No words, "
                   "letters, numbers, logos or people."),
}
# X attaches at most four images to a post: a cover and three slides.
X_CAROUSEL_RULE = ("a carousel of images: exactly 3 slides after the cover (X shows at most four images; the cover is "
                   "\"title\" and \"subtitle\"). Each slide: a heading of at most 50 characters and one or two short "
                   "sentences (at most 160 characters). The last slide is the takeaway.")
X_CAROUSEL_SLIDES = 3
AUTO_RULE = ("Pick the kind that suits the post best: carousel for a framework or several points (best on "
             "LinkedIn); flow for a process or pipeline; compare for a contrast; list for tips or lessons; stat "
             "when one figure carries the post; quote when a line from a source carries it. (Not \"image\": "
             "that one is only made when asked for.)")


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
    image_prompt: str = ""

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
    kind = want if want in KINDS else (out.kind if out.kind in KINDS and out.kind != "image" else "carousel")
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


def _note(card: dict[str, Any], note: str) -> None:
    flags = dict(card.get("flags") or {})
    flags["notes"] = [*[n for n in flags.get("notes") or [] if n != note], note]
    card["flags"] = flags


def make_visual(ctx: Ctx, card: dict[str, Any], work: dict[str, Any]) -> dict[str, Any]:
    """Write the visual for the card's current text (his edits included) and keep it if it passes the checks.
    An AI image ("image" visuals, or a background he asked for) comes from images.py; when no image service can
    make one, an illustration isn't kept and a background is left out, and the card says why."""
    want = work.get("visual_kind") or "auto"
    picture = "image" if want == "image" else "background" if work.get("ai_background") else None
    text = post_text(card)
    if not text.strip():
        raise ValueError("no draft to draw from")
    sources = card.get("sources") or []
    rules = {**KIND_RULES, **({"carousel": X_CAROUSEL_RULE} if card["platform"] == "x" else {})}
    if want in KINDS:
        rule = f"Make {rules[want]}"
    else:
        # A background picture only goes behind a carousel cover, a big number or a quote, so pick among those.
        options = [k for k in rules if k in BACKGROUND_KINDS] if picture == "background" else [k for k in rules if k != "image"]
        rule = (AUTO_RULE + (" A background picture was asked for, so pick carousel, stat or quote."
                             if picture == "background" else "")
                + " What each kind needs:\n" + "\n".join(f"- {k}: {rules[k]}" for k in options))
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
    image_rule = IMAGE_RULES[picture].format(name=ctx.settings.display_name) if picture else ""
    prompt = prompting.render("visual", display_name=ctx.settings.display_name,
                              platform_label=draft.PLATFORM_LABEL[card["platform"]], kind_rule=rule, size=size,
                              note=(work.get("note") or "").strip() or "(none)", input_json=material,
                              image_rule=f"- {image_rule}" if image_rule else "",
                              image_field=', "image_prompt": "…"' if picture else "")
    personal = card.get("mode") == "interview" or bool(card.get("answers")) or bool(card.get("working"))
    req = LLMRequest(task="visual", system=draft._system(ctx), prompt=prompt, max_output_tokens=2000,
                     personal=personal, prompt_version=prompting.version("visual"))
    out, _ = ctx.llm.call_json(req, VisualOut)
    visual = clean(out, want, len(sources), card["platform"])
    if visual["kind"] != "image":  # an illustration may go without a headline
        visual["title"] = visual["title"] or textutil.truncate(card.get("title"), 90)
    visual["alt_text"] = visual["alt_text"] or default_alt(visual)
    now = timeutil.now_iso()
    card["work"] = None
    card["updated_at"] = now
    # The picture's description goes to an image service, so it's checked too.
    blocked = guardrails.find_terms(f"{visual_text(visual)}\n{out.image_prompt}", ctx.blocklist)
    if blocked:
        _note(card, "The visual mentioned a term from your blocklist, so it wasn't kept. Ask for another one.")
        draft.save_card(ctx, card)
        draft.log_interaction(ctx, "visual_blocked", card, kind=visual["kind"])
        ctx.run.note(f"Visual for card {card['id']} blocked (blocklist match)")
        return card
    if picture == "background" and visual["kind"] not in BACKGROUND_KINDS:
        _note(card, f"AI backgrounds go behind a carousel cover, a big number or a quote; this visual is a "
                    f"{KIND_LABEL[visual['kind']]}, so it's drawn without one.")
    if picture and (visual["kind"] == "image" or visual["kind"] in BACKGROUND_KINDS):
        width, height = images.size_for(card["platform"])
        idea = out.image_prompt or card.get("angle") or card.get("title") or ""
        try:
            res = images.generate(ctx, images.styled_prompt(ctx, idea, background=visual["kind"] != "image",
                                                            accent=ctx.settings.visuals.accent),
                                  width, height, card_id=card["id"], purpose=picture)
        except images.ImagesUnavailable as exc:
            if visual["kind"] == "image":
                _note(card, f"No AI image this time: {exc}.")
                draft.save_card(ctx, card)
                draft.log_interaction(ctx, "visual_failed", card, kind="image", reason="unavailable")
                ctx.run.note(f"AI image for card {card['id']} not made: no image service available")
                return card
            _note(card, f"The visual is drawn without an AI background: {exc}.")
        except images.ImageError:
            if visual["kind"] == "image":
                raise  # the work stays queued and the next run tries again (up to three times)
            _note(card, "The AI background couldn't be made this time (the image service had an error), so the "
                        "visual is drawn without it. Ask again to retry.")
        else:
            visual["image"] = {"path": res.path, "width": res.width, "height": res.height,
                               "content_type": res.content_type, "provider": res.provider, "model": res.model,
                               "created_at": now}
            # Say it's AI-made, keeping within the 600-character alt text.
            if visual["kind"] == "image" and not visual["alt_text"].lower().startswith("ai-generated"):
                lead = "AI-generated illustration: "
                visual["alt_text"] = lead + textutil.truncate(visual["alt_text"], 600 - len(lead))
            elif visual["kind"] != "image":
                tail = " (Background: an AI-generated image.)"
                visual["alt_text"] = textutil.truncate(visual["alt_text"], 600 - len(tail)) + tail
    # A source line may name the publisher and date, so those count as evidence too.
    cited = " ".join(f"{s.get('publisher') or ''} {(s.get('published_at') or '')[:10]}" for s in sources)
    evidence = f"{draft.evidence_text(card)}\n{text}\n{cited}"
    visual["unsourced"] = guardrails.unsourced_numbers(visual_text(visual, with_alt=False), evidence)
    visual["created_at"] = now
    card["visual"] = visual
    if (card.get("working") or {}).get("visual"):
        card["working"] = {**card["working"], "visual": None}  # a new visual replaces his edits of the old one
    draft.save_card(ctx, card)
    image = visual.get("image") or {}
    draft.log_interaction(ctx, "visual_created", card, kind=visual["kind"], requested=want,
                          items=len(visual["items"]), unsourced=len(visual["unsourced"]),
                          image=image.get("provider"), background=bool(image) and visual["kind"] != "image")
    log.info(f"visuals: {visual['kind']} with {len(visual['items'])} items for a {card['platform']} card"
             + (f", AI image from {image['provider']}" if image else ""))
    return card
