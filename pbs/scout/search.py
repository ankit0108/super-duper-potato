"""On-demand search (FR-15): reaches beyond the daily source lists, for requests and for cards without sources.

A query is first turned into a search plan that says what Ankit most likely means, given his profile and pillars
("AI automation" → automating business processes with AI, not factory robots): a few specific queries, words that
mark the wrong meaning, an arXiv query, and how recent results must be. Results from Google News, Hacker News,
arXiv and Reddit are then scored (relevance, recency, wrong-meaning words) and, when a model is available,
checked once more for relevance. Without a model the plan comes from his pillar keywords instead.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import ids, log, prompting, textutil, timeutil
from ..context import Ctx
from ..llm.base import AllProvidersFailed, BudgetExhausted, LLMError, LLMRequest
from .fetch import FetchJob, fetch_all, no_sleep
from .parsers import _parse_feed, _parse_hn
from .scouting import DedupIndex
from .sources import gnews_search_url

_INDIA_HINT = re.compile(r"\b(india|indian|bihar|patna|delhi|mumbai|modi|rupee|crore|lakh)\b|[ऀ-ॿ]", re.I)
_ARXIV_SAFE = re.compile(r"[^A-Za-z0-9 :\"()\-_.+]")
_OPERATORS = re.compile(r'"|\bOR\b|\bAND\b|[()]')
DEFAULT_RECENCY_DAYS = 14
PAPER_MAX_DAYS = 90
KEEP = 12  # results kept for drafting and storage


# ---------------------------------------------------------------------------
# The plan: what he means
# ---------------------------------------------------------------------------


@dataclass
class SearchPlan:
    query: str
    interpretation: str
    queries: list[str]
    exclude: list[str] = field(default_factory=list)
    arxiv: str | None = None
    recency_days: int = DEFAULT_RECENCY_DAYS
    background: bool = False
    source: str = "fallback"  # "model" when a model planned it

    def as_dict(self) -> dict[str, Any]:
        return {"interpretation": self.interpretation, "queries": self.queries, "exclude": self.exclude,
                "recency_days": self.recency_days, "planned_by": self.source}


class _PlanOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    interpretation: str = ""
    queries: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    arxiv: str | None = None
    recency_days: int | None = None
    background: bool = False

    @field_validator("queries", "exclude", mode="before")
    @classmethod
    def _strings(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = [v]
        return [str(x) for x in v or [] if isinstance(x, (str, int, float)) and str(x).strip()]


def _clean_query(q: str) -> str:
    q = re.sub(r"\bwhen:\d+[dhmy]\b|\bsite:\S+", " ", q)  # the plan adds recency itself; no site filters
    return textutil.normalize_ws(q)[:160]


def _pillar_lines(ctx: Ctx) -> str:
    lines = []
    for platform in ("linkedin", "x"):
        for key, p in ctx.settings.pillars(platform).items():
            kws = ", ".join(p.keywords[:12])
            lines.append(f"- {'LinkedIn' if platform == 'linkedin' else 'X'} {key}: {p.label}. "
                         f"{p.description.strip()} (keywords: {kws})")
    return "\n".join(lines)


def plan_search(ctx: Ctx, query: str, notes: str | None = None, recency_days: int | None = None) -> SearchPlan:
    """What he most likely means, as concrete searches. A model plans it when one is available."""
    from ..draft import profile_text

    query = textutil.normalize_ws(query)
    payload = {"query": query, "notes": (notes or "").strip() or None,
               "today": ctx.local_date_str()}
    prompt = prompting.render("search_plan", display_name=ctx.settings.display_name,
                              profile=profile_text(ctx.settings.profile), pillars=_pillar_lines(ctx),
                              input_json=payload)
    req = LLMRequest(task="search_plan", system="You plan precise news and research searches.", prompt=prompt,
                     max_output_tokens=900, prompt_version=prompting.version("search_plan"))
    try:
        out, _ = ctx.llm.call_json(req, _PlanOut)
    except (BudgetExhausted, AllProvidersFailed, LLMError, ValueError) as exc:
        log.info(f"search: planning unavailable ({type(exc).__name__}); using his pillar keywords")
        return fallback_plan(ctx, query, notes, recency_days)
    low = query.casefold()
    queries = [q for q in dict.fromkeys(_clean_query(q) for q in out.queries) if len(q) >= 2][:3]
    exclude = [w for w in dict.fromkeys(textutil.normalize_ws(w).casefold() for w in out.exclude)
               if w and " " not in w and w not in low][:5]
    days = recency_days or out.recency_days or DEFAULT_RECENCY_DAYS
    return SearchPlan(
        query=query,
        interpretation=textutil.truncate(textutil.normalize_ws(out.interpretation), 240) or query,
        queries=queries or [query],
        exclude=exclude,
        arxiv=_arxiv_query(out.arxiv) if out.arxiv else None,
        recency_days=max(3, min(90, int(days))),
        background=bool(out.background),
        source="model",
    )


def fallback_plan(ctx: Ctx, query: str, notes: str | None = None, recency_days: int | None = None) -> SearchPlan:
    """Without a model: add the keywords of his best-matching LinkedIn pillar and X lane to the query."""
    text = f"{query} {notes or ''}".casefold()
    q_tokens = set(textutil.sim_tokens(query))
    queries = [query]
    labels = []
    for platform in ("linkedin", "x"):
        best: tuple[int, float, str] | None = None
        for key, p in ctx.settings.pillars(platform).items():
            hits = sum(1 for k in p.keywords if re.search(rf"(?<![\w]){re.escape(k.casefold())}(?![\w])", text))
            if hits and (best is None or (hits, p.weight) > best[:2]):
                best = (hits, p.weight, key)
        if not best:
            continue
        pillar = ctx.settings.pillar(platform, best[2])
        extra = [k for k in pillar.keywords  # type: ignore[union-attr]
                 if not set(textutil.sim_tokens(k)) & q_tokens and k.casefold() not in text][:3]
        if extra:
            terms = " OR ".join(f'"{k}"' if " " in k else k for k in extra)
            queries.append(f"{query} ({terms})")
            labels.append(pillar.label.lower())  # type: ignore[union-attr]
    words = " AND ".join(f"all:{t}" for t in textutil.sim_tokens(query)[:4])
    return SearchPlan(query=query,
                      interpretation=f"{query}, as it relates to {' and '.join(labels)}" if labels else query,
                      queries=list(dict.fromkeys(queries))[:3], arxiv=words or None,
                      recency_days=recency_days or DEFAULT_RECENCY_DAYS)


def _arxiv_query(raw: str) -> str | None:
    q = _ARXIV_SAFE.sub(" ", raw or "")
    q = textutil.normalize_ws(q)
    if q.count('"') % 2:
        q = q.replace('"', "")
    return q[:300] or None


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def _plain(q: str) -> str:
    """A query without search operators, for engines that don't understand them (HN, Reddit)."""
    return textutil.normalize_ws(_OPERATORS.sub(" ", q))


