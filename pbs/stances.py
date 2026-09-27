"""Stances: seeded recurring issues, and proposals of new ones. The system never picks a side (FR-25)."""

from __future__ import annotations

import datetime as dt
import re
from functools import cache
from importlib import resources
from typing import Any
from urllib.parse import quote

import yaml
from pydantic import BaseModel, ConfigDict, Field

from . import log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import BudgetExhausted, LLMRequest


@cache
def seed_stances() -> list[dict[str, Any]]:
    return yaml.safe_load(resources.files("pbs.defaults").joinpath("stances.yaml").read_text(encoding="utf-8")) or []


def ensure_seeded(ctx: Ctx) -> int:
    if ctx.store.get_setting("stances_seeded"):
        return 0
    now = timeutil.now_iso()
    n = 0
    for s in seed_stances():
        if ctx.store.get("stances", s["id"]):
            continue
        ctx.store.insert("stances", {
            "id": s["id"], "issue": s["issue"], "tier": s.get("tier", "other"), "context": s.get("context"),
            "positions": s.get("positions") or [], "chosen": None, "status": "proposed",
            "sources": [{"url": f"https://en.wikipedia.org/w/index.php?search={quote(s['issue'])}",
                         "title": f"Background reading: {s['issue']}", "publisher": "Wikipedia"}],
            "keywords": s.get("keywords") or [], "created_by": "seed", "created_at": now, "updated_at": now,
        })
        n += 1
    ctx.store.set_setting("stances_seeded", True)
    return n


class _Issue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    key: str
    issue: str
    tier: str = "other"
    context: str = ""
    positions: list[dict[str, str]] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class _IssuesOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    issues: list[_Issue] = Field(default_factory=list)


def propose(ctx: Ctx, count: int = 3) -> int:
    """Propose new recurring issues from recent affairs topics that no stance covers yet."""
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=14))
    topics = ctx.store.select("topics", "scout = 'affairs' AND last_seen_at >= ?", (since,), order="n_sources DESC",
                              limit=40)
    existing = ctx.store.select("stances")
    payload = {"recent_affairs_topics": [textutil.truncate(t.get("title_en") or t.get("title"), 140) for t in topics],
               "existing_issues": [s["issue"] for s in existing], "count": count}
    prompt = prompting.render("stances", input_json=payload, count=count, display_name=ctx.settings.display_name)
    req = LLMRequest(task="stances", system="You describe public debates fairly and neutrally.", prompt=prompt,
                     max_output_tokens=2500, prompt_version=prompting.version("stances"))
    try:
        out, _ = ctx.llm.call_json(req, _IssuesOut)
    except (BudgetExhausted, ValueError) as exc:
        log.info(f"stances: proposals skipped ({type(exc).__name__})")
        return 0
    known = {s["id"] for s in existing} | {s["issue"].casefold() for s in existing}
    now = timeutil.now_iso()
    added = 0
    for issue in out.issues[:count]:
        key = re.sub(r"[^a-z0-9]+", "-", issue.key.casefold()).strip("-")[:48]
        positions = [{"key": re.sub(r"[^a-z0-9-]+", "-", (p.get("key") or p.get("label") or f"p{i}").casefold())[:30],
                      "label": textutil.truncate(p.get("label") or "", 80), "text": textutil.truncate(p.get("text") or "", 400)}
                     for i, p in enumerate(issue.positions[:4], 1) if p.get("text")]
        if not key or key in known or issue.issue.casefold() in known or len(positions) < 2:
            continue
        ctx.store.insert("stances", {
            "id": key, "issue": textutil.truncate(issue.issue, 160), "tier": issue.tier if issue.tier in
            ("world", "india", "bihar", "other") else "other", "context": textutil.truncate(issue.context, 400),
            "positions": positions, "chosen": None, "status": "proposed", "keywords": issue.keywords[:12],
            "sources": [{"url": f"https://en.wikipedia.org/w/index.php?search={quote(issue.issue)}",
                         "title": f"Background reading: {issue.issue}", "publisher": "Wikipedia"}],
            "created_by": "system", "created_at": now, "updated_at": now,
        })
        added += 1
    log.info(f"stances: proposed {added} new issues")
    return added


def match_issue(ctx: Ctx, text: str) -> str | None:
    """Stance id whose keywords appear in the text (used when triage doesn't name one)."""
    low = text.casefold()
    for s in ctx.store.select("stances", "status != 'archived'"):
        for kw in s.get("keywords") or []:
            if kw and re.search(rf"(?<![\w]){re.escape(kw.casefold())}(?![\w])", low):
                return s["id"]
    return None
