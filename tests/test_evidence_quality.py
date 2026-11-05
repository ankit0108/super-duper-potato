"""Regressions from the production audit, using synthetic data only."""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from pbs import draft, learn, performance, pulse, rank, timeutil, topics
from pbs.llm.base import BudgetExhausted, LLMError, LLMRequest, LLMResponse, ModelCycle
from pbs.llm.fake import FakeProvider
from pbs.llm.openai_compat import OpenAICompatProvider
from pbs.llm.router import Router
from pbs.scout.parsers import parse
from pbs.scout.scouting import DedupIndex, ingest_items
from pbs.scout.sources import sync_seeds
from pbs.settings import ProviderSpec


def test_earnings_of_different_companies_never_merge_even_in_old_cluster():
    rows = [
        {"id": "a", "title": "Acme Q2 profit jumps 5X to 201 Cr", "summary": "Quarterly profit and revenue rise."},
        {"id": "b", "title": "Beta Q2 profit falls 31% to 142 Cr", "summary": "Quarterly profit and revenue fall."},
        {"id": "c", "title": "Acme Q2 profit jumps five times to 201 Cr", "summary": "Quarterly profit and revenue rise."},
    ]
    for row in rows:
        row["topic_id"] = "old-contaminated-topic"
    groups = topics.cluster(rows, 0.32)
    assert {frozenset(g) for g in groups} == {frozenset(("a", "c")), frozenset(("b",))}


def test_split_old_topic_gets_distinct_ids_and_matching_primary_sources(make_ctx):
    ctx = make_ctx()
    raw = [{"title": title, "url": f"https://example.org/{i}", "published_at": timeutil.now_iso(),
            "summary": summary} for i, (title, summary) in enumerate([
                ("Acme Q2 profit rises 50%", "Acme reports higher profit."),
                ("Beta Q2 profit rises 40%", "Beta reports higher profit."),
            ])]
    item_ids, _ = ingest_items(ctx.store, {"id": "s", "scout": "startups"}, raw, DedupIndex(ctx.store, 7))
    ctx.store.insert("topics", {"id": "old", "title": "Acme Q2 profit rises 50%"})
    for iid in item_ids:
        ctx.store.update("items", iid, topic_id="old")
    ids = topics.build_topics(ctx)
    assert len(ids) == len(set(ids)) == 2
    for tid in ids:
        topic = ctx.store.get("topics", tid)
        assert draft.select_sources(ctx, topic)[0]["title"] == topic["title"]


def test_primary_source_tracks_the_subject_not_the_newest_unrelated_article(make_ctx):
    ctx = make_ctx()
    raw = [{"title": "Beta Q2 profit falls", "url": "https://example.org/b", "summary": "Lots of detail " * 40},
           {"title": "Acme Q2 profit rises", "url": "https://example.org/a", "summary": ""}]
    ids, _ = ingest_items(ctx.store, {"id": "s", "scout": "startups"}, raw, DedupIndex(ctx.store, 7))
    assert draft.select_sources(ctx, {"item_ids": ids, "title": "Acme Q2 profit rises"})[0]["url"].endswith("/a")


def test_healthy_auto_paused_sources_recover_once_but_user_pauses_stay(store):
    for name, reason in (("auto", "No picked cards from 111 items in 4 weeks"),
                         ("user", "Paused by you"), ("broken", "No successful fetch for 7 days (HTTP 403)")):
        store.insert("sources", {"id": name, "active": False, "paused_reason": reason})
    sync_seeds(store)
    assert store.get("sources", "auto")["active"]
    assert not store.get("sources", "user")["active"] and not store.get("sources", "broken")["active"]
    store.update("sources", "auto", active=False, paused_reason="Paused by you")
    sync_seeds(store)
    assert not store.get("sources", "auto")["active"]


def test_bluesky_parser_retains_observed_counts_and_skips_bad_uris():
    row = {"uri": "at://did:plc:abc/app.bsky.feed.post/123abc", "author": {"handle": "engineer.example"},
           "record": {"text": "A real post about AI evaluation", "createdAt": timeutil.now_iso()},
           "likeCount": 45, "repostCount": 7, "replyCount": 3}
    items = parse({"kind": "bsky_search"}, json.dumps({"posts": [row, {**row, "uri": "javascript:bad"}]}).encode())
    assert len(items) == 1 and items[0]["signals"]["bsky_likes"] == 45
    assert items[0]["url"] == "https://bsky.app/profile/did:plc:abc/post/123abc"
    feed = parse({"kind": "bsky_feed"}, json.dumps({"feed": [{"post": row}, {"post": row, "reason": {"type": "repost"}}]}).encode())
    assert len(feed) == 1 and feed[0]["signals"]["bsky_replies"] == 3