def search_jobs(plan: SearchPlan, now: dt.datetime | None = None) -> list[tuple[FetchJob, dict[str, Any]]]:
    now = now or timeutil.now()
    jobs: list[tuple[FetchJob, dict[str, Any]]] = []

    def add(key: str, url: str, kind: str, name: str, lang: str = "en") -> None:
        jobs.append((FetchJob(key=key, url=url), {"id": key, "kind": kind, "name": name, "lang": lang}))

    minus = " ".join(f"-{w}" for w in plan.exclude)
    window = f"when:{plan.recency_days}d"
    for i, q in enumerate(plan.queries[:3]):
        add(f"search:gnews-{i}", gnews_search_url(textutil.normalize_ws(f"{q} {minus} {window}"), "en", "US"),
            "gnews", "Google News")
    if _INDIA_HINT.search(" ".join([plan.query, *plan.queries])):
        add("search:gnews-in", gnews_search_url(textutil.normalize_ws(f"{plan.queries[0]} {minus} {window}"),
                                                "en", "IN"), "gnews", "Google News India")
        add("search:gnews-hi", gnews_search_url(plan.query, "hi"), "gnews", "Google News (Hindi)", "hi")
    since = int((now - dt.timedelta(days=plan.recency_days * 2)).timestamp())
    add("search:hn", f"https://hn.algolia.com/api/v1/search?query={quote(_plain(plan.queries[0]))}&tags=story"
        f"&hitsPerPage=20&numericFilters=created_at_i>{since}", "hn_search", "Hacker News")
    if plan.arxiv:
        add("search:arxiv", f"https://export.arxiv.org/api/query?search_query={quote(plan.arxiv)}"
            "&sortBy=submittedDate&sortOrder=descending&max_results=12", "arxiv", "arXiv")
    add("search:reddit", f"https://www.reddit.com/search.rss?q={quote(_plain(plan.queries[0]))}&sort=relevance"
        "&t=month", "reddit", "Reddit")
    if plan.background:
        add("search:wikipedia", "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=3"
            f"&srsearch={quote(plan.query)}", "wikipedia_search", "Wikipedia")
    return jobs


def _parse_wikipedia_search(content: bytes) -> list[dict[str, Any]]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    out = []
    for hit in (data.get("query") or {}).get("search", []):
        title = hit.get("title")
        if not title:
            continue
        out.append({"url": f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}", "title": title,
                    "summary": textutil.strip_html(hit.get("snippet")), "published_at": None, "lang": "en",
                    "publisher": "Wikipedia", "signals": {"background": 1}})
    return out


