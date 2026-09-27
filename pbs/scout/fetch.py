"""Polite async fetching with conditional requests, per-host limits and failure isolation."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx


@dataclass
class FetchResult:
    key: str
    url: str
    status: int | None
    content: bytes = b""
    etag: str | None = None
    last_modified: str | None = None
    error: str | None = None
    not_modified: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and (self.not_modified or (self.status is not None and 200 <= self.status < 300))


@dataclass
class FetchJob:
    key: str
    url: str
    etag: str | None = None
    last_modified: str | None = None


SLOW_HOSTS = {"news.google.com": 1.0, "www.reddit.com": 2.0, "export.arxiv.org": 3.0}


async def no_sleep(_seconds: float) -> None:
    """Politeness delays only matter against real hosts; offline runs (a mock transport) skip them."""


async def fetch_all(jobs: list[FetchJob], *, user_agent: str, timeout: float = 20, concurrency: int = 8,
                    transport: httpx.AsyncBaseTransport | None = None, max_bytes: int = 5_000_000,
                    sleep=asyncio.sleep) -> list[FetchResult]:
    sem = asyncio.Semaphore(concurrency)
    host_locks: dict[str, asyncio.Semaphore] = {}
    headers = {"User-Agent": user_agent, "Accept": "application/rss+xml, application/atom+xml, application/json, "
               "application/xml;q=0.9, text/xml;q=0.9, */*;q=0.5"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers,
                                 transport=transport) as client:

        async def one(job: FetchJob) -> FetchResult:
            host = urlsplit(job.url).hostname or ""
            lock = host_locks.setdefault(host, asyncio.Semaphore(1 if host in SLOW_HOSTS else 2))
            async with sem, lock:
                hdrs = {}
                if job.etag:
                    hdrs["If-None-Match"] = job.etag
                if job.last_modified:
                    hdrs["If-Modified-Since"] = job.last_modified
                result = await _get(client, job, hdrs, max_bytes)
                if result.status in (429, 500, 502, 503, 504) or (result.error and "Timeout" in result.error):
                    await sleep(2.0 + random.random())
                    result = await _get(client, job, hdrs, max_bytes)
                if host in SLOW_HOSTS:
                    await sleep(SLOW_HOSTS[host] * (0.5 + random.random()))
                return result

        return list(await asyncio.gather(*(one(j) for j in jobs)))


async def _get(client: httpx.AsyncClient, job: FetchJob, hdrs: dict[str, str], max_bytes: int) -> FetchResult:
    try:
        resp = await client.get(job.url, headers=hdrs)
    except httpx.HTTPError as exc:
        return FetchResult(job.key, job.url, None, error=f"{type(exc).__name__}")
    if resp.status_code == 304:
        return FetchResult(job.key, job.url, 304, not_modified=True, etag=job.etag, last_modified=job.last_modified)
    if resp.status_code >= 400:
        return FetchResult(job.key, job.url, resp.status_code, error=f"HTTP {resp.status_code}")
    content = resp.content[:max_bytes]
    return FetchResult(job.key, job.url, resp.status_code, content=content, etag=resp.headers.get("etag"),
                       last_modified=resp.headers.get("last-modified"))
