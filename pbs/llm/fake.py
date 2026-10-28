"""Deterministic offline provider for tests, demos and dry runs (PBS_LLM=fake).

It reads the JSON inside <input>…</input> and returns well-formed output for each task, so the whole
pipeline can run without network access. Tests can register overrides per task.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from .. import textutil
from .base import LLMError, LLMRequest, LLMResponse

_INPUT_RE = re.compile(r"<input>\s*(.*?)\s*</input>", re.DOTALL)

Handler = Callable[[LLMRequest, Any], Any]


def read_input(prompt: str) -> Any:
    m = _INPUT_RE.search(prompt)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


class FakeProvider:
    def __init__(self, name: str = "fake", handlers: dict[str, Handler] | None = None,
                 fail_with: LLMError | None = None, model: str = "fake-1"):
        self.name = name
        self.handlers: dict[str, Handler] = dict(DEFAULT_HANDLERS)
        self.handlers.update(handlers or {})
        self.fail_with = fail_with
        self.current_model = model
        self.calls: list[LLMRequest] = []

    def available(self) -> bool:
        return True

    def generate(self, req: LLMRequest) -> LLMResponse:
        self.calls.append(req)
        if self.fail_with is not None:
            raise self.fail_with
        data = read_input(req.prompt)
        handler = self.handlers.get(req.task) or self.handlers["default"]
        out = handler(req, data)
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        return LLMResponse(text=text, provider=self.name, model=self.current_model, tokens_in=len(req.prompt) // 4,
                           tokens_out=len(text) // 4)


# ---------------------------------------------------------------------------
# Default handlers
# ---------------------------------------------------------------------------


def _pulse(req: LLMRequest, data: Any) -> Any:
    """Two conversations a platform, as a grounded search would find them."""
    convs = [
        ("linkedin", "AI agents that report work they never did",
         "People are sharing screenshots of agents confidently saying a task is done when it isn't.",
         "A screenshot plus a one-line caption: the evidence does the work.",
         "https://www.linkedin.com/posts/someone_ai-agents-activity-7300000000000000001"),
        ("linkedin", "Engineers asked to justify every AI tool cost",
         "Managers are asking teams to show what each AI subscription saves; engineers are pushing back.",
         "A relatable tension with a clear side to take.", ""),
        ("x", "The model that refused to write a regex",
         "A viral thread of a model politely declining a harmless task, and the replies trying to talk it round.",
         "Absurd, specific and easy to quote-post.", "https://x.com/someone/status/1900000000000000001"),
        ("x", "Founders posting their AI bill",
         "Startup founders are sharing their monthly model bills and what they cut.",
         "Real numbers people compare with their own.", ""),
    ]
    return {"conversations": [{"platform": p, "topic": t, "what_people_say": s, "why_it_works": w,
                               "angle": f"What {t.lower()} says about how teams use AI now",
                               "examples": [u] if u else []} for p, t, s, w, u in convs]}


def _humor_write(req: LLMRequest, data: Any) -> Any:
    """Six versions of a joke about the material's topic, each in a different style."""
    topic = str(data.get("topic") or "this").rstrip(".")
    sources = data.get("sources") or []
    short = textutil.truncate(topic, 90)
    x = data.get("platform") == "x"
    versions = [
        ("detail", f"{short}.\n\nThe press release says \u201ctransformational\u201d. The changelog says \u201cminor fixes\u201d."),
        ("understatement", f"{short}.\n\nSo that's my afternoon's reading sorted, and possibly my career."),
        ("escalation", f"Monday: {short}.\nTuesday: a strategy deck about it.\nWednesday: a strategy deck about the deck."),
        ("parody", f"Thrilled to announce I have read about {short.lower()}. Humbled. Grateful. Still confused."),
        ("misdirection", f"Everyone's asking what {short.lower()} means for the industry. I'm asking who approved the name."),
        ("pattern", "Every big launch ends the same way: a demo that works, and a support page titled \u201cKnown issues\u201d."),
    ]
    if x:
        versions = [(d, t if len(t) <= 170 else t[:167].rsplit(" ", 1)[0] + "\u2026") for d, t in versions]
    first = f"Source: {sources[0]['url']}" if sources and sources[0].get("url") else ""
    return {"options": [{"device": d, "text": t} for d, t in versions],
            "hashtags": [] if x else ["#AI", "#SoftwareEngineering"], "first_comment": first}