# ---------------------------------------------------------------------------
# Scoring and the relevance check
# ---------------------------------------------------------------------------


def _wrong_meaning(plan: SearchPlan, text: str) -> str | None:
    low = text.casefold()
    for w in plan.exclude:
        if re.search(rf"(?<![\w]){re.escape(w)}", low):
            return w
    return None


def _age_days(item: dict[str, Any], now: dt.datetime) -> float | None:
    t = timeutil.parse(item.get("published_at"))
    return max(0.0, (now - t).total_seconds() / 86400) if t else None


def score(plan: SearchPlan, src: dict[str, Any], item: dict[str, Any], now: dt.datetime) -> float:
    toks = set(textutil.sim_tokens(f"{item.get('title')} {item.get('summary')}"))
    q = set(textutil.sim_tokens(plan.query))
    meaning = set(textutil.sim_tokens(" ".join([plan.interpretation, *plan.queries]))) - q
    rel = len(q & toks) / max(1, len(q)) + 0.5 * min(1.0, len(meaning & toks) / 3)
    age = _age_days(item, now)
    recency = 0.5 if age is None else 0.5 ** (age / max(1.0, plan.recency_days / 2))
    bonus = {"grounded": 0.3, "arxiv": 0.05}.get(src["kind"], 0.0)
    return round(rel + 0.6 * recency + bonus, 4)


def keep_recent(plan: SearchPlan, src: dict[str, Any], item: dict[str, Any], now: dt.datetime) -> bool:
    age = _age_days(item, now)
    if age is None:
        return True
    limit = PAPER_MAX_DAYS if src["kind"] == "arxiv" else plan.recency_days * 2
    return age <= limit


class _RerankOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    keep: list[str] = Field(default_factory=list)

    @field_validator("keep", mode="before")
    @classmethod
    def _ids(cls, v: Any) -> Any:
        return [str(x) for x in v or [] if isinstance(x, (str, int))]


def rerank(ctx: Ctx, plan: SearchPlan, found: list[tuple[dict[str, Any], dict[str, Any]]]
           ) -> list[tuple[dict[str, Any], dict[str, Any]]] | None:
    """Keep the results a model judges to be about what he means, best first. None if no model answered."""
    if not found:
        return found
    ref = {f"R{i}": pair for i, pair in enumerate(found[:30], 1)}
    payload = [{"id": k, "title": textutil.truncate(p[1].get("title"), 160), "publisher": p[1].get("publisher"),
                "date": (p[1].get("published_at") or "")[:10] or None,
                "summary": textutil.truncate(p[1].get("summary"), 160) or None} for k, p in ref.items()]
    prompt = prompting.render("search_rerank", display_name=ctx.settings.display_name, query=plan.query,
                              interpretation=plan.interpretation, input_json=payload)
    req = LLMRequest(task="search_rerank", system="You judge search results for relevance, strictly.",
                     prompt=prompt, max_output_tokens=600, prompt_version=prompting.version("search_rerank"))
    try:
        out, _ = ctx.llm.call_json(req, _RerankOut)
    except (BudgetExhausted, AllProvidersFailed, LLMError, ValueError) as exc:
        log.info(f"search: relevance check unavailable ({type(exc).__name__})")
        return None
    kept = [ref[k] for k in dict.fromkeys(out.keep) if k in ref]
    return kept


# ---------------------------------------------------------------------------
# Running a search
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    plan: SearchPlan
    found: list[tuple[dict[str, Any], dict[str, Any]]]  # (pseudo source, raw item), best first
    fetched: int = 0
    checked: bool = False  # a model confirmed relevance

    def summary(self) -> dict[str, Any]:
        return {**self.plan.as_dict(), "results": self.fetched, "kept": len(self.found), "checked": self.checked}


