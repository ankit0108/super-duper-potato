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


def _hindi_source(ctx):
    """The seed Hindi feeds were cut in November 2026; one he adds on the Sources page is still translated."""
    from pbs.scout.sources import sync_seeds

    sync_seeds(ctx.store)
    ctx.store.insert("sources", {"id": "my-bihar-hi", "name": "Google News: बिहार", "kind": "gnews",
                                 "query": "बिहार when:2d", "hl": "hi", "gl": "IN", "ceid": "IN:hi", "lang": "hi",
                                 "scout": "affairs", "tier": "bihar", "active": True, "added_by": "user"})


def test_hindi_items_are_marked_and_translated(make_ctx):
    ctx = make_ctx()
    _hindi_source(ctx)
    run_scouts(ctx)
    build_topics(ctx)
    hi = ctx.store.select("items", "lang = 'hi'")
    assert hi and all(i["title_en"] for i in hi)


def test_same_story_clusters_into_one_topic_with_why_now(make_ctx):
    ctx = make_ctx()
    run_scouts(ctx)
    build_topics(ctx)
    top = ctx.store.select("topics", order="n_sources DESC", limit=1)[0]
    # Generic agent stories no longer bridge into the launch cluster.
    assert len(top["item_ids"]) == 3 and top["n_sources"] == 3
    assert "Covered by 3 outlets" in top["why_now"]["note"]
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


def test_a_seed_whose_address_changes_gets_a_fresh_start(store):
    from pbs.scout.sources import AUTO_PAUSE, sync_seeds

    sync_seeds(store)
    # As an older release left it: a direct feed that GitHub's servers couldn't reach, paused automatically.
    store.update("sources", "venturebeat-ai", kind="rss", url="https://venturebeat.com/category/ai/feed/", query=None,
                 consecutive_failures=9, last_error="HTTP 403", etag='"old"', active=False,
                 paused_reason=f"{AUTO_PAUSE} 7 days (HTTP 403)")
    store.update("sources", "reddit-machinelearning", active=False, paused_reason="Paused by Ankit")
    sync_seeds(store)
    row = store.get("sources", "venturebeat-ai")
    assert row["kind"] == "gnews" and row["query"].startswith("site:venturebeat.com") and not row.get("url")
    assert row["active"] and not row.get("paused_reason") and row["consecutive_failures"] == 0
    assert not row.get("etag") and not row.get("last_error")
    assert not store.get("sources", "reddit-machinelearning")["active"]  # his own pause stays


def test_translation_survives_a_bare_list_reply(make_ctx):
    # Gemini Flash-Lite answered the translation with a bare list on the first live run, which crashed topics.
    from conftest import fake_providers

    def bare(req, data):
        items = data if isinstance(data, list) else data.get("items", [])
        return [{"id": it.get("id"), "title_en": f"(EN) {it.get('title', '')}", "summary_en": ""} for it in items]

    ctx = make_ctx(providers=fake_providers(translate=bare))
    _hindi_source(ctx)
    run_scouts(ctx)
    build_topics(ctx)
    hi = ctx.store.select("items", "lang = 'hi'")
    assert hi and all(i["title_en"].startswith("(EN)") for i in hi)
    assert ctx.store.count("topics") > 0


# ---------------------------------------------------------------------------
# The November 2026 source round, and sources only he can remove
# ---------------------------------------------------------------------------

NEW_IDS = ("openai-developer-blog", "claude-code-changelog", "epoch-ai", "gnews-itnews", "gnews-scroll",
           "startup-daily", "gnews-capital-brief", "pod-acquired", "bsky-hamel", "pivot-to-ai", "gnews-cricket",
           "farnam-street", "meta-ai-blog", "mistral-news")