def _humor_judge(req: LLMRequest, data: Any) -> Any:
    """Prefers the second version (so tests see the critic's pick win over the writers' order)."""
    versions = data.get("versions") or []
    scores = [{"version": v["version"], "surprise": 4 if v["version"] == 2 else 2, "specific": 3, "share": 3,
               "cliche": False, "explains": False, "mean": False, "wrong": False} for v in versions]
    return {"scores": scores, "best": 2 if len(versions) > 1 else 1, "runner_up": 1 if len(versions) > 1 else None,
            "verdict": "ok", "note": "The understatement lands; the rest try too hard."}


def _translate(req: LLMRequest, data: Any) -> Any:
    items = data if isinstance(data, list) else data.get("items", [])
    return {"items": [{"id": it.get("id"), "title_en": f"(EN) {it.get('title', '')}",
                       "summary_en": f"(EN) {it.get('summary', '')}"[:300]} for it in items]}


def _pick_pillar(text: str, keys: list[str], fallback: str) -> str:
    low = text.lower()
    rules = [
        ("research", ("paper", "arxiv", "benchmark", "study", "research")),
        ("industry", ("raises", "launch", "funding", "regulation", "acquire", "release", "announces")),
        ("learning", ("mcp", "agent", "eval", "sdk", "framework")),
        ("receipts", ("automation", "rpa", "bank", "workflow", "enterprise")),
        ("affairs", ("bihar", "india", "election", "government", "minister", "patna", "world")),
        ("startups", ("startup", "founder", "raises", "funding", "seed", "series")),
        ("tech", ("ai", "model", "llm", "openai", "google", "software")),
    ]
    for key, words in rules:
        if key in keys and any(w in low for w in words):
            return key
    return fallback


def _triage(req: LLMRequest, data: Any) -> Any:
    topics = data.get("topics", []) if isinstance(data, dict) else data
    li_keys = re.findall(r"^- (\w+):", req.prompt.split("X lanes")[0], re.MULTILINE) or ["research", "industry"]
    x_part = req.prompt.split("X lanes", 1)[1] if "X lanes" in req.prompt else ""
    x_keys = re.findall(r"^- (\w+):", x_part, re.MULTILINE) or ["tech", "affairs", "startups"]
    out = []
    formats = ["x_single", "x_thread", "x_reply", "x_quote"]
    for i, t in enumerate(topics):
        text = f"{t.get('title', '')} {t.get('summary', '')} {t.get('scout', '')}"
        scout = t.get("scout")
        li = _pick_pillar(text, li_keys, li_keys[0])
        x = "affairs" if scout == "affairs" and "affairs" in x_keys else _pick_pillar(text, x_keys, x_keys[0])
        li_fit = "none" if scout == "affairs" else li
        out.append({
            "id": t.get("id"),
            "summary_en": textutil.truncate(t.get("summary") or t.get("title") or "", 200),
            "sensitive": False,
            "sensitive_reason": "",
            "issue_key": None,
            "linkedin": {"pillar": li_fit, "angle_potential": 3 + (i % 3 == 0), "angle":
                         f"What {textutil.truncate(t.get('title', ''), 60)} means for teams automating real work",
                         "format_note": ""},
            "x": {"lane": x, "angle_potential": 3 + (i % 2), "angle":
                  f"The part of {textutil.truncate(t.get('title', ''), 60)} most people will miss",
                  "format": formats[i % len(formats)],
                  "affairs_type": "tracker" if x == "affairs" else None},
        })
    return {"topics": out}


