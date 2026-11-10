"""The platform scouts: their searches, their reports and "Draft this" (pbs/agents/scout.py)."""

from __future__ import annotations

import json

import pytest
from conftest import write_inbox

from pbs import draft, inbox
from pbs.agents import scout as scouts
from pbs.deliver import morning_delivery
from pbs.rank import build_candidates, build_memory
from pbs.scout import websearch
from pbs.scout.parsers import parse
from pbs.scout.scouting import run_scouts
from pbs.topics import build_topics

POST = "https://www.linkedin.com/posts/asha-rao_agents-in-production-activity-7300000000000000001-AbCd"
RESULTS = {"results": [
    {"url": POST, "title": "What a year of running agents in production taught us",
     "content": "Three lessons from moving an invoice agent from pilot to production.",
     "published_date": "2026-09-27T08:00:00Z"},
    {"url": "https://www.linkedin.com/in/asha-rao", "title": "Asha Rao", "content": "Profile"},
    {"url": "not a url", "title": "Broken"},
]}


def _search_world(web, body=RESULTS, status=200):
    web.world["api.tavily.com/search"] = (status, "application/json", json.dumps(body))


def test_search_client_counts_use_and_stops_at_the_cap(make_ctx, web, monkeypatch):
    ctx = make_ctx()
    with pytest.raises(websearch.SearchUnavailable):
        websearch.search(ctx, "AI agents")  # no key
    assert websearch.remaining(ctx) == 0
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _search_world(web)
    ctx.settings.websearch.monthly_cap = 1
    rows = websearch.search(ctx, "AI agents", where="linkedin")
    assert [r["url"] for r in rows] == [POST, "https://www.linkedin.com/in/asha-rao"]
    assert websearch.status(ctx) == {"available": True, "used": 1, "cap": 1, "error": None}
    with pytest.raises(websearch.SearchUnavailable):
        websearch.search(ctx, "AI agents")  # the month is used up: no request is made
    assert sum("api.tavily.com" in u for u in web.requests) == 1