def test_the_seed_file_loads_with_unique_ids_and_his_choices():
    from pbs.scout.sources import REVIEW_2026_11_DELETE, seed_sources

    seeds = seed_sources()
    ids = [s["id"] for s in seeds]
    assert len(ids) == len(set(ids))
    assert not set(REVIEW_2026_11_DELETE) & set(ids), "what he cut is gone from the seed file"
    assert set(NEW_IDS) <= set(ids)
    assert "gnews-meta-ai" in ids, "kept alongside the primary Meta feed until the 4-week review"
    assert not any("RESOLVE_AT_BUILD" in str(s.get("url")) for s in seeds)
    by_id = {s["id"]: s for s in seeds}
    assert by_id["gnews-itnews"]["gl"] == "AU" and by_id["gnews-scroll"]["tier"] == "india"
    assert by_id["gary-marcus"]["kind"] == "gnews" and by_id["ainews"]["url"] == "https://latent.space/feeds/news.xml"
    reddit = [s for s in seeds if s["id"].startswith("reddit-")]
    assert {s["id"] for s in reddit} == {"reddit-ai-agents", "reddit-llmdevs", "reddit-rpa", "reddit-developersindia",
                                         "reddit-programmerhumor", "reddit-linkedinlunatics", "reddit-localllama",
                                         "reddit-machinelearning"}
    assert all(s["kind"] == "reddit" and s["url"].endswith((".rss?t=day", ".rss?t=week")) for s in reddit)
    assert by_id["reddit-rpa"]["url"].endswith("t=week")


def test_the_review_migration_deletes_once_fixes_in_place_and_lifts_only_system_pauses(store):
    from pbs.scout.sources import REVIEW_2026_11, REVIEW_2026_11_DELETE, sync_seeds

    # The table as it was before this release: the cut sources, a fixed one he edited, paused ones.
    sync_seeds(store)
    store.set_setting(REVIEW_2026_11, False)
    for sid in REVIEW_2026_11_DELETE:
        store.insert("sources", {"id": sid, "name": sid, "kind": "rss", "url": f"https://example.com/{sid}",
                                 "scout": "affairs", "active": True, "added_by": "seed"})
    store.update("sources", "gary-marcus", kind="rss", url="https://garymarcus.substack.com/feed", query=None,
                 extra={"user_edited": True}, consecutive_failures=4, last_error="HTTP 403")
    store.update("sources", "reddit-ai-agents", extra={"min_score": 80})
    store.update("sources", "reddit-machinelearning", active=False, paused_reason="No successful fetch for 7 days (HTTP 429)")
    store.update("sources", "lobsters", active=False, paused_reason="No picked cards from 40 items in 4 weeks")
    store.update("sources", "hn-ask", active=False, paused_reason=None)  # he paused it on the Sources page
    store.update("sources", "techmeme", active=False, paused_reason="Paused by you")
    sync_seeds(store)
    assert not any(store.get("sources", sid) for sid in REVIEW_2026_11_DELETE)
    assert set(REVIEW_2026_11_DELETE) <= set(store.get_setting("deleted_sources", []))
    marcus = store.get("sources", "gary-marcus")
    assert marcus["kind"] == "gnews" and marcus["query"].startswith("site:garymarcus.substack.com")
    assert marcus["consecutive_failures"] == 0 and not marcus.get("last_error")
    assert "min_score" not in (store.get("sources", "reddit-ai-agents").get("extra") or {})
    assert store.get("sources", "reddit-machinelearning")["active"] and store.get("sources", "lobsters")["active"]
    assert not store.get("sources", "hn-ask")["active"] and not store.get("sources", "techmeme")["active"]
    # It runs once, and nothing it deleted comes back.
    store.update("sources", "reddit-machinelearning", active=False, paused_reason="Paused by you")
    sync_seeds(store)
    assert not any(store.get("sources", sid) for sid in REVIEW_2026_11_DELETE)
    assert not store.get("sources", "reddit-machinelearning")["active"]