def _hooks(title: str) -> list[dict[str, str]]:
    short = textutil.truncate(title, 70)
    return [
        {"type": "question", "text": f"What does {short} change for people doing the work?"},
        {"type": "observation", "text": f"{short}: the detail that matters is not the headline."},
        {"type": "how-to", "text": f"How to read {short} if you build automation for a living:"},
    ]


_NOT_TAGS = {"adds", "says", "gets", "makes", "launches", "plans", "reports", "shows", "finds", "about", "after",
             "into", "with", "from", "this", "that", "what", "when", "your", "their", "more", "less", "than"}


def _draft(req: LLMRequest, data: Any) -> Any:
    title = data.get("topic") or data.get("title") or "this topic"
    platform = data.get("platform", "linkedin")
    fmt = data.get("format", "li_text")
    sources = data.get("sources") or []
    first = sources[0] if sources else {}
    fact = textutil.truncate(first.get("summary") or first.get("title") or title, 180)
    answers = data.get("questions_and_answers") or []
    answer_text = " ".join(a.get("answer", "") for a in answers if a.get("answer"))
    angle = data.get("angle") or f"Why {title} matters"
    body_core = answer_text or fact
    hooks = _hooks(title)
    claims = [{"text": fact, "source": 0}] if sources else []
    words = [w for w in textutil.sim_tokens(title) if w.isalpha() and len(w) > 3 and w not in _NOT_TAGS][:3]
    tags = ["#" + w.capitalize() for w in words]
    out: dict[str, Any] = {"hook_type": "observation", "hooks": hooks, "claims": claims, "format_note": "",
                           "angle": angle, "posts": [], "text": "",
                           "hashtags": tags if platform == "linkedin" else tags[:1],
                           "first_comment": f"Source: {first['url']}" if first.get("url") and fmt != "x_reply" else ""}
    if platform == "linkedin":
        out["text"] = (f"{hooks[1]['text']}\n\n{body_core}\n\n{angle}. The useful question for anyone automating "
                       f"real work is what changes in practice, not in the demo.\n\nWhere would this land in your "
                       f"process first?")
        out["format_note"] = "Could work as a 4-slide carousel: context, what changed, what it means, what to try."
    elif fmt == "x_thread":
        out["posts"] = [
            textutil.truncate(hooks[1]["text"], 250),
            textutil.truncate(body_core, 250),
            textutil.truncate(f"{angle}.", 250),
        ]
    elif fmt == "x_reply":
        out["text"] = textutil.truncate(f"The underrated part: {body_core}", 240)
        out["reply_context"] = f"Replies to posts announcing {textutil.truncate(title, 80)}"
        out["search_terms"] = textutil.sim_tokens(title)[:3]
    elif fmt == "x_quote":
        out["text"] = textutil.truncate(f"Worth reading past the headline: {body_core}", 250)
        out["quote_source"] = 0
    else:
        out["text"] = textutil.truncate(f"{hooks[1]['text']} {body_core}", 270)
    return out


def _questions(req: LLMRequest, data: Any) -> Any:
    title = data.get("topic") or data.get("title") or "this"
    return {
        "questions": [
            {"q": f"Where have you seen something like {textutil.truncate(title, 60)} play out in real work?",
             "why": "Grounds the post in firsthand experience"},
            {"q": "What would you tell a team about to try this?", "why": "Gives the post a practical takeaway"},
        ],
        "angle": f"A practitioner's view on {textutil.truncate(title, 60)}",
    }


def _reflect(req: LLMRequest, data: Any) -> Any:
    return {
        "summary": "Posts with a concrete opening line were picked more and edited less.",
        "changes": [
            {"op": "add", "text": "Open with a concrete detail from the source, not a general statement.",
             "platform": None, "pillar": None, "confidence": "medium",
             "evidence": data.get("post_ids", [])[:3], "reversal": "Edit ratio rises for two weeks."},
        ],
        "experiments": [
            {"platform": "x", "pillar": None, "instruction": "Lead with a number from the sources.",
             "hypothesis": "Number hooks get more replies on X.", "confidence": "low"},
        ],
        "proposals": [],
    }


