"""What works on LinkedIn and X: a reviewed guide shipped with the code, the updates Ankit approved, and a monthly
research step that reads recent coverage of both platforms and proposes changes (never applied without him).

Every draft, rewrite and adaptation gets the current rules for its platform and format (style.py), after his own
learned style rules, which win when they disagree.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from functools import cache
from importlib import resources
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from . import log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import AllProvidersFailed, BudgetExhausted, LLMError, LLMRequest
from .scout.fetch import FetchJob, fetch_all, no_sleep
from .scout.parsers import _parse_feed
from .scout.sources import gnews_search_url

UPDATES = "platform_guide_updates"  # settings key: the changes he approved, in order
RESEARCH_MONTH = "platform_research_month"  # settings key: the last month the research ran
LABEL = {"linkedin": "LinkedIn", "x": "X"}

# Recent coverage of how the platforms show posts and what works there (Google News, last 30 days).
QUERIES = {
    "linkedin": ['"LinkedIn algorithm" when:30d', 'LinkedIn creators posts reach engagement when:30d'],
    "x": ['"X algorithm" OR "Twitter algorithm" when:30d', 'X Twitter posts reach creators engagement when:30d'],
}


@cache
def base_guide() -> dict[str, Any]:
    return yaml.safe_load(resources.files("pbs.defaults").joinpath("platform_guide.yaml").read_text(encoding="utf-8"))


def current_rules(ctx: Ctx) -> list[dict[str, Any]]:
    """The guide with his approved updates applied: [{id, platform, format, text, source, sources, articles}]."""
    rules: list[dict[str, Any]] = []
    guide = base_guide()
    for platform in ("linkedin", "x"):
        for fmt, entries in (guide.get(platform) or {}).items():
            for e in entries or []:
                rules.append({"id": e["id"], "platform": platform, "format": None if fmt == "all" else fmt,
                              "text": e["text"], "source": "guide"})
    for ch in ctx.store.get_setting(UPDATES, []) or []:
        op = ch.get("op")
        if op == "add":
            rules.append({"id": ch["id"], "platform": ch["platform"], "format": ch.get("format"), "text": ch["text"],
                          "source": "research", "sources": ch.get("sources") or [],
                          "articles": ch.get("articles") or [], "added_at": ch.get("at")})
        elif op == "modify":
            for r in rules:
                if r["id"] == ch.get("rule_id"):
                    r.update(text=ch["text"], source="research", sources=ch.get("sources") or [],
                             articles=ch.get("articles") or [], added_at=ch.get("at"))
        elif op == "remove":
            rules = [r for r in rules if r["id"] != ch.get("rule_id")]
    return rules


def rules_for(ctx: Ctx, platform: str, fmt: str) -> list[str]:
    return [r["text"] for r in current_rules(ctx) if r["platform"] == platform and r["format"] in (None, fmt)]


def render(rules: list[str]) -> str:
    return "\n".join(f"- {r}" for r in rules) if rules else "- (No platform notes.)"


def apply_update(ctx: Ctx, change: dict[str, Any]) -> str | None:
    """Apply an approved guide change. Returns an error message, or None."""
    op = change.get("op")
    if op not in ("add", "modify", "remove"):
        return f"unknown change {op!r}"
    known = {r["id"] for r in current_rules(ctx)}
    if op in ("modify", "remove") and change.get("rule_id") not in known:
        return f"the rule {change.get('rule_id')} is no longer in the guide"
    if op in ("add", "modify") and not (change.get("text") or "").strip():
        return "the change has no text"
    updates = list(ctx.store.get_setting(UPDATES, []) or [])
    entry = {**change, "at": timeutil.now_iso()}
    if op == "add":
        entry["id"] = entry.get("id") or f"r-{change.get('platform')}-{len(updates) + 1}"
    updates.append(entry)
    ctx.store.set_setting(UPDATES, updates)
    return None


# ---------------------------------------------------------------------------
# Monthly research
# ---------------------------------------------------------------------------


def research_due(ctx: Ctx) -> bool:
    return ctx.store.get_setting(RESEARCH_MONTH) != ctx.local_now().strftime("%Y-%m")


class _Change(BaseModel):
    model_config = ConfigDict(extra="ignore")
    op: Literal["add", "modify", "remove"]
    rule_id: str | None = None
    platform: Literal["linkedin", "x"] | None = None
    format: str | None = None
    text: str | None = None
    why: str | None = None
    evidence: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"


class _ResearchOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str = ""
    changes: list[_Change] = Field(default_factory=list)


def _articles(ctx: Ctx) -> list[dict[str, Any]]:
    jobs = [FetchJob(key=f"{platform}:{i}", url=gnews_search_url(q, "en", "US"))
            for platform, qs in QUERIES.items() for i, q in enumerate(qs)]
    sc = ctx.settings.scouting
    results = asyncio.run(fetch_all(jobs, user_agent=sc.user_agent, timeout=sc.timeout_seconds, concurrency=4,
                                    transport=ctx.transport, **({"sleep": no_sleep} if ctx.transport is not None else {})))
    since = timeutil.now() - dt.timedelta(days=45)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for res in results:
        if not res.ok or not res.content:
            continue
        for item in _parse_feed({"kind": "gnews", "name": "Google News"}, res.content)[:15]:
            key = textutil.title_key(item["title"])
            published = timeutil.parse(item.get("published_at"))
            if key in seen or (published and published < since):
                continue
            seen.add(key)
            out.append({"platform": res.key.split(":")[0], **item})
    out.sort(key=lambda it: it.get("published_at") or "", reverse=True)
    return out[:20]


def research(ctx: Ctx) -> dict[str, Any]:
    """Read the month's coverage of both platforms and propose guide changes for him to approve."""
    from . import playbook

    month = ctx.local_now().strftime("%Y-%m")
    articles = _articles(ctx)
    if not articles:
        log.info("platform: no recent coverage found; guide unchanged")
        ctx.store.set_setting(RESEARCH_MONTH, month)
        return {"articles": 0, "proposals": 0}
    ref = {f"A{i}": a for i, a in enumerate(articles, 1)}
    rules = current_rules(ctx)
    rules_text = "\n".join(f"- {r['id']} [{LABEL[r['platform']]}{', ' + r['format'] if r['format'] else ''}]: {r['text']}"
                           for r in rules)
    payload = [{"id": k, "platform": a["platform"], "title": a["title"], "publisher": a.get("publisher"),
                "date": (a.get("published_at") or "")[:10] or None, "summary": textutil.truncate(a.get("summary"), 300)}
               for k, a in ref.items()]
    prompt = prompting.render("platform_research", display_name=ctx.settings.display_name, rules=rules_text,
                              input_json=payload)
    req = LLMRequest(task="research", system="You track how LinkedIn and X show posts, carefully and with evidence.",
                     prompt=prompt, max_output_tokens=2500, prompt_version=prompting.version("platform_research"))
    try:
        out, _ = ctx.llm.call_json(req, _ResearchOut)
    except (BudgetExhausted, AllProvidersFailed, LLMError, ValueError) as exc:
        log.info(f"platform: research skipped ({type(exc).__name__}); tries again next run")
        return {"articles": len(articles), "proposals": 0, "skipped": True}
    known = {r["id"]: r for r in rules}
    made = 0
    for ch in out.changes[:5]:
        cited = [ref[e] for e in dict.fromkeys(ch.evidence) if e in ref][:4]
        if not cited:
            continue  # no evidence from the articles: not proposed
        sources = [a["url"] for a in cited]
        target = known.get(ch.rule_id or "")
        platform = ch.platform or (target or {}).get("platform")
        if ch.op in ("modify", "remove") and not target:
            continue
        if ch.op in ("add", "modify") and not (ch.text or "").strip():
            continue
        if platform not in ("linkedin", "x"):
            continue
        change = {"op": ch.op, "rule_id": target["id"] if target else None, "platform": platform,
                  "format": ch.format if ch.format in ctx.settings.formats else None,
                  "text": textutil.truncate(ch.text, 300) if ch.text else None, "sources": sources,
                  "articles": [{"url": a["url"], "title": textutil.truncate(a["title"], 160),
                                "publisher": a.get("publisher")} for a in cited]}
        verb = {"add": "Add", "modify": "Update", "remove": "Remove"}[ch.op]
        title = f"{LABEL[platform]} guide: {verb.lower()} “{textutil.truncate(ch.text or target['text'], 110)}”"
        detail = " ".join(p for p in [textutil.truncate(ch.why, 300),
                                      f"Replaces: “{target['text']}”" if ch.op == "modify" and target else ""] if p)
        playbook.create_proposal(ctx, kind="platform_guide", title=title, detail=detail or None,
                                 payload={"guide_change": change}, evidence=sources, confidence=ch.confidence,
                                 source="research")
        made += 1
    ctx.store.set_setting(RESEARCH_MONTH, month)
    ctx.store.set_setting("platform_research_summary", {"month": month, "summary": textutil.truncate(out.summary, 400),
                                                         "articles": len(articles), "proposals": made})
    log.info(f"platform: research read {len(articles)} articles, proposed {made} guide changes")
    return {"articles": len(articles), "proposals": made}
