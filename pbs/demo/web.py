"""Mock web for offline runs: builds feed documents for seed sources around a reference time."""

from __future__ import annotations

import base64
import datetime as dt
import json
import re
from email.utils import format_datetime
from typing import Any
from xml.sax.saxutils import escape

import httpx

from .. import ids, timeutil
from ..images import demo_png


def rss(title: str, items: list[dict[str, Any]]) -> str:
    parts = [f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{escape(title)}</title>']
    for it in items:
        src = f'<source url="https://example.com">{escape(it["publisher"])}</source>' if it.get("publisher") else ""
        parts.append(
            f"<item><title>{escape(it['title'])}</title><link>{escape(it['url'])}</link>"
            f"<description>{escape(it.get('summary', ''))}</description>"
            f"<pubDate>{format_datetime(it['at'])}</pubDate>{src}</item>"
        )
    parts.append("</channel></rss>")
    return "".join(parts)


def atom(title: str, items: list[dict[str, Any]]) -> str:
    parts = [f'<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>{escape(title)}</title>']
    for it in items:
        parts.append(
            f"<entry><title>{escape(it['title'])}</title><link href=\"{escape(it['url'])}\"/>"
            f"<summary>{escape(it.get('summary', ''))}</summary>"
            f"<updated>{timeutil.iso(it['at'])}</updated><published>{timeutil.iso(it['at'])}</published></entry>"
        )
    parts.append("</feed>")
    return "".join(parts)


def build_world(ref: dt.datetime | None = None) -> dict[str, tuple[int, str, str]]:
    """Map of URL fragment -> (status, content-type, body)."""
    ref = ref or timeutil.now()

    def at(hours_ago: float) -> dt.datetime:
        return ref - dt.timedelta(hours=hours_ago)

    world: dict[str, tuple[int, str, str]] = {}
    xml = "application/rss+xml"

    world["techcrunch.com/category/artificial-intelligence"] = (200, xml, rss("TechCrunch AI", [
        {"title": "OpenAI launches an agent platform aimed at enterprise automation teams",
         "url": "https://techcrunch.com/2026/09/27/openai-agent-platform-enterprise/",
         "summary": "The platform lets companies build agents that operate internal tools, with audit logs and "
                    "approval steps. Early customers include banks and insurers piloting back-office workflows.",
         "at": at(6)},
        {"title": "Anthropic raises $5 billion as enterprise demand for Claude grows",
         "url": "https://techcrunch.com/2026/09/27/anthropic-raises/",
         "summary": "The round values the company at $183 billion. Enterprise revenue now makes up 80% of sales.",
         "at": at(9)},
        {"title": "UiPath adds agentic orchestration to its automation suite",
         "url": "https://techcrunch.com/2026/09/26/uipath-agentic-orchestration/",
         "summary": "UiPath says customers can mix RPA bots, AI agents and people in one governed workflow, with "
                    "human approval steps for exceptions.", "at": at(20)},
    ]))
    world["theverge.com/rss/ai-artificial-intelligence"] = (200, xml, rss("The Verge AI", [
        {"title": "OpenAI's new agent platform wants to run your company's back office",
         "url": "https://www.theverge.com/2026/9/27/openai-agents-enterprise",
         "summary": "OpenAI's enterprise agent platform ships with connectors, approvals and audit logs for "
                    "regulated industries like banking.", "at": at(4)},
        {"title": "Why AI coding agents still struggle with legacy enterprise systems",
         "url": "https://www.theverge.com/2026/9/26/ai-agents-legacy-systems",
         "summary": "Mainframes, brittle integrations and missing documentation remain the hard part.",
         "at": at(26)},
    ]))
    world["news.google.com/rss/search?q=site%3Aventurebeat.com"] = (200, xml, rss("Google News", [
        {"title": "OpenAI debuts enterprise agent platform with human approval steps - VentureBeat",
         "url": "https://news.google.com/rss/articles/venturebeat-openai-enterprise-agent-platform",
         "publisher": "VentureBeat",
         "summary": "Agents can be scoped to specific tools, and every action is logged for compliance review.",
         "at": at(5)},
    ]))
    world["news.google.com/rss/search?q=UiPath"] = (200, xml, rss("Google News", [
        {"title": "Automation Anywhere unveils AI agents for finance operations - Business Wire",
         "url": "https://news.google.com/rss/articles/aa-agents-finance", "publisher": "Business Wire",
         "summary": "", "at": at(12)},
        {"title": "UiPath brings agentic orchestration to regulated industries - Reuters",
         "url": "https://news.google.com/rss/articles/uipath-reuters", "publisher": "Reuters", "summary": "",
         "at": at(18)},
    ]))
    world["huggingface.co/api/daily_papers"] = (200, "application/json", json.dumps([
        {"paper": {"id": "2609.01234", "title": "AgentBench-Enterprise: Evaluating LLM Agents on Real Back-Office "
                   "Workflows", "summary": "We introduce a benchmark of 1,200 tasks from finance and insurance "
                   "operations. The best agent completes 41% of tasks end to end; failures cluster around "
                   "exception handling.", "upvotes": 142}, "publishedAt": timeutil.iso(at(14))},
        {"paper": {"id": "2609.04567", "title": "Small Models, Long Tools: Tool-Use Distillation for Efficient Agents",
                   "summary": "Distilling tool-use traces into a 3B model recovers 90% of teacher accuracy.",
                   "upvotes": 64}, "publishedAt": timeutil.iso(at(16))},
    ]))
    world["hn.algolia.com/api/v1/search?tags=front_page"] = (200, "application/json", json.dumps({"hits": [
        {"title": "OpenAI Agent Platform", "url": "https://openai.com/index/agent-platform/", "points": 612,
         "num_comments": 388, "created_at": timeutil.iso(at(5)), "objectID": "41000001"},
        {"title": "Show the evals: why our agent benchmark numbers didn't hold up in production",
         "url": "https://example.dev/blog/evals-production", "points": 233, "num_comments": 91,
         "created_at": timeutil.iso(at(15)), "objectID": "41000002"},
    ]}))
    world["export.arxiv.org/api/query"] = (200, "application/atom+xml", atom("arXiv", [
        {"title": "Measuring Exception Handling in LLM Agents for Business Process Automation",
         "url": "http://arxiv.org/abs/2609.07777v1",
         "summary": "We study how LLM agents recover from exceptions in invoice, KYC and claims workflows.",
         "at": at(30)},
    ]))
    world["modelcontextprotocol/python-sdk/releases"] = (200, "application/atom+xml", atom("Releases", [
        {"title": "v1.20.0: streamable HTTP improvements and auth fixes",
         "url": "https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.20.0",
         "summary": "Adds resumable streams and tightens OAuth handling for remote MCP servers.", "at": at(40)},
    ]))
    world["simonwillison.net/atom"] = (200, "application/atom+xml", atom("Simon Willison", [
        {"title": "Notes on OpenAI's agent platform", "url": "https://simonwillison.net/2026/Sep/27/agent-platform/",
         "summary": "The interesting part is the permission model: agents get scoped tools and every call is logged.",
         "at": at(3)},
    ]))

    # Affairs: world, India, Bihar (incl. Hindi)
    world["feeds.bbci.co.uk/news/world"] = (200, xml, rss("BBC World", [
        {"title": "Global leaders agree framework on AI safety testing at summit",
         "url": "https://www.bbc.com/news/world-ai-summit-framework",
         "summary": "Twenty-eight countries signed a framework for pre-deployment testing of frontier AI models.",
         "at": at(10)},
        {"title": "Stampede at railway station kills 12 during festival rush",
         "url": "https://www.bbc.com/news/world-asia-stampede",
         "summary": "Officials said 12 people died and dozens were injured.", "at": at(7)},
    ]))
    world["thehindu.com/news/national"] = (200, xml, rss("The Hindu", [
        {"title": "Cabinet approves ₹12,000 crore semiconductor packaging push",
         "url": "https://www.thehindu.com/news/national/semiconductor-packaging-approval/article1.ece",
         "summary": "The Union Cabinet approved incentives worth ₹12,000 crore for chip packaging units in three states.",
         "at": at(11)},
        {"title": "Parliamentary panel to hear experts on simultaneous elections bill",
         "url": "https://www.thehindu.com/news/national/one-nation-one-election-panel/article2.ece",
         "summary": "The joint committee examining the bills will hear constitutional experts next week.",
         "at": at(22)},
    ]))
    world["hindustantimes.com/feeds/rss/india-news"] = (200, xml, rss("HT India", [
        {"title": "Centre clears ₹12,000-crore scheme to boost chip packaging",
         "url": "https://www.hindustantimes.com/india-news/chip-packaging-scheme-101.html",
         "summary": "Incentives target assembly and testing units; Bihar is among states seeking a unit.",
         "at": at(9)},
    ]))
    world["news.google.com/rss/search?q=Bihar"] = (200, xml, rss("Google News", [
        {"title": "Bihar to build 3 new industrial corridors along expressways, says minister - Hindustan Times",
         "url": "https://news.google.com/rss/articles/bihar-corridors", "publisher": "Hindustan Times",
         "summary": "", "at": at(8)},
        {"title": "Patna Metro priority corridor to open for passengers next month - Times of India",
         "url": "https://news.google.com/rss/articles/patna-metro", "publisher": "Times of India",
         "summary": "", "at": at(13)},
    ]))
    world["news.google.com/rss/search?q=%E0%A4%AC%E0%A4%BF%E0%A4%B9%E0%A4%BE%E0%A4%B0"] = (200, xml, rss("Google News", [
        {"title": "बिहार में एक्सप्रेसवे के किनारे तीन नए औद्योगिक गलियारे बनेंगे - लाइव हिन्दुस्तान",
         "url": "https://news.google.com/rss/articles/hi-bihar-corridors", "publisher": "लाइव हिन्दुस्तान",
         "summary": "", "at": at(7)},
    ]))
    world["en.wikipedia.org/api/rest_v1/feed/onthisday"] = (200, "application/json", json.dumps({"events": [
        {"text": "The first Bihar Legislative Assembly session is convened in Patna.", "year": 1952,
         "pages": [{"extract": "The Bihar Legislative Assembly is the lower house of the Bihar legislature.",
                    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Bihar_Legislative_Assembly"}}}]},
        {"text": "A treaty is signed somewhere far away.", "year": 1815, "pages": []},
    ]}))

    # Startups
    world["inc42.com/feed"] = (200, xml, rss("Inc42", [
        {"title": "Bengaluru AI startup raises $30 Mn to automate insurance claims",
         "url": "https://inc42.com/buzz/ai-claims-startup-raises/",
         "summary": "The Series B round will fund expansion into Southeast Asia; the startup says claims are "
                    "processed 4x faster.", "at": at(15)},
    ]))
    world["techcrunch.com/category/startups"] = (200, xml, rss("TechCrunch Startups", [
        {"title": "YC's latest batch is two-thirds AI agent companies",
         "url": "https://techcrunch.com/2026/09/26/yc-batch-ai-agents/",
         "summary": "Of 160 companies, roughly 105 build agents for specific business workflows.", "at": at(28)},
    ]))
    # A broken source to exercise health tracking.
    world["feeds.npr.org/1004"] = (500, "text/plain", "upstream error")
    return world


class MockWeb:
    """httpx transport serving `build_world()`. Unknown URLs get an empty feed (or empty JSON for APIs).

    With `filler=True` (the desk demo), unknown feeds return two posts from several days ago instead: every
    source then looks alive on the Sources page, but nothing old enough to become today's news.
    """

    def __init__(self, world: dict[str, tuple[int, str, str]] | None = None, filler: bool = False):
        self.world = world if world is not None else build_world()
        self.filler = filler
        self.requests: list[str] = []

    def _match(self, url: str) -> tuple[int, str, str] | None:
        best = None
        for frag, resp in self.world.items():
            if frag in url and (best is None or len(frag) > len(best[0])):
                best = (frag, resp)
        return best[1] if best else None

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        hit = self._match(url)
        if hit is None and (image := self._image(request, url)) is not None:
            return image
        if hit is None:
            if "algolia" in url or "api/" in url:
                return httpx.Response(200, json={"hits": [], "events": []})
            return httpx.Response(200, headers={"content-type": "application/rss+xml"},
                                  text=rss("feed", self._older_posts(url) if self.filler else []))
        status, ctype, body = hit
        return httpx.Response(status, headers={"content-type": ctype, "etag": f'"{hash(body) & 0xffff}"'},
                              content=body.encode("utf-8"))

    @staticmethod
    def _image(request: httpx.Request, url: str) -> httpx.Response | None:
        """The image services, answering like the real ones with a small generated picture (images.demo_png)."""
        kind = ("cloudflare" if "api.cloudflare.com" in url and "/ai/run/" in url
                else "gemini" if "generativelanguage.googleapis.com" in url and "image" in url and ":generateContent" in url
                else "xai" if "api.x.ai/v1/images/generations" in url else None)
        if kind is None:
            return None
        body = request.content or b""
        wide = False
        m = re.search(rb'name="width"\r\n\r\n(\d+)\r\n.*?name="height"\r\n\r\n(\d+)', body, re.S)
        if m:
            wide = int(m.group(1)) > int(m.group(2))
        elif b'"16:9"' in body:
            wide = True
        size = (400, 225) if wide else (320, 400)
        png = demo_png(f"{url}:{len(body)}", *size)
        b64 = base64.b64encode(png).decode("ascii")
        if kind == "cloudflare":
            return httpx.Response(200, json={"result": {"image": b64}, "success": True, "errors": [], "messages": []})
        if kind == "gemini":
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"inlineData": {"mimeType": "image/png", "data": b64}}]}}]})
        return httpx.Response(200, json={"data": [{"b64_json": b64}]})

    @staticmethod
    def _older_posts(url: str) -> list[dict[str, Any]]:
        host = httpx.URL(url).host or "example.com"
        key = ids.short_hash(url)
        return [{"title": f"Earlier post {n} from {host} ({key})", "url": f"https://{host}/archive/{key}-{n}",
                 "summary": "", "at": timeutil.now() - dt.timedelta(days=4 + n)} for n in (1, 2)]

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)
