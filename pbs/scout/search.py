"""On-demand search for requests (FR-15): reaches beyond the daily source lists."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from urllib.parse import quote

from .. import log, textutil
from ..context import Ctx
from ..llm.base import BudgetExhausted, LLMError, LLMRequest
from .fetch import FetchJob, fetch_all
from .parsers import _parse_feed, _parse_hn
from .sources import gnews_search_url

_INDIA_HINT = re.compile(r"\b(india|indian|bihar|patna|delhi|mumbai|modi|rupee|crore|lakh)\b|[ऀ-ॿ]", re.I)


def search_jobs(query: str) -> list[tuple[FetchJob, dict[str, Any]]]:
    q = query.strip()
    jobs: list[tuple[FetchJob, dict[str, Any]]] = []

    def add(key: str, url: str, kind: str, name: str, lang: str = "en") -> None:
        jobs.append((FetchJob(key=key, url=url), {"id": key, "kind": kind, "name": name, "lang": lang}))

    add("search:gnews-en", gnews_search_url(f"{q} when:30d", "en", "US"), "gnews", "Google News")
    if _INDIA_HINT.search(q):
        add("search:gnews-in", gnews_search_url(f"{q} when:30d", "en", "IN"), "gnews", "Google News India")
        add("search:gnews-hi", gnews_search_url(q, "hi"), "gnews", "Google News (Hindi)", "hi")
    add("search:hn", f"https://hn.algolia.com/api/v1/search?query={quote(q)}&tags=story&hitsPerPage=15", "hn_search",
        "Hacker News")
    add("search:arxiv", f"https://export.arxiv.org/api/query?search_query=all:{quote(q)}&sortBy=relevance&max_results=8",
        "arxiv", "arXiv")
    add("search:wikipedia", "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=4"
        f"&srsearch={quote(q)}", "wikipedia_search", "Wikipedia")
    add("search:reddit", f"https://www.reddit.com/search.rss?q={quote(q)}&sort=relevance&t=month", "reddit", "Reddit")
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
                    "publisher": "Wikipedia", "signals": {}})
    return out


def run_search(ctx: Ctx, query: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Returns [(pseudo_source, raw_item)] ordered by relevance to the query."""
    jobs = search_jobs(query)
    sc = ctx.settings.scouting
    results = asyncio.run(fetch_all([j for j, _ in jobs], user_agent=sc.user_agent, timeout=sc.timeout_seconds,
                                    concurrency=4, transport=ctx.transport,
                                    **({"sleep": _nosleep} if ctx.transport is not None else {})))
    meta = {j.key: m for j, m in jobs}
    found: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for res in results:
        src = meta[res.key]
        if not res.ok or not res.content:
            continue
        try:
            if src["kind"] in ("gnews", "arxiv", "reddit"):
                raw = _parse_feed({**src, "kind": src["kind"]}, res.content)
            elif src["kind"] == "hn_search":
                raw = _parse_hn({"kind": "hn_show"}, res.content)
            elif src["kind"] == "wikipedia_search":
                raw = _parse_wikipedia_search(res.content)
            else:
                raw = []
        except Exception as exc:  # noqa: BLE001
            log.error(f"search:{res.key}", exc)
            raw = []
        for item in raw[:10]:
            found.append((src, item))
    grounded = grounded_search(ctx, query)
    found.extend(grounded)
    q_tokens = set(textutil.sim_tokens(query))

    def relevance(pair: tuple[dict[str, Any], dict[str, Any]]) -> float:
        item = pair[1]
        toks = set(textutil.sim_tokens(f"{item.get('title')} {item.get('summary')}"))
        overlap = len(q_tokens & toks) / max(1, len(q_tokens))
        bonus = 0.3 if pair[0]["kind"] == "grounded" else 0.0
        return overlap + bonus

    found.sort(key=relevance, reverse=True)
    log.info(f"search: {len(found)} results for request")
    return found


def grounded_search(ctx: Ctx, query: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Gemini with Google Search grounding, when the free tier allows it (checked by `pbs doctor`)."""
    try:
        resp = ctx.llm.call(LLMRequest(
            task="search", system="You are a careful research assistant. Only state facts supported by search results.",
            prompt=(f"Find the most important recent facts and developments about: {query}\n"
                    "Write 5 to 8 short bullet points, each with a date where known. No opinions."),
            json_mode=False, grounding=True, max_output_tokens=1200))
    except (BudgetExhausted, LLMError) as exc:
        log.info(f"search: grounding unavailable ({type(exc).__name__})")
        return []
    src = {"id": "search:grounded", "kind": "grounded", "name": "Google Search (via Gemini)", "lang": "en"}
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if resp.grounding:
        out.append((src, {"url": resp.grounding[0]["url"], "title": f"Search summary: {query}",
                          "summary": textutil.truncate(resp.text, 700), "published_at": None, "lang": "en",
                          "publisher": "Google Search summary", "signals": {"grounded": 1}}))
    for g in resp.grounding[:6]:
        out.append((src, {"url": g["url"], "title": g.get("title") or textutil.url_host(g["url"]),
                          "summary": "", "published_at": None, "lang": "en",
                          "publisher": g.get("title") or "Web", "signals": {"grounded": 1}}))
    return out


async def _nosleep(_s: float) -> None:
    return None
