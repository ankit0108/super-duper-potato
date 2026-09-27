from __future__ import annotations

from pbs.scout.parsers import parse
from pbs.scout.scouting import run_scouts
from pbs.topics import build_topics


def test_scouts_ingest_dedupe_and_track_health(make_ctx):
    ctx = make_ctx()
    stats = run_scouts(ctx)
    assert stats["failed"] == 1 and stats["new_items"] > 20
    npr = ctx.store.get("sources", "npr-world")
    assert npr["consecutive_failures"] == 1 and npr["last_error"] == "HTTP 500"
    ok = ctx.store.get("sources", "techcrunch-ai")
    assert ok["items_last_run"] == 3 and ok["last_success_at"]
    # Second run: same feeds, nothing new, duplicates counted instead.
    again = run_scouts(ctx)
    assert again["new_items"] == 0 and again["duplicates"] >= stats["new_items"]


def test_google_news_titles_lose_publisher_suffix(make_ctx):
    ctx = make_ctx()
    run_scouts(ctx)
    rows = ctx.store.select("items", "source_id LIKE 'gnews-bihar%'")
    titles = [i["title"] for i in rows]
    assert "Bihar to build 3 new industrial corridors along expressways, says minister" in titles
    assert {i["signals"]["publisher"] for i in rows} >= {"Hindustan Times", "Times of India"}


def test_hindi_items_are_marked_and_translated(make_ctx):
    ctx = make_ctx()
    run_scouts(ctx)
    build_topics(ctx)
    hi = ctx.store.select("items", "lang = 'hi'")
    assert hi and all(i["title_en"] for i in hi)


def test_same_story_clusters_into_one_topic_with_why_now(make_ctx):
    ctx = make_ctx()
    run_scouts(ctx)
    build_topics(ctx)
    top = ctx.store.select("topics", order="n_sources DESC", limit=1)[0]
    assert len(top["item_ids"]) == 5 and top["n_sources"] == 5
    assert "Covered by 5 outlets" in top["why_now"]["note"] and "Hacker News" in top["why_now"]["note"]
    assert "OpenAI" in top["title"]


def test_affairs_reach_linkedin_only_where_they_meet_tech(make_ctx):
    ctx = make_ctx()
    run_scouts(ctx)
    build_topics(ctx)
    for t in ctx.store.select("topics", "scout = 'affairs'"):
        li = t["fit"]["linkedin"]
        if "ai safety" in (t["title"] + t["summary"]).lower():
            continue
        assert max(li.values()) == 0.0


def test_otd_parser_filters_to_relevant_events():
    content = b'{"events": [{"text": "Patna gets its first university.", "year": 1917, "pages": [{"extract": "x", "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Patna_University"}}}]}, {"text": "Something unrelated.", "year": 1800, "pages": []}]}'
    items = parse({"kind": "wikipedia_otd"}, content, "2026-09-28")
    assert len(items) == 1 and items[0]["signals"]["otd_tier"] == "bihar"