def test_a_refused_search_is_kept_for_the_desk_without_counting(make_ctx, web, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _search_world(web, {"detail": "unauthorized"}, status=401)
    ctx = make_ctx()
    with pytest.raises(websearch.SearchUnavailable):
        websearch.search(ctx, "AI agents")
    state = websearch.status(ctx)
    assert state["used"] == 0 and state["error"] == "HTTP 401"


def test_a_scouts_searches_join_the_days_items_as_search_cited(make_ctx, web, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _search_world(web)
    ctx = make_ctx()
    done = scouts.run_probes(ctx, "linkedin")
    assert done and all(p["where"] in ("linkedin", "web") for p in done)
    items = ctx.store.select("items", "source_id = ?", ("scout-linkedin",))
    posts = [it for it in items if it["url"] == POST]
    assert len(posts) == 1, "the post is kept once however many searches return it"
    sig = posts[0]["signals"]
    assert sig["search_cited"] == 1 and sig["discovery_platform"] == "linkedin" and sig["probe"]
    assert not [it for it in items if "/in/" in it["url"]], "a profile page isn't a post"
    assert scouts.run_probes(make_ctx(), "x") is not None
    monkeypatch.delenv("TAVILY_API_KEY")
    assert scouts.run_probes(ctx, "linkedin") == []


def test_reports_are_written_validated_and_linked_to_cards(make_ctx):
    ctx = make_ctx()
    res = morning_delivery(ctx)
    cards = {c["id"]: c for c in ctx.store.select("cards", "delivery_id = ?", (res["id"],))}
    for platform in ("linkedin", "x"):
        report = ctx.store.get("scout_reports", scouts.report_id(platform, ctx.local_date_str()))
        assert report["status"] == "ok" and report["opportunities"]
        assert len(report["opportunities"]) <= ctx.settings.agents.opportunities
        scores = [o["score"] for o in report["opportunities"]]
        assert scores == sorted(scores, reverse=True)
        for o in report["opportunities"]:
            assert ctx.store.get("topics", o["id"]), "every opportunity is a stored story"
            assert set(o["marks"]) == set(scouts.MEASURES[platform])
            # The fake scout gives full traction marks to stories with nothing behind them: code caps it.
            assert o["marks"]["traction"] <= scouts.TRACTION_CAP[o["evidence_level"]]
            if o["evidence_level"] == "hypothesis":
                assert o["marks"]["traction"] <= 1 and not o["evidence"]
            if o["format"] == "x_quote":
                assert o["reply_to"]
            if o["card_id"]:
                card = cards[o["card_id"]]
                assert card["topic_id"] == o["id"] and card["scout"]["why"] == o["why"]
                assert card["score_parts"]["scout"] == o["score"]
        assert any(o["card_id"] for o in report["opportunities"])
    state = json.loads((ctx.data_root / "desk" / "desk.json").read_text()) if (ctx.data_root / "desk" / "desk.json").exists() \
        else None
    from pbs import export
    state = state or export.build(ctx)
    assert {r["platform"] for r in state["scouts"]} == {"linkedin", "x"}
    assert state["scout_search"]["available"] is False


def _candidates(ctx):
    run_scouts(ctx)
    build_topics(ctx)
    return build_candidates(ctx, ctx.store.select("topics"), build_memory(ctx), use_llm=False)


def test_a_scouts_score_moves_a_story_and_a_pass_moves_it_down(make_ctx):
    ctx = make_ctx()
    cands = _candidates(ctx)["linkedin"]
    before = {c.topic["id"]: c.base for c in cands}
    report = scouts.report(ctx, "linkedin", cands)
    assert report["status"] == "ok"
    by_id = {c.topic["id"]: c for c in cands if c.topic.get("id")}
    for o in report["opportunities"]:
        c = by_id[o["id"]]
        assert c.base == pytest.approx(before[o["id"]] * (0.7 + 0.6 * o["score"]), abs=1e-3)
        assert c.scout["rank"] == o["rank"] and c.pillar == o["lane"], "a scout never moves a story to another lane"
    for p in report["passed"]:
        assert by_id[p["id"]].base == pytest.approx(before[p["id"]] * 0.6, abs=1e-3)
    # A fresh set a little later asks nothing new: the morning's report is used again.
    calls = sum(len(p.calls) for p in ctx.llm._providers.values() if hasattr(p, "calls"))
    again = scouts.report(ctx, "linkedin", _candidates(ctx)["linkedin"])
    assert again["created_at"] == report["created_at"]
    assert sum(len(p.calls) for p in ctx.llm._providers.values() if hasattr(p, "calls")) == calls


def test_without_a_model_the_report_is_the_ranking_with_its_evidence(make_ctx):
    ctx = make_ctx()
    cands = _candidates(ctx)["x"]
    before = {c.topic["id"]: c.base for c in cands}
    report = scouts.report(ctx, "x", cands, use_llm=False)
    assert report["status"] == "fallback" and report["error"] and report["model"] is None
    assert report["opportunities"] and all(o["why"] == "" and o["score"] == 0 for o in report["opportunities"])
    assert {c.topic["id"]: c.base for c in cands} == before, "an unscored report reorders nothing"
    ctx.settings.llm.daily_cap = 3
    assert not scouts.affordable(ctx, 15), "the day's drafts come first"


def test_draft_this_makes_a_card_from_an_opportunity(make_ctx):
    ctx = make_ctx()
    morning_delivery(ctx)
    report = ctx.store.get("scout_reports", scouts.report_id("linkedin", ctx.local_date_str()))
    spare = next(o for o in report["opportunities"] if not o["card_id"])
    event = {"type": "scout.draft", "report_id": report["id"], "topic_id": spare["id"]}
    write_inbox(ctx.data_root, [{"id": "s1", **event}])
    assert inbox.ingest(ctx)["applied"] == 1
    card = next(c for c in ctx.store.select("cards", "topic_id = ?", (spare["id"],)) if c["platform"] == "linkedin")
    assert card["work"]["kind"] == "draft" and card["scout"]["why"] == spare["why"] and card["pillar"] == spare["lane"]
    assert card["expires_at"] > card["created_at"]
    linked = ctx.store.get("scout_reports", report["id"])
    assert next(o for o in linked["opportunities"] if o["id"] == spare["id"])["card_id"] == card["id"]
    assert draft.process_work(ctx)["done"] == 1
    assert ctx.store.get("cards", card["id"])["draft"]
    write_inbox(ctx.data_root, [{"id": "s2", **event}, {"id": "s3", **event, "topic_id": "top_nope"}], name="again")
    assert inbox.ingest(ctx)["rejected"] == 2


def test_trending_models_parser_reads_the_hubs_counts():
    body = json.dumps([
        {"id": "acme/small-agent-7b", "likes": 1840, "downloads": 220000, "pipeline_tag": "text-generation",
         "createdAt": "2026-09-25T10:00:00.000Z"},
        {"id": "private/thing", "private": True, "likes": 3},
        {"id": "no-slash", "likes": 9},
        "junk",
    ]).encode()
    rows = parse({"id": "hf-trending-models", "kind": "hf_models"}, body)
    assert [r["url"] for r in rows] == ["https://huggingface.co/acme/small-agent-7b"]
    assert rows[0]["signals"] == {"hf_model_likes": 1840, "hf_model_rank": 1}
    assert "1,840 likes" in rows[0]["summary"] and "text generation" in rows[0]["title"]
    assert parse({"kind": "hf_models"}, b"<html>") == []
