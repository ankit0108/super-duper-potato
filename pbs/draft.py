"""Drafting: external drafts, interview questions, drafts from answers, rewrites, brief cards.

Every draft passes the deterministic guardrails before it can reach the desk. A card records the
playbook, prompt and voice versions and the model that wrote it.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import guardrails, ids, log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import BudgetExhausted, LLMRequest, LLMResponse, json_rows, why_unavailable
from .style import Style, render_examples, render_rules, style_for

PLATFORM_LABEL = {"linkedin": "LinkedIn", "x": "X"}

AFFAIRS_INSTRUCTIONS = {
    "history": "Affairs post type: history behind the news. Explain the background that makes today's news make "
               "sense. Every date and figure must come from the material.",
    "tracker": "Affairs post type: development tracker. What actually changed, before and after, with figures from "
               "the material.",
    "outlook": "Affairs post type: future outlook. Where this is heading and what would change that. Frame it as "
               "scenarios, never as predictions stated as fact.",
    "opinion": "Affairs post type: opinion. Use ONLY his recorded stance in the material. Don't go beyond it or add "
               "arguments he hasn't made.",
}
MODE_EXTERNAL = ("Mode: external. Write analysis from the material. Don't claim experiences for him. An analytical "
                 "angle is fine: he sees it as a proposal and adopts it only by posting.")
UNANSWERED = ("This topic invites his own experience, but he hasn't answered the questions yet: write a strong "
              "analysis post from the sources alone, in his voice, without inventing anything he did, saw or thinks. "
              "Prefer the newest sources and say when things happened.")
SENSITIVE = ("Handle with care: this involves a tragedy, violence or a communal incident. Neutral, factual, humane "
             "tone. No provocative hook, no opinion, no engagement question.")

ANGLE_FALLBACK = {
    "research": "What this result means for teams automating real work",
    "industry": "What this move signals for enterprise automation buyers",
    "receipts": "Where this meets what production automation actually teaches",
    "learning": "What building with this would teach",
    "tech": "The detail most coverage will miss",
    "affairs": "What actually changed, with the numbers",
    "startups": "What this says about where the market is heading",
    "life": "A personal observation",
}


def format_instructions(ctx: Ctx, fmt: str) -> str:
    x = ctx.settings.platforms.x
    limit = ctx.settings.x_char_limit()
    fold = ctx.settings.platforms.linkedin.fold_chars
    return {
        "li_text": (f"Format: a LinkedIn text post. The first line must earn the click before the 'see more' fold "
                    f"(about {fold} characters): concrete and specific, no throat-clearing. Short paragraphs separated "
                    "by blank lines. No hashtags unless one is genuinely useful (at most 3, at the end). End on a "
                    "specific point or a genuine question tied to the post, never bait."),
        "x_single": (f"Format: a single X post of at most {limit} characters (a link counts as 23). One idea, "
                     "concrete. No hashtags, at most one emoji."),
        "x_thread": (f"Format: an X thread of {x.thread_min} to {x.thread_max} posts, each at most {limit} characters. "
                     "Post 1 is the hook and must stand alone. Each post adds one step. The last post lands the "
                     "takeaway, with the main source link if useful."),
        "x_quote": (f"Format: a quote-post comment on the main source (at most {min(limit, 280)} characters). Add "
                    "what the source doesn't say: context, an implication or a sharp question. Also return "
                    '"quote_source": the index of the source to quote.'),
        "x_reply": ("Format: a reply to large accounts' posts about this announcement (at most 200 characters). Add "
                    "one specific thing: a detail from the material, a practical implication or a precise question. "
                    "Never sycophantic ('Great post'), never self-promotional. Also return \"reply_context\" (one "
                    'line: what the reply responds to) and "search_terms" (2 to 4 words to find the thread on X).'),
    }[fmt]


def _extra_fields(fmt: str) -> str:
    if fmt == "x_reply":
        return ', "reply_context": "…", "search_terms": ["…", "…"]'
    if fmt == "x_quote":
        return ', "quote_source": 0'
    return ""


# ---------------------------------------------------------------------------
# Output model and clean-up
# ---------------------------------------------------------------------------


class HookOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str = "observation"
    text: str

    @field_validator("text")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v).split("\n")[0].strip()


class ClaimOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    source: int | None = None


class DraftOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = ""
    posts: list[str] = Field(default_factory=list)
    hook_type: str | None = None
    hooks: list[HookOut] = Field(default_factory=list)
    claims: list[ClaimOut] = Field(default_factory=list)
    format_note: str | None = ""
    angle: str | None = ""
    reply_context: str | None = None
    search_terms: list[str] = Field(default_factory=list)
    quote_source: int | None = None

    @field_validator("claims", mode="before")
    @classmethod
    def _claims(cls, v: Any) -> Any:
        out = []
        for c in v or []:
            if isinstance(c, str):
                out.append({"text": c})
            elif isinstance(c, dict) and c.get("text"):
                src = c.get("source")
                if isinstance(src, str) and src.strip().isdigit():
                    c = {**c, "source": int(src.strip())}
                elif not isinstance(src, int):
                    c = {**c, "source": None}
                out.append(c)
        return out

    @field_validator("hooks", mode="before")
    @classmethod
    def _hooks(cls, v: Any) -> Any:
        out = []
        for h in v or []:
            if isinstance(h, str) and h.strip():
                out.append({"type": "observation", "text": h})
            elif isinstance(h, dict) and (h.get("text") or "").strip():
                out.append(h)
        return out


_MD_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_MD_HEAD = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")
_MD_BULLET = re.compile(r"(?m)^\s*[*•]\s+")
_THREAD_NUM = re.compile(r"^\s*(?:\d{1,2}\s*/\s*\d{0,2}|\(\d{1,2}/\d{1,2}\)|\d{1,2}[.)])\s*")


def clean_text(text: str | None) -> str:
    text = (text or "").replace("\r\n", "\n")
    text = _MD_BOLD.sub(lambda m: m.group(1) or m.group(2), text)
    text = _MD_HEAD.sub("", text)
    text = _MD_BULLET.sub("- ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _norm_hook_type(ctx: Ctx, t: str | None) -> str:
    t = (t or "").strip().lower().replace("_", "-")
    aliases = {"howto": "how-to", "how to": "how-to", "stat": "number", "statistic": "number", "data": "number",
               "anecdote": "story", "insight": "observation", "claim": "contrarian", "bold": "contrarian"}
    t = aliases.get(t, t)
    return t if t in ctx.settings.hooks.types else "observation"


def _fallback_hooks(title: str) -> list[dict[str, str]]:
    short = textutil.truncate(title, 80)
    return [
        {"type": "question", "text": f"What does {short} actually change?"},
        {"type": "observation", "text": f"The interesting part of {short} isn't the headline."},
        {"type": "how-to", "text": f"How to read {short}:"},
    ]


def normalize_output(ctx: Ctx, card: dict[str, Any], out: DraftOut, sources: list[dict[str, Any]]) -> dict[str, Any]:
    fmt = card["format"]
    x = ctx.settings.platforms.x
    text = clean_text(out.text)
    posts = [clean_text(_THREAD_NUM.sub("", p)) for p in out.posts if p and p.strip()]
    if fmt == "x_thread":
        if not posts and text:
            posts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        posts = posts[: x.thread_max]
        text = ""
    elif not text and posts:
        text = "\n\n".join(posts)
        posts = []
    else:
        posts = []
    if not text and not posts:
        raise ValueError("draft is empty")
    draft: dict[str, Any] = {"text": text, "posts": posts}
    if fmt == "x_reply":
        lane_accounts = ctx.settings.watchlist.get(card.get("pillar") or "", []) or ctx.settings.watchlist.get("tech", [])
        terms = [t for t in (out.search_terms or []) if isinstance(t, str) and t.strip()][:4]
        if not terms:
            terms = textutil.sim_tokens(card.get("title"))[:3]
        draft["reply"] = {"context": clean_text(out.reply_context or f"Posts about {card.get('title')}"),
                          "search_terms": terms, "accounts": lane_accounts[:8]}
    if fmt == "x_quote":
        idx = out.quote_source if isinstance(out.quote_source, int) else 0
        if 0 <= idx < len(sources):
            draft["quote_url"] = sources[idx]["url"]
        elif sources:
            draft["quote_url"] = sources[0]["url"]
    hooks: list[dict[str, str]] = []
    seen: set[str] = set()
    for h in out.hooks:
        key = h.text.casefold()
        if h.text and key not in seen:
            seen.add(key)
            hooks.append({"type": _norm_hook_type(ctx, h.type), "text": h.text})
    for h in _fallback_hooks(card.get("title") or ""):
        if len(hooks) >= 3:
            break
        if h["text"].casefold() not in seen:
            hooks.append(h)
    claims = [{"text": textutil.truncate(c.text, 300),
               "source": c.source if isinstance(c.source, int) and 0 <= c.source < len(sources) else None}
              for c in out.claims[:15]]
    return {
        "draft": draft,
        "hooks": hooks[:3],
        "hook_type": _norm_hook_type(ctx, out.hook_type),
        "claims": claims,
        "format_note": clean_text(out.format_note) if card["platform"] == "linkedin" else None,
        "angle": clean_text(out.angle) or card.get("angle"),
    }


# ---------------------------------------------------------------------------
# Material
# ---------------------------------------------------------------------------


def select_sources(ctx: Ctx, topic: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    item_ids = topic.get("item_ids") or []
    if not item_ids:
        return []
    placeholders = ",".join("?" for _ in item_ids)
    items = ctx.store.select("items", f"id IN ({placeholders})", item_ids)
    src_names = {s["id"]: s.get("name") for s in ctx.store.select("sources")}

    def pref(it: dict[str, Any]) -> tuple[int, int]:
        english = 0 if (it.get("lang") != "hi" or it.get("title_en")) else 1
        summary = 0 if (it.get("summary_en") or it.get("summary")) else 1
        return (english, summary)

    ordered = sorted(items, key=lambda it: it.get("published_at") or "", reverse=True)
    ordered.sort(key=pref)
    out: list[dict[str, Any]] = []
    publishers: set[str] = set()
    for it in ordered:
        pub = (it.get("signals") or {}).get("publisher") or src_names.get(it["source_id"]) or textutil.url_host(it["url"])
        if pub in publishers and len(items) > limit:
            continue
        publishers.add(pub)
        hindi = it.get("lang") == "hi"
        out.append({
            "url": it["url"],
            "title": it.get("title_en") or it["title"],
            "publisher": pub,
            "lang": it.get("lang") or "en",
            "published_at": it.get("published_at"),
            "orig_title": it["title"] if hindi else None,
            "summary": textutil.truncate(it.get("summary_en") or it.get("summary") or "", 420),
        })
        if len(out) >= limit:
            break
    return out


def evidence_text(card: dict[str, Any], stance_text: str | None = None) -> str:
    parts = [card.get("title") or ""]
    for s in card.get("sources") or []:
        parts += [s.get("title") or "", s.get("summary") or "", s.get("orig_title") or ""]
    for a in card.get("answers") or []:
        parts.append(a.get("answer") or "")
    if stance_text:
        parts.append(stance_text)
    return "\n".join(p for p in parts if p)


def _stance_for(ctx: Ctx, card: dict[str, Any]) -> dict[str, Any] | None:
    key = card.get("issue_key") or (card.get("flags") or {}).get("stance_id")
    if not key:
        return None
    stance = ctx.store.get("stances", key)
    if not stance or not stance.get("chosen"):
        return None
    return stance


def stance_text(stance: dict[str, Any] | None) -> str | None:
    if not stance:
        return None
    chosen = stance.get("chosen") or {}
    if chosen.get("custom_text"):
        return f"{stance['issue']}: {chosen['custom_text']}"
    for pos in stance.get("positions") or []:
        if pos.get("key") == chosen.get("position_key"):
            return f"{stance['issue']}: {pos.get('label')} — {pos.get('text')}"
    return None


def _material(card: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {
        "platform": card["platform"],
        "format": card["format"],
        "topic": card.get("title"),
        "why_now": card.get("why_now"),
        "angle": card.get("angle"),
        "sources": [{"index": i, "title": s.get("title"), "publisher": s.get("publisher"),
                     "date": (s.get("published_at") or "")[:10] or None, "summary": s.get("summary"),
                     "url": s.get("url")} for i, s in enumerate(card.get("sources") or [])],
    }
    data.update(extra or {})
    return data


def profile_text(profile: str) -> str:
    """The profile without HTML comments (the editing hints in the default template)."""
    return re.sub(r"<!--.*?-->", "", profile or "", flags=re.DOTALL).strip() or "(No profile yet.)"


def _system(ctx: Ctx) -> str:
    return prompting.render("system", display_name=ctx.settings.display_name,
                            profile=profile_text(ctx.settings.profile),
                            avoid_examples=", ".join(f'"{p}"' for p in ctx.settings.voice.avoid_phrases[:8]))


def _common_vars(ctx: Ctx, card: dict[str, Any], style: Style) -> dict[str, Any]:
    pillar = ctx.settings.pillar(card["platform"], card["pillar"])
    x = ctx.settings.platforms.x
    fmt_label = ctx.settings.formats[card["format"]].label.lower() if card["format"] in ctx.settings.formats else "post"
    return {
        "display_name": ctx.settings.display_name,
        "platform_label": PLATFORM_LABEL[card["platform"]],
        "format_label": fmt_label,
        "pillar_label": pillar.label if pillar else card["pillar"],
        "pillar_description": pillar.description if pillar else "",
        "angle": card.get("angle") or ANGLE_FALLBACK.get(card["pillar"], "A specific, non-generic angle"),
        "format_instructions": format_instructions(ctx, card["format"]),
        "affairs_instructions": AFFAIRS_INSTRUCTIONS.get(card.get("affairs_type") or "", ""),
        "sensitive_instructions": SENSITIVE if (card.get("flags") or {}).get("sensitive") else "",
        "style_rules": render_rules(style.rules),
        "length_target": style.length_target,
        "avoid": ", ".join(style.avoid[:40]),
        "hook_prefs": ", ".join(style.hook_prefs[:3]),
        "hook_types": ", ".join(ctx.settings.hooks.types),
        "examples": render_examples(style.examples),
        "thread_min": x.thread_min,
        "thread_max": x.thread_max,
        "x_limit": ctx.settings.x_char_limit(),
        "extra_fields": _extra_fields(card["format"]),
    }


# ---------------------------------------------------------------------------
# Applying results
# ---------------------------------------------------------------------------


def _apply(ctx: Ctx, card: dict[str, Any], norm: dict[str, Any], resp: LLMResponse, style: Style,
           prompt_version: str, stance: dict[str, Any] | None, keep_status: bool = False) -> dict[str, Any]:
    now = timeutil.now_iso()
    card.update(norm)
    if card.get("draft_original") is None:
        card["draft_original"] = norm["draft"]
    card["versions"] = {"playbook": style.playbook_version, "prompt": prompt_version, "voice": style.voice_version}
    card["llm"] = {"provider": resp.provider, "model": resp.model}
    card["draft_state"] = "full"
    card["working"] = None
    check = guardrails.check_card(card, settings=ctx.settings, blocklist=ctx.blocklist,
                                  evidence=evidence_text(card, stance_text(stance)),
                                  avoid_phrases=style.avoid, bait_phrases=ctx.settings.voice.bait_phrases)
    card["flags"] = check.flags
    if stance:
        card["flags"]["stance_id"] = stance["id"]
    if check.blocked:
        card["status"] = "blocked"
        ctx.run.note(f"Blocked card {card['id']} (blocklist match)")
    elif not keep_status or card.get("status") in ("drafting", "needs_input", "failed", "blocked"):
        card["status"] = "suggested"
    card["work"] = None
    card["updated_at"] = now
    card["revision"] = int(card.get("revision") or 0) + 1
    save_card(ctx, card)
    return card


def save_card(ctx: Ctx, card: dict[str, Any]) -> None:
    ctx.store.upsert("cards", card)


def log_interaction(ctx: Ctx, type_: str, card: dict[str, Any] | None = None, **data: Any) -> None:
    ctx.store.insert("interactions", {
        "id": ids.new_id("int"),
        "at": timeutil.now_iso(),
        "type": type_,
        "card_id": card["id"] if card else data.pop("card_id", None),
        "post_id": data.pop("post_id", None),
        "request_id": data.pop("request_id", None) or (card or {}).get("request_id"),
        "platform": (card or {}).get("platform") or data.pop("platform", None),
        "data": data or None,
    })


# ---------------------------------------------------------------------------
# Drafting operations
# ---------------------------------------------------------------------------


def draft_external(ctx: Ctx, card: dict[str, Any], avoid_angles: list[str] | None = None,
                   experiment: dict[str, Any] | None = None, unanswered: bool = False) -> dict[str, Any]:
    """An analysis draft from the card's sources. `unanswered`: a card that asked for his experience or view,
    drafted before he answered (so no opinion he hasn't recorded, and no experiences)."""
    style = style_for(ctx, card["platform"], card["pillar"], card["format"])
    opinion = card.get("affairs_type") == "opinion"
    stance = _stance_for(ctx, card) if opinion else None
    extra: dict[str, Any] = {}
    if stance:
        extra["recorded_stance"] = stance_text(stance)
    if avoid_angles:
        extra["angles_already_used"] = avoid_angles
    exp_text = ""
    if experiment:
        exp_text = f"Experiment for this draft (follow it): {experiment['instruction']}"
    elif avoid_angles:
        exp_text = "Take a clearly different angle from the ones already used (listed in the material)."
    vars_ = _common_vars(ctx, card, style)
    mode = MODE_EXTERNAL
    if unanswered:
        mode += " " + UNANSWERED
        if opinion and not stance:
            vars_["affairs_instructions"] = AFFAIRS_INSTRUCTIONS["outlook"]
    vars_.update(mode_instructions=mode, experiment_instructions=exp_text, input_json=_material(card, extra))
    version = prompting.version("system", "draft")
    req = LLMRequest(task="draft", system=_system(ctx), prompt=prompting.render("draft", **vars_),
                     max_output_tokens=3000, prompt_version=version)
    out, resp = ctx.llm.call_json(req, DraftOut)
    norm = normalize_output(ctx, card, out, card.get("sources") or [])
    card["draft_basis"] = "sources"
    return _apply(ctx, card, norm, resp, style, version, stance, keep_status=True)


class NoSources(Exception):
    """Nothing recent and relevant was found to draft from."""


def news_can_help(ctx: Ctx, card: dict[str, Any]) -> bool:
    """Whether recent sources add anything: not for personal-life posts, which only his own words can make."""
    spec = ctx.settings.pillar(card["platform"], card["pillar"])
    return bool(spec and set(spec.scouts) - {"life"})


def ensure_sources(ctx: Ctx, card: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    """A card without sources (interview-bank and Saturday cards) gets recent ones from a search on its topic."""
    if card.get("sources"):
        return card["sources"]
    from .scout import search

    res = search.run_search(ctx, card.get("title") or "", notes=card.get("angle"),
                            recency_days=ctx.settings.drafting.source_search_days)
    item_ids = search.ingest_results(ctx, res.found, origin=f"card:{card['id']}", limit=limit * 2)
    card["sources"] = select_sources(ctx, {"item_ids": item_ids}, limit=limit)
    return card["sources"]


def draft_from_sources(ctx: Ctx, card: dict[str, Any]) -> dict[str, Any]:
    """A card with questions he hasn't answered: a post from recent sources that he can use as it is.
    Answering later redrafts it from his answers plus these sources. Raises NoSources when there's nothing."""
    if not ensure_sources(ctx, card):
        save_card(ctx, card)
        raise NoSources(card["id"])
    card = draft_external(ctx, card, unanswered=True)
    log_interaction(ctx, "drafted_from_sources", card, questions=len(card.get("questions") or []))
    return card


def fill_interview(ctx: Ctx, card: dict[str, Any], draft_now: bool | None = None,
                   wait_for_budget: bool = False) -> dict[str, Any]:
    """Questions for a card that needs his experience or view, and (unless switched off) a draft from recent
    sources right away, so answering is optional. Without sources or model budget it stays questions-only;
    with `wait_for_budget` (he asked for the draft) running out of budget is raised so the work queue retries."""
    if not card.get("questions"):
        card = ask_questions(ctx, card)
    elif card.get("status") in ("drafting", "failed"):
        card["status"] = "needs_input"
        card["draft_state"] = "pending"
        card["updated_at"] = timeutil.now_iso()
        save_card(ctx, card)
    if draft_now is None:
        # Personal-life posts have nothing to draw on in the news: those wait for his answers unless he asks.
        draft_now = ctx.settings.drafting.interview_draft_now and news_can_help(ctx, card)
    if not draft_now:
        return card
    try:
        return draft_from_sources(ctx, card)
    except NoSources:
        log.info(f"draft: no recent sources for {card['id']}; it waits for his answers")
    except BudgetExhausted as exc:
        if wait_for_budget:
            raise
        log.info(f"draft: {card['id']} keeps its questions only ({type(exc).__name__})")
    return card


def ask_questions(ctx: Ctx, card: dict[str, Any], n: int | None = None) -> dict[str, Any]:
    n = max(1, min(3, n or ctx.settings.drafting.questions_per_card))
    pillar = ctx.settings.pillar(card["platform"], card["pillar"])
    opinion = card.get("affairs_type") == "opinion"
    stance_ctx = ""
    if opinion and card.get("issue_key"):
        stance = ctx.store.get("stances", card["issue_key"])
        if stance:
            positions = "; ".join(f"{p['label']}: {p['text']}" for p in stance.get("positions") or [])
            stance_ctx = f"Recurring issue: {stance['issue']}. Main positions people hold: {positions}"
    opinion_instr = ("This is an opinion post on a public issue: ask for his view in his own words. You may lay out "
                     "the main positions neutrally, but never suggest which is right." if opinion else "")
    prompt = prompting.render(
        "questions", display_name=ctx.settings.display_name, platform_label=PLATFORM_LABEL[card["platform"]],
        pillar_label=pillar.label if pillar else card["pillar"], n_questions=f"{min(n, 3)}",
        title=card.get("title"), why_now=card.get("why_now") or "", angle=card.get("angle") or "",
        stance_context=stance_ctx, opinion_instructions=opinion_instr, input_json=_material(card))
    version = prompting.version("system", "questions")
    req = LLMRequest(task="questions", system=_system(ctx), prompt=prompt, max_output_tokens=1200,
                     prompt_version=version)
    data, resp = ctx.llm.call_json(req, _questions_schema)
    card["questions"] = [{"id": f"q{i}", "q": q["q"], "why": q.get("why"), "kind": "stance" if opinion else None}
                         for i, q in enumerate(data["questions"][:n], 1)]
    if data.get("angle"):
        card["angle"] = clean_text(data["angle"])
    card["status"] = "needs_input"
    card["draft_state"] = "pending"
    card["work"] = None
    card["llm"] = {"provider": resp.provider, "model": resp.model}
    card["versions"] = {**(card.get("versions") or {}), "prompt": version}
    card["updated_at"] = timeutil.now_iso()
    card["revision"] = int(card.get("revision") or 0) + 1
    save_card(ctx, card)
    return card


def _questions_schema(data: Any) -> dict[str, Any]:
    qs = [q for q in json_rows(data, "questions") if str(q.get("q", "")).strip()]
    if not qs:
        raise ValueError("no questions returned")
    return {"questions": [{"q": clean_text(str(q["q"])), "why": clean_text(str(q.get("why") or ""))} for q in qs],
            "angle": data.get("angle") if isinstance(data, dict) else None}


def draft_from_answers(ctx: Ctx, card: dict[str, Any]) -> dict[str, Any]:
    """His answers for the personal part, recent sources for facts and context."""
    if news_can_help(ctx, card):
        try:
            ensure_sources(ctx, card)
        except Exception as exc:  # noqa: BLE001 - his answers alone still make a post
            log.info(f"draft: sources unavailable for {card['id']} ({type(exc).__name__}); answers only")
    style = style_for(ctx, card["platform"], card["pillar"], card["format"])
    qa = []
    by_q = {q["id"]: q["q"] for q in card.get("questions") or []}
    for a in card.get("answers") or []:
        qa.append({"question": by_q.get(a["question_id"], ""), "answer": a["answer"]})
    stance = _stance_for(ctx, card)
    extra = {"questions_and_answers": qa}
    if stance:
        extra["recorded_stance"] = stance_text(stance)
    reuse = reusable_answers(ctx, card)
    if reuse:
        extra["earlier_answers_he_marked_reusable"] = reuse
    vars_ = _common_vars(ctx, card, style)
    vars_["input_json"] = _material(card, extra)
    version = prompting.version("system", "draft_interview")
    req = LLMRequest(task="draft_personal", system=_system(ctx), prompt=prompting.render("draft_interview", **vars_),
                     max_output_tokens=3000, personal=True, prompt_version=version)
    out, resp = ctx.llm.call_json(req, DraftOut)
    norm = normalize_output(ctx, card, out, card.get("sources") or [])
    card["draft_basis"] = "answers"
    card = _apply(ctx, card, norm, resp, style, version, stance)
    log_interaction(ctx, "drafted_from_answers", card, sources=len(card.get("sources") or []))
    return card


def reusable_answers(ctx: Ctx, card: dict[str, Any], limit: int = 3) -> list[str]:
    """Earlier answers he allowed to be reused, on the same pillar (never stretched: quoted verbatim)."""
    rows = ctx.store.select("interactions", "type = 'answered' AND card_id != ?", (card["id"],),
                            order="at DESC", limit=30)
    out = []
    for r in rows:
        data = r.get("data") or {}
        if data.get("reusable") and data.get("pillar") == card.get("pillar"):
            for a in data.get("answers") or []:
                out.append(textutil.truncate(a, 400))
        if len(out) >= limit:
            break
    return out[:limit]


def rewrite(ctx: Ctx, card: dict[str, Any], work: dict[str, Any]) -> dict[str, Any]:
    style = style_for(ctx, card["platform"], card["pillar"], card["format"])
    current = card.get("working") or card.get("draft") or {}
    current_text = current.get("text") or ""
    current_posts = current.get("posts") or []
    chips = work.get("chips") or []
    personal = card.get("mode") == "interview" or bool(card.get("working"))
    stance = _stance_for(ctx, card)
    hooks = (card.get("working") or {}).get("hooks") or card.get("hooks") or []
    extra: dict[str, Any] = {"current_draft": {"text": current_text, "posts": current_posts},
                             "current_hooks": [h.get("text") for h in hooks]}
    if card.get("answers"):
        by_q = {q["id"]: q["q"] for q in card.get("questions") or []}
        extra["questions_and_answers"] = [{"question": by_q.get(a["question_id"], ""), "answer": a["answer"]}
                                          for a in card["answers"]]
    if stance:
        extra["recorded_stance"] = stance_text(stance)
    vars_ = _common_vars(ctx, card, style)
    vars_.update(
        note=(work.get("note") or "").strip() or "Improve it",
        chips=("Quick asks: " + ", ".join(chips)) if chips else "",
        target_instructions="",
        mode_rule=("Every experience and opinion must stay within his answers." if card.get("mode") == "interview"
                   else "Don't claim experiences for him."),
        input_json=_material(card, extra),
    )
    version = prompting.version("system", "rewrite")
    req = LLMRequest(task="draft_personal" if personal else "draft", system=_system(ctx),
                     prompt=prompting.render("rewrite", **vars_), max_output_tokens=3000, personal=personal,
                     prompt_version=version)
    out, resp = ctx.llm.call_json(req, DraftOut)
    norm = normalize_output(ctx, card, out, card.get("sources") or [])
    card["rewrite_count"] = int(card.get("rewrite_count") or 0) + 1
    card = _apply(ctx, card, norm, resp, style, version, stance, keep_status=True)
    log_interaction(ctx, "rewritten", card, note=work.get("note"), chips=chips)
    return card


def adapt(ctx: Ctx, source_card: dict[str, Any], work: dict[str, Any]) -> dict[str, Any]:
    """Create a card for the other platform from an existing card (a 'rewrite' with a target platform)."""
    target = work["target_platform"]
    fmt = work.get("target_format") or ("li_text" if target == "linkedin" else "x_single")
    pillar_map = {"research": "tech", "industry": "tech", "receipts": "tech", "learning": "tech",
                  "tech": "industry", "startups": "industry", "affairs": "industry", "life": "learning"}
    pillar = source_card["pillar"] if ctx.settings.pillar(target, source_card["pillar"]) else pillar_map.get(
        source_card["pillar"], next(iter(ctx.settings.pillars(target))))
    now = timeutil.now_iso()
    card = {
        **{k: source_card.get(k) for k in ("topic_id", "request_id", "title", "why_now", "angle", "sources",
                                            "questions", "answers", "issue_key", "affairs_type")},
        "id": ids.new_id("crd"),
        "kind": "adapt",
        "platform": target,
        "mode": source_card.get("mode") or "external",
        "pillar": pillar,
        "format": fmt,
        "status": "drafting",
        "flags": {"sensitive": (source_card.get("flags") or {}).get("sensitive", False)},
        "created_at": now,
        "updated_at": now,
        "delivered_at": now,
        "expires_at": timeutil.iso(timeutil.now() + _days(ctx.settings.expiry.request_days)),
        "revision": 0,
        "draft_state": "pending",
    }
    base = source_card.get("working") or source_card.get("draft") or {}
    save_card(ctx, card)
    work2 = {"kind": "rewrite", "note": (work.get("note") or "") + f" Adapt this {PLATFORM_LABEL[source_card['platform']]} "
             f"post for {PLATFORM_LABEL[target]}.", "chips": work.get("chips") or []}
    card["working"] = base
    card = rewrite(ctx, card, work2)
    card["rewrite_count"] = 0
    save_card(ctx, card)
    log_interaction(ctx, "adapted", card, from_card=source_card["id"])
    return card


def _days(n: int):
    import datetime as dt

    return dt.timedelta(days=n)


def make_brief(ctx: Ctx, card: dict[str, Any], reason: str) -> dict[str, Any]:
    """No model budget left: deliver topic, why now, angle and sources, with a 'Draft this' button."""
    card["draft_state"] = "brief"
    card["draft"] = None
    card["angle"] = card.get("angle") or ANGLE_FALLBACK.get(card["pillar"], "")
    card["hooks"] = card.get("hooks") or []
    flags = dict(card.get("flags") or {})
    notes = list(flags.get("notes") or [])
    if reason not in notes:
        notes.append(reason)
    flags["notes"] = notes
    card["flags"] = flags
    if card.get("status") == "drafting":
        card["status"] = "needs_input" if card.get("mode") == "interview" and not card.get("questions") else "suggested"
    card["updated_at"] = timeutil.now_iso()
    save_card(ctx, card)
    return card


# ---------------------------------------------------------------------------
# Work queue (answers, rewrites, 'draft this')
# ---------------------------------------------------------------------------


def process_work(ctx: Ctx, limit: int = 12) -> dict[str, int]:
    """Handle cards Ankit is waiting on, oldest request first."""
    stats = {"done": 0, "failed": 0, "deferred": 0}
    rows = [c for c in ctx.store.select("cards", "work IS NOT NULL") if c.get("work")]
    rows.sort(key=lambda c: (c["work"].get("requested_at") or "", c["id"]))
    for card in rows[:limit]:
        work = card["work"]
        try:
            if work.get("target_platform") and work["target_platform"] != card["platform"]:
                card["work"] = None
                save_card(ctx, card)
                adapt(ctx, card, work)
            elif work["kind"] == "rewrite":
                rewrite(ctx, card, work)
            elif work["kind"] == "questions":
                ask_questions(ctx, card)
            elif card.get("mode") == "interview" and card.get("answers"):
                draft_from_answers(ctx, card)
            elif card.get("mode") == "interview":
                # "Draft from sources" (or a retry): questions stay optional; a draft from recent sources now.
                card = fill_interview(ctx, card, draft_now=True, wait_for_budget=True)
                if not card.get("draft"):
                    card["work"] = None
                    flags = dict(card.get("flags") or {})
                    note = "No recent sources found for this topic: answer a question to get a draft."
                    flags["notes"] = [*[n for n in flags.get("notes") or [] if n != note], note]
                    card["flags"] = flags
                    save_card(ctx, card)
            else:
                draft_external(ctx, card)
            stats["done"] += 1
        except BudgetExhausted as exc:
            work["attempts"] = int(work.get("attempts") or 0) + 1
            work["last_error"] = f"Waiting: {why_unavailable(exc)}; will retry on the next run"
            card["work"] = work
            save_card(ctx, card)
            stats["deferred"] += 1
            log.info(f"work: deferred {card['id']} ({type(exc).__name__})")
            break
        except Exception as exc:  # noqa: BLE001 - one card must not stop the queue
            work["attempts"] = int(work.get("attempts") or 0) + 1
            work["last_error"] = f"{type(exc).__name__}"
            if work["attempts"] >= 3:
                card["work"] = None
                card["status"] = "failed" if card.get("status") == "drafting" else card.get("status")
                flags = dict(card.get("flags") or {})
                flags["notes"] = [*(flags.get("notes") or []), "Drafting failed three times; try Rewrite or skip"]
                card["flags"] = flags
            else:
                card["work"] = work
            save_card(ctx, card)
            stats["failed"] += 1
            log.error(f"work:{card['id']}", exc)
    return stats
