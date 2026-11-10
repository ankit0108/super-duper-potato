"""The scouts' web search: Tavily's free tier (about 1,000 searches a month, no card), with the TAVILY_API_KEY
secret. Gemini's free tier has no Google Search and Groq retired its search in September 2026, so this is how a
scout looks for public LinkedIn and X posts and what the web is saying.

Results are evidence that a search engine returned a page, nothing more: they say nothing about how a post
performed. Usage is counted per month against `websearch.monthly_cap`; only counts are logged.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from .. import log, textutil
from ..context import Ctx

ENV = "TAVILY_API_KEY"
URL = "https://api.tavily.com/search"
USAGE_KEY = "websearch_usage"  # {"month": "2026-11", "count": 41, "error": None}
DOMAINS = {"linkedin": ["linkedin.com"], "x": ["x.com", "twitter.com"]}


class SearchUnavailable(Exception):
    """No key, the month's searches are used up, or the service said no."""


def available() -> bool:
    return bool(os.environ.get(ENV, "").strip())


def _usage(ctx: Ctx) -> dict[str, Any]:
    month = ctx.local_date_str()[:7]
    row = ctx.store.get_setting(USAGE_KEY) or {}
    return row if row.get("month") == month else {"month": month, "count": 0, "error": None}


def remaining(ctx: Ctx) -> int:
    """Searches left this month (0 without a key)."""
    if not available():
        return 0
    return max(0, ctx.settings.websearch.monthly_cap - int(_usage(ctx).get("count") or 0))


def status(ctx: Ctx) -> dict[str, Any]:
    """For the desk: whether the scouts can search, and how much of the month is used."""
    usage = _usage(ctx)
    return {"available": available(), "used": int(usage.get("count") or 0),
            "cap": ctx.settings.websearch.monthly_cap, "error": usage.get("error")}


async def _post(body: dict[str, Any], transport: Any, timeout: float) -> httpx.Response:
    headers = {"Authorization": f"Bearer {os.environ.get(ENV, '').strip()}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        return await client.post(URL, json=body, headers=headers)


def search(ctx: Ctx, query: str, *, where: str = "web", days: int = 3,
           max_results: int | None = None) -> list[dict[str, Any]]:
    """One search. `where`: "linkedin" or "x" keeps to that site's public posts; "web" is the open web.
    Returns [{url, title, content, published}], best first. Raises SearchUnavailable."""
    if not available():
        raise SearchUnavailable("no key")
    if remaining(ctx) <= 0:
        raise SearchUnavailable("the month's searches are used up")
    body: dict[str, Any] = {"query": textutil.normalize_ws(query)[:300], "search_depth": "basic", "topic": "general",
                            "max_results": max_results or ctx.settings.websearch.results,
                            "time_range": "day" if days <= 1 else "week" if days <= 7 else "month",
                            "include_answer": False}
    if where in DOMAINS:
        body["include_domains"] = DOMAINS[where]
    usage = _usage(ctx)
    try:
        resp = asyncio.run(_post(body, ctx.transport, ctx.settings.scouting.timeout_seconds))
        if resp.status_code == 400 and "time_range" in resp.text:
            body.pop("time_range")  # an older API version: ask once more without the date filter
            resp = asyncio.run(_post(body, ctx.transport, ctx.settings.scouting.timeout_seconds))
    except httpx.HTTPError as exc:
        raise SearchUnavailable(type(exc).__name__) from exc
    if resp.status_code != 200:
        # 401/403: the key; 429 and 432/433: the plan's limits. Kept for the desk, without the response text.
        usage["error"] = f"HTTP {resp.status_code}"
        ctx.store.set_setting(USAGE_KEY, usage)
        raise SearchUnavailable(f"HTTP {resp.status_code}")
    usage.update(count=int(usage.get("count") or 0) + 1, error=None)
    ctx.store.set_setting(USAGE_KEY, usage)
    try:
        rows = resp.json().get("results") or []
    except ValueError as exc:
        raise SearchUnavailable("unreadable reply") from exc
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        url = textutil.http_url(r.get("url"))
        title = textutil.normalize_ws(str(r.get("title") or ""))
        if url and title:
            out.append({"url": url, "title": title, "content": textutil.normalize_ws(str(r.get("content") or "")),
                        "published": r.get("published_date") if isinstance(r.get("published_date"), str) else None})
    return out


def log_use(ctx: Ctx, searches: int, found: int) -> None:
    usage = _usage(ctx)
    log.info(f"websearch: {searches} searches, {found} results kept ({usage.get('count', 0)} of "
             f"{ctx.settings.websearch.monthly_cap} used this month)")