def test_public_activity_survives_no_ai_and_does_not_claim_linkedin_success(make_ctx):
    ctx = make_ctx()
    ctx.settings.llm.daily_cap = 0
    raw = [{"title": "Engineers discussing an evaluation harness", "url": "https://bsky.app/profile/a/post/b",
            "published_at": timeutil.now_iso(), "signals": {"discovery_platform": "bluesky", "bsky_likes": 30,
                                                            "bsky_replies": 4, "bsky_reposts": 2}}]
    ingest_items(ctx.store, {"id": "s", "scout": "buzz"}, raw, DedupIndex(ctx.store, 7))
    result = pulse.run(ctx)
    assert result["found"] == 1
    row = pulse.recent(ctx)["conversations"][0]
    assert row["platform"] == "bluesky" and row["evidence"] == "observed_activity"
    assert row["metrics"]["likes"] == 30 and row["why"] == ""


def test_search_claim_without_grounding_is_not_accepted(make_ctx):
    class Uncited(FakeProvider):
        def generate(self, req):
            response = super().generate(req)
            response.grounding = []
            return response
    ctx = make_ctx(providers={"gemini": Uncited("gemini")})
    assert pulse.run(ctx)["found"] == 0
    assert not ctx.store.select("items", "source_id = ?", (pulse.SOURCE_ID,))


def test_zero_weight_topic_is_excluded_before_spending_on_triage(make_ctx):
    ctx = make_ctx()
    ctx.settings.strategy["x"]["affairs"].weight = 0
    topic = {"fit": {"x": {"affairs": 0.9}}, "title": "An affairs headline"}
    assert rank.prescore(ctx, topic, "x", rank.Memory([], [], {}, [], {})) is None


def test_parallel_calls_reserve_budget_before_network(store, settings):
    barrier = threading.Barrier(2)
    class Slow(FakeProvider):
        def generate(self, req):
            barrier.wait(timeout=5)
            return super().generate(req)
    settings.llm.max_calls_per_run = 2
    settings.llm.routes["draft"] = ["groq"]
    router = Router(settings, store, providers={"groq": Slow("groq")}, sleep=lambda _: None)
    def call(_):
        try:
            return router.call(LLMRequest(task="draft", system="", prompt="x"))
        except BudgetExhausted:
            return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(call, range(6)))
    assert sum(r is not None for r in results) == 2
    assert router.used_today() == router.usage.attempts == 2


def test_rate_limited_model_is_not_hammered_by_next_draft():
    cycle = ModelCycle("p", ["a", "b"], True)
    calls = []
    def attempt(model):
        calls.append(model)
        if model == "a":
            raise LLMError("TPM", rate_limited=True, status=429, retry_after=60)
        return LLMResponse(text="ok", provider="p", model=model)
    req = LLMRequest(task="draft", system="", prompt="x")
    cycle.run(req, attempt)
    cycle.idx = 0
    cycle.run(req, attempt)
    assert calls == ["a", "b", "b"]


@pytest.mark.parametrize("url,model,enabled", [
    ("http://127.0.0.1:11434/v1", "qwen3:8b", True),
    ("https://ollama.com/v1", "qwen3:8b", False),
    ("http://localhost:11434/v1", "model:cloud", False),
])
def test_ollama_opt_in_cannot_silently_use_cloud(url, model, enabled, monkeypatch):
    provider = OpenAICompatProvider("ollama", ProviderSpec(kind="ollama", model=model, base_url=url))
    assert not provider.available()
    monkeypatch.setenv("PBS_OLLAMA_ENABLED", "1")
    assert provider.available() is enabled


def test_analytics_does_not_merge_different_snapshots_or_retain_rejected_reward(make_ctx):
    ctx = make_ctx()
    ctx.store.insert("posts", {"id": "p", "platform": "linkedin", "posted_at": "2026-09-20T08:00:00Z",
                               "final_text": "An example", "perf": 0.8, "reward": 4})
    for mid, date, imp, eng in (("old", "2026-09-21T08:00:00Z", 100, 10),
                                 ("new", "2026-09-22T08:00:00Z", 400, None)):
        ctx.store.insert("metrics", {"id": mid, "post_id": "p", "platform": "linkedin", "status": "confirmed",
                                     "captured_at": date, "impressions": imp, "engagements": eng})
    row = performance.gather(ctx)["posts"][0]
    assert row["impressions"] == 400 and "engagement_rate" not in row
    ctx.store.update("metrics", "old", status="rejected")
    ctx.store.update("metrics", "new", status="rejected")
    learn.update_rewards(ctx)
    assert ctx.store.get("posts", "p")["perf"] is None
    assert performance.coverage(ctx)["linkedin"]["missing"] == 1


def test_small_sample_and_weighted_rates_are_explicit():
    data = performance.summarise([
        {"platform": "x", "source": "pbs", "weekday": "Tue", "impressions": 10, "engagement": 2, "engagement_rate": 20},
        {"platform": "x", "source": "pbs", "weekday": "Tue", "impressions": 990, "engagement": 8, "engagement_rate": 0.81},
    ])["x"]
    assert data["weighted_engagement_rate"] == 1.0
    assert data["by_weekday"][0]["evidence"] == "insufficient"
    assert data["rate_posts"] == 2