def test_a_failing_source_is_never_paused_and_is_fetched_every_run(make_ctx, web):
    ctx = make_ctx()
    run_scouts(ctx)
    ctx.store.update("sources", "simon-willison", consecutive_failures=30, last_success_at="2026-01-01T00:00:00Z",
                     last_error="HTTP 500")
    web.world["simonwillison.net/atom"] = (500, "text/plain", "down")
    stats = run_scouts(ctx)
    row = ctx.store.get("sources", "simon-willison")
    assert row["active"] and not row.get("paused_reason") and row["consecutive_failures"] == 31
    assert stats["sources"] == len([s for s in ctx.store.select("sources", "active = 1")
                                    if s.get("kind") not in ("pulse", "websearch")]), "every active feed is fetched"


def _review(ctx, yields, *, failing=(), old=True):
    from pbs import report

    for sid in failing:
        ctx.store.update("sources", sid, consecutive_failures=5, last_success_at="2026-09-01T00:00:00Z",
                         last_error="HTTP 404")
    if old:
        for s in ctx.store.select("sources"):
            ctx.store.update("sources", s["id"], created_at="2026-07-01T00:00:00Z")
    rows = [{"source_id": sid, "items_28d": n, "picked_items_28d": k} for sid, (n, k) in yields.items()]
    return report.source_review(ctx, {"source_yield": rows})


def test_the_weekly_source_review_asks_and_remembers_what_he_keeps(make_ctx):
    from conftest import write_inbox

    from pbs import inbox
    from pbs.scout.sources import sync_seeds

    ctx = make_ctx()
    sync_seeds(ctx.store)
    everyone = {s["id"]: (5, 1) for s in ctx.store.select("sources")}  # healthy: some items, a pick
    pid = _review(ctx, {**everyone, "the-register": (300, 0), "xkcd": (0, 0)}, failing=["lobsters"])
    prop = ctx.store.get("proposals", pid)
    rows = prop["payload"]["review"]
    assert [r["id"] for r in rows] == ["lobsters", "xkcd", "the-register"], "failing first, then empty, then quiet"
    assert rows[0]["why"].startswith("Failing for") and rows[2]["why"] == "300 items in 28 days, none in a card you picked"
    assert _review(ctx, everyone) is None, "one review at a time"
    write_inbox(ctx.data_root, [{"id": "r1", "type": "proposal.decide", "proposal_id": pid, "decision": "approve",
                                 "choices": {"lobsters": "remove", "xkcd": "keep"}}])
    inbox.ingest(ctx)
    assert ctx.store.get("proposals", pid)["status"] == "applied"
    assert ctx.store.get("sources", "lobsters") is None and "lobsters" in ctx.store.get_setting("deleted_sources")
    assert ctx.store.get("sources", "xkcd")["active"] and ctx.store.get("sources", "the-register")["active"]
    # Kept ones aren't asked about again for 12 weeks, unless one starts failing.
    assert _review(ctx, {**everyone, "the-register": (300, 0), "xkcd": (0, 0)}) is None
    again = ctx.store.get("proposals", _review(ctx, {**everyone, "the-register": (300, 0)}, failing=["xkcd"]))
    assert [r["id"] for r in again["payload"]["review"]] == ["xkcd"]


def test_new_sources_and_searches_are_not_reviewed(make_ctx):
    from pbs.scout.sources import sync_seeds

    ctx = make_ctx()
    sync_seeds(ctx.store)
    quiet = {s["id"]: (0, 0) for s in ctx.store.select("sources")}
    assert _review(ctx, quiet, old=False) is None, "a source under four weeks old isn't judged yet"
    rows = ctx.store.get("proposals", _review(ctx, quiet))["payload"]["review"]
    assert len(rows) == ctx.settings.scouting.review_max
    assert not {"social-pulse", "scout-linkedin", "scout-x"} & {r["id"] for r in rows}


def test_a_youtube_feed_gives_each_video_its_description():
    from pathlib import Path

    xml = (Path(__file__).parent / "fixtures" / "youtube_feed.xml").read_bytes()
    items = parse({"id": "yt-karpathy", "kind": "rss", "name": "Andrej Karpathy (YouTube)"}, xml)
    assert len(items) == 1 and items[0]["url"] == "https://www.youtube.com/watch?v=7xTGNNLPyMI"
    assert items[0]["summary"].startswith("This is a general audience deep dive")