def run_search(ctx: Ctx, query: str, notes: str | None = None, *, recency_days: int | None = None,
               plan: SearchPlan | None = None) -> SearchResult:
    plan = plan or plan_search(ctx, query, notes, recency_days)
    jobs = search_jobs(plan)
    sc = ctx.settings.scouting
    results = asyncio.run(fetch_all([j for j, _ in jobs], user_agent=sc.user_agent, timeout=sc.timeout_seconds,
                                    concurrency=4, transport=ctx.transport,
                                    **({"sleep": no_sleep} if ctx.transport is not None else {})))
    meta = {j.key: m for j, m in jobs}
    raw_found: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for res in results:
        src = meta[res.key]
        if not res.ok or not res.content:
            continue
        try:
            if src["kind"] in ("gnews", "arxiv", "reddit"):
                raw = _parse_feed({**src, "kind": src["kind"]}, res.content)
            elif src["kind"] == "hn_search":
                raw = _parse_hn({"kind": "hn_search"}, res.content)
            elif src["kind"] == "wikipedia_search":
                raw = _parse_wikipedia_search(res.content)
            else:
                raw = []
        except Exception as exc:  # noqa: BLE001
            log.error(f"search:{res.key}", exc)
            raw = []
        raw_found.extend((src, item) for item in raw[:12])
    raw_found.extend(grounded_search(ctx, plan))
    fetched = len(raw_found)

    now = timeutil.now()
    seen: set[str] = set()
    scored: list[tuple[float, tuple[dict[str, Any], dict[str, Any]]]] = []
    dropped = {"old": 0, "wrong_meaning": 0, "duplicate": 0}
    for src, item in raw_found:
        key = textutil.canonical_url(item.get("url")) or textutil.title_key(item.get("title"))
        if key in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(key)
        if not keep_recent(plan, src, item, now):
            dropped["old"] += 1
            continue
        if src["kind"] != "grounded" and _wrong_meaning(plan, f"{item.get('title')} {item.get('summary')}"):
            dropped["wrong_meaning"] += 1
            continue
        scored.append((score(plan, src, item, now), (src, item)))
    scored.sort(key=lambda s: -s[0])
    found = [pair for _, pair in scored]
    checked = False
    kept = rerank(ctx, plan, found)
    if kept:
        found, checked = kept, True
    log.info(f"search: {fetched} results, {len(found)} kept (dropped {dropped['old']} old, "
             f"{dropped['wrong_meaning']} off-meaning; plan by {plan.source}; checked={checked})")
    return SearchResult(plan=plan, found=found[:KEEP], fetched=fetched, checked=checked)


def grounded_search(ctx: Ctx, plan: SearchPlan) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Gemini with Google Search grounding, when the free tier allows it (skipped for the day once it says no)."""
    if ctx.llm.grounding_off_today():
        return []
    try:
        resp = ctx.llm.call(LLMRequest(
            task="search", system="You are a careful research assistant. Only state facts supported by search results.",
            prompt=(f"Find the most important recent facts and developments about: {plan.interpretation}\n"
                    f"(his words: {plan.query})\n"
                    "Write 5 to 8 short bullet points, each with a date where known. No opinions."),
            json_mode=False, grounding=True, max_output_tokens=1200))
    except (BudgetExhausted, AllProvidersFailed, LLMError) as exc:
        log.info(f"search: grounding unavailable ({type(exc).__name__})")
        return []
    src = {"id": "search:grounded", "kind": "grounded", "name": "Google Search (via Gemini)", "lang": "en"}
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if resp.grounding:
        out.append((src, {"url": resp.grounding[0]["url"], "title": f"Search summary: {plan.query}",
                          "summary": textutil.truncate(resp.text, 700), "published_at": None, "lang": "en",
                          "publisher": "Google Search summary", "signals": {"grounded": 1}}))
    for g in resp.grounding[:6]:
        out.append((src, {"url": g["url"], "title": g.get("title") or textutil.url_host(g["url"]),
                          "summary": "", "published_at": None, "lang": "en",
                          "publisher": g.get("title") or "Web", "signals": {"grounded": 1}}))
    return out


# ---------------------------------------------------------------------------
# Storing results as items
# ---------------------------------------------------------------------------


def ingest_results(ctx: Ctx, found: list[tuple[dict[str, Any], dict[str, Any]]], origin: str,
                   limit: int = KEEP) -> list[str]:
    """Store search results as items (reusing existing items for URLs we already have). Returns item ids."""
    index = DedupIndex(ctx.store, ctx.settings.scouting.dedup_window_days)
    now = timeutil.now_iso()
    item_ids: list[str] = []
    for src, raw in found:
        canonical = textutil.canonical_url(raw["url"])
        key = textutil.title_key(raw["title"])
        existing = index.find(canonical, key, raw["title"])
        if existing:
            if existing not in item_ids:
                item_ids.append(existing)
            continue
        item_id = ids.stable_id("itm", canonical or key)
        signals = dict(raw.get("signals") or {})
        signals["publisher"] = raw.get("publisher") or src.get("name")
        ctx.store.upsert("items", {
            "id": item_id, "source_id": src["id"], "scout": "request", "url": raw["url"], "canonical_url": canonical,
            "title": raw["title"], "summary": raw.get("summary") or "", "lang": raw.get("lang") or "en",
            "published_at": raw.get("published_at"), "fetched_at": now, "title_key": key, "signals": signals,
            "origin": origin,
        })
        index.add(item_id, canonical, key, raw["title"])
        item_ids.append(item_id)
    return item_ids[:limit]