def _voice(req: LLMRequest, data: Any) -> Any:
    return {"rules": ["Keep sentences short and concrete.", "Cut hedging words like 'really' and 'very'."],
            "summary": "Prefers shorter, plainer drafts."}


def _vision(req: LLMRequest, data: Any) -> Any:
    for img, _mime in req.images:
        try:
            return json.loads(img.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return {"platform": "linkedin", "kind": "post_analytics", "posts": [], "account": {}}


def _stances(req: LLMRequest, data: Any) -> Any:
    return {"issues": [
        {"key": "sample-issue", "issue": "Sample recurring issue", "tier": "india",
         "context": "Neutral one-line context.", "positions": [
             {"key": "a", "label": "Position A", "text": "One view, stated fairly."},
             {"key": "b", "label": "Position B", "text": "Another view, stated fairly."}],
         "keywords": ["sample"]},
    ]}


def _evergreen(req: LLMRequest, data: Any) -> Any:
    return {"topics": [
        {"platform": "linkedin", "pillar": "receipts", "title": "What production automation teaches that demos don't",
         "angle": "The unglamorous work that decides whether automation survives", "mode": "interview",
         "questions": [{"q": "What was the first thing that broke when an automation met real data?", "why": "Story"},
                       {"q": "What check do you now add before anything goes live?", "why": "Takeaway"}]},
        {"platform": "x", "pillar": "life", "title": "A small habit that changed your week", "mode": "interview",
         "angle": "Personal observation", "questions": [{"q": "What habit stuck this year, and why?", "why": "Story"}]},
    ]}


def _search(req: LLMRequest, data: Any) -> Any:
    q = data.get("query", "the topic") if isinstance(data, dict) else "the topic"
    return f"Recent developments on {q}: summary from grounded search."


def _search_plan(req: LLMRequest, data: Any) -> Any:
    q = data.get("query", "the topic") if isinstance(data, dict) else "the topic"
    automation = "automation" in q.casefold()
    return {"interpretation": f"{q}, for teams automating business work" if automation
            else f"{q}, for people building with AI at work",
            "queries": [q, f"{q} enterprise workflow" if automation else f"{q} latest"],
            "exclude": ["industrial", "manufacturing"] if automation else [],
            "arxiv": f'abs:"{q}"', "recency_days": 14, "background": False}


def _search_rerank(req: LLMRequest, data: Any) -> Any:
    """Keeps what's on topic: drops factory robotics, and the mock web's placeholder posts."""
    rows = data if isinstance(data, list) else []
    off = ("factory", "earlier post")
    return {"keep": [r.get("id") for r in rows if not any(w in str(r.get("title", "")).casefold() for w in off)]}


def _research(req: LLMRequest, data: Any) -> Any:
    """One change, citing the newest article; nothing when there are no articles."""
    rows = data if isinstance(data, list) else []
    if not rows:
        return {"summary": "Nothing new this month.", "changes": []}
    a = rows[0]
    return {"summary": "One documented change this month.",
            "changes": [{"op": "add", "platform": a.get("platform") or "linkedin", "format": None,
                         "text": textutil.truncate(f"Reflect this month's change: {a.get('title')}", 200),
                         "why": "Reported this month.", "evidence": [a.get("id")], "confidence": "medium"}]}


_VISUAL_MARKERS = (("carousel", "Make a document carousel"), ("carousel", "Make a carousel of images"),
                   ("flow", "Make a flowchart"),
                   ("compare", "Make a two-column comparison"), ("list", "Make a numbered list"),
                   ("stat", "Make one big number"), ("quote", "Make a quote card"),
                   ("image", "Make an AI illustration"))


def _visual(req: LLMRequest, data: Any) -> Any:
    """The requested kind (a carousel when it's up to the model), built from the post's own sentences."""
    data = data if isinstance(data, dict) else {}
    post = data.get("post") or ""
    sentences = [s for s in textutil.split_sentences(post.replace("\n", " ")) if s.strip()]
    kind = next((k for k, marker in _VISUAL_MARKERS if marker in req.prompt), "carousel")
    title = textutil.truncate(data.get("topic") or (sentences[0] if sentences else "The point"), 70)
    sources = data.get("sources") or []
    figures = textutil.numeric_claims(post)
    if kind == "stat" and not figures:
        kind = "list"  # a big number needs a figure
    picture = ({"image_prompt": f"A calm, concrete scene that stands for: {title}. Soft morning light."}
               if '"image_prompt"' in req.prompt else {})
    if kind == "image":
        return {"kind": "image", "title": textutil.truncate(title, 60), "items": [], "caption": "",
                "alt_text": f"An illustration for a post about {title}", "sources": [], **picture}
    if kind == "stat":
        about = next((s for s in sentences if figures[0] in s), sentences[0] if sentences else title)
        items = [{"title": figures[0], "body": textutil.truncate(about, 120)}]
    elif kind == "quote":
        items = [{"title": (sources[0].get("publisher") if sources else None) or "The source",
                  "body": textutil.truncate(sentences[0] if sentences else title, 200)}]
    elif kind == "compare":
        half = max(1, len(sentences) // 2)
        items = [{"title": "What it says", "body": "\n".join(textutil.truncate(s, 60) for s in sentences[:half][:4])},
                 {"title": "What it means", "body": "\n".join(textutil.truncate(s, 60) for s in sentences[half:][:4])
                  or "Watch what happens next"}]
    else:
        chunks = (sentences or [title])[: {"carousel": 6, "flow": 5, "list": 5}[kind]]
        while len(chunks) < 3:
            chunks.append(f"Step {len(chunks) + 1}")
        items = [{"title": textutil.truncate(s, 40), "body": textutil.truncate(s, 200)} for s in chunks]
    return {"kind": kind, "title": title, "subtitle": data.get("angle") or "", "items": items,
            "caption": f"Source: {sources[0].get('title')}" if sources else "", "alt_text": "",
            "sources": [0] if sources else [], **picture}


_EDIT_FIXES = [
    (re.compile(r"\s*—\s*"), ", "),
    (re.compile(r"(?i)\bhere's (?:why|what|how|the thing)[^.:!?]*[.:!]\s*"), ""),
    (re.compile(r"(?i)\b(?:in short|ultimately|the bottom line|at the end of the day)[,:]?\s*"), ""),
    (re.compile(r"(?i)\b(it|this|that)(?:'s| is) not (?:about )?([^,.;]+)[,;] (?:it|this|that)(?:'s| is) (?:about )?"),
     r"\2 matters less than "),
    (re.compile(r"(?i)\b(?:it's worth noting that|when it comes to)\s*"), ""),
]


def _edit(req: LLMRequest, data: Any) -> Any:
    """The editor pass: removes the tells it was told about, keeping every fact (a deterministic stand-in)."""
    data = data if isinstance(data, dict) else {}

    def fix(text: str) -> str:
        for pattern, repl in _EDIT_FIXES:
            text = pattern.sub(repl, text)
        return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text).strip()

    return {"text": fix(data.get("text") or ""), "posts": [fix(p) for p in data.get("posts") or []]}


def _default(req: LLMRequest, data: Any) -> Any:
    return {"ok": True}


DEFAULT_HANDLERS: dict[str, Handler] = {
    "translate": _translate,
    "triage": _triage,
    "draft": _draft,
    "draft_personal": _draft,
    "questions": _questions,
    "reflect": _reflect,
    "voice": _voice,
    "vision": _vision,
    "stances": _stances,
    "evergreen": _evergreen,
    "search": _search,
    "search_plan": _search_plan,
    "search_rerank": _search_rerank,
    "research": _research,
    "visual": _visual,
    "edit": _edit,
    "pulse": _pulse,
    "humor_write": _humor_write,
    "humor_judge": _humor_judge,
    "default": _default,
}
