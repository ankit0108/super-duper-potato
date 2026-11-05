"""Beyond news and papers: what people are talking about (the buzz scout), what's trending, and what's working on
LinkedIn and X (the social pulse)."""

from __future__ import annotations

import datetime as dt
import json

from pbs import deliver, export, pulse, timeutil
from pbs.rank import Memory, build_memory, prescore, shortlist, trend_for
from pbs.scout.parsers import parse
from pbs.scout.scouting import save_terms, trending_terms
from pbs.topics import why_now

NOW = "2026-09-27T19:45:00Z"


def _reddit(*posts):
    return json.dumps({"data": {"children": [{"data": p} for p in posts]}}).encode()


def _post(**kw):
    base = {"title": "A post", "score": 2000, "num_comments": 300, "permalink": "/r/technology/comments/abc/a_post/",
            "url": "https://example.com/story", "subreddit_name_prefixed": "r/technology", "created_utc": 1790000000}
    return {**base, **kw}


def test_reddit_keeps_what_people_talk_about_with_its_score_comments_and_thread():
    source = {"id": "r", "kind": "reddit_json", "name": "r/technology", "extra": {"min_score": 1000}}
    items = parse(source, _reddit(
        _post(title="Company replaces its support team with a chatbot, then hires them back", score=5400,
              num_comments=900),
        _post(title="Ask: what's the weirdest AI bug you shipped?", is_self=True, selftext="Mine renamed every user.",
              url="https://www.reddit.com/r/technology/comments/abc/"),
        _post(title="lol", post_hint="image", url="https://i.redd.it/x.png"),
        _post(title="When the AI agent says it updated the record but it did not", post_hint="image",
              url="https://i.redd.it/y.png"),
        _post(title="Not safe", over_18=True),
        _post(title="Too small to matter", score=50),
    ))
    assert [it["title"][:16] for it in items] == ["Company replaces", "Ask: what's the ", "When the AI agen"]
    story, ask, picture = items
    assert story["url"] == "https://example.com/story" and story["publisher"] == "example.com"
    assert story["signals"] == {"reddit_score": 5400, "reddit_comments": 900,
                                "discussion_url": "https://www.reddit.com/r/technology/comments/abc/a_post/"}
    assert ask["url"].startswith("https://www.reddit.com/") and ask["summary"] == "Mine renamed every user."
    # A picture we can't see: kept only with a telling title, and the drafter is told it's a picture.
    assert picture["summary"].startswith("A picture post on r/technology")


def test_mastodon_links_and_google_trends_arrive_as_stories_with_how_much_people_share_and_search():
    masto = parse({"kind": "mastodon_links"}, json.dumps([
        {"url": "https://example.org/ai-fridge", "title": "The fridge that argues back", "description": "<p>An AI fridge.</p>",
         "provider_name": "Example", "history": [{"accounts": "60"}, {"accounts": "40"}, {"accounts": "900"}]},
        {"title": "No link"},
    ]).encode())
    assert masto == [{"url": "https://example.org/ai-fridge", "title": "The fridge that argues back",
                      "summary": "An AI fridge.", "published_at": None, "lang": "en", "publisher": "Example",
                      "signals": {"mastodon_accounts": 100}}]
    rss = b"""<rss><channel><item><title>chatgpt outage</title><ht:approx_traffic>200,000+</ht:approx_traffic>
      <pubDate>Sun, 27 Sep 2026 18:00:00 +0000</pubDate>
      <ht:news_item><ht:news_item_title><![CDATA[ChatGPT down for millions &amp; counting]]></ht:news_item_title>
      <ht:news_item_url>https://news.example.com/outage</ht:news_item_url>
      <ht:news_item_source>Example News</ht:news_item_source></ht:news_item></item>
      <item><title>no story</title></item></channel></rss>"""
    (trend,) = parse({"kind": "gtrends", "extra": {"geo": "India"}}, rss)
    assert trend["title"] == "ChatGPT down for millions & counting" and trend["url"] == "https://news.example.com/outage"
    assert trend["signals"] == {"search_traffic": 200000, "trend_term": "chatgpt outage"}
    assert "Trending on Google Search in India" in trend["summary"] and trend["publisher"] == "Example News"


def test_trending_words_on_x_and_bluesky_lift_the_stories_that_mention_them(make_ctx):
    ctx = make_ctx()
    page = b"""<div><ol class="trend-card__list"><li><a href="https://twitter.com/search?q=x" class="trend-link">#OpenAIDevDay</a></li>
      <li><a class="trend-link">Monday</a></li><li><a class="trend-link">#AI</a></li></ol>
      <ol class="trend-card__list"><li><a class="trend-link">Last hour only</a></li></ol></div>"""
    x_terms = parse({"kind": "trends24"}, page)
    assert [t["term"] for t in x_terms] == ["#OpenAIDevDay", "Monday", "#AI"]
    bsky = parse({"kind": "bsky_trends"}, json.dumps({"topics": [{"topic": "agents", "displayName": "AI agents"}]}).encode())
    save_terms(ctx.store, {"extra": {"region": "India"}}, x_terms)
    save_terms(ctx.store, {}, bsky)
    assert len(trending_terms(ctx.store)) == 4
    memory = build_memory(ctx)
    # "Monday" and "#AI" are too generic to match; the rest match as phrases, with or without spaces.
    assert [t for _, t, _ in memory.trending] == ["#OpenAIDevDay", "AI agents"]
    topic = {"title": "What OpenAI Dev Day means for builders", "summary": "", "why_now": {"signals": {}},
             "fit": {"x": {"tech": 0.8}}, "newest_published_at": NOW, "scout": "tech"}
    assert trend_for(topic, memory) == {"on": "x", "term": "#OpenAIDevDay", "why": None}
    _, parts, _ = prescore(ctx, topic, "x", memory)
    assert parts["momentum"] >= 0.75
    # A day and a half later they're gone.
    timeutil.freeze("2026-09-29T09:00:00Z")
    assert trending_terms(ctx.store) == []


def test_discussion_lifts_a_story_and_says_so_in_its_why_now(make_ctx):
    ctx = make_ctx()
    item = {"published_at": NOW, "fetched_at": NOW, "lang": "en",
            "signals": {"reddit_score": 5400, "reddit_comments": 900, "discussion_url": "https://www.reddit.com/r/t/1"}}
    why = why_now([item], ["example.com"])
    assert "5,400 upvotes and 900 comments on Reddit" in why["note"]
    assert why["signals"]["discussion_url"] == "https://www.reddit.com/r/t/1"
    quiet = {"title": "A story", "summary": "", "fit": {"x": {"tech": 0.8}}, "newest_published_at": NOW,
             "scout": "buzz", "why_now": {"signals": {}}}
    loud = {**quiet, "why_now": why}
    memory = Memory([], [], {}, [], {})
    assert prescore(ctx, loud, "x", memory)[1]["momentum"] == 1.0
    assert prescore(ctx, quiet, "x", memory)[1]["momentum"] == 0.0


def test_what_people_talk_about_keeps_seats_on_the_shortlist(make_ctx):
    ctx = make_ctx()
    ctx.settings.scouting.shortlist_per_platform = 3
    ctx.settings.scouting.shortlist_seats = {"buzz": 2}
    scored = [({"id": f"n{i}", "scout": "tech"}, i) for i in range(6)] + [({"id": f"b{i}", "scout": "buzz"}, 9)
                                                                       for i in range(3)]
    assert [t["id"] for t, _ in shortlist(ctx, scored)] == ["n0", "n1", "n2", "b0", "b1"]


def test_the_social_pulse_finds_whats_working_once_a_day(make_ctx, capsys):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    calls = [c for p in ctx.llm._providers.values() for c in p.calls if c.task == "pulse"]
    assert len(calls) == 1 and calls[0].grounding and not calls[0].json_mode
    assert "site:linkedin.com/posts" in calls[0].prompt and "Tech humour" in calls[0].prompt
    items = ctx.store.select("items", "source_id = ?", (pulse.SOURCE_ID,))
    assert {i["signals"]["discovery_platform"] for i in items} == {"linkedin", "x"} and len(items) == 2
    agents = next(i for i in items if i["title"].startswith("AI agents that report"))
    assert agents["url"].startswith("https://www.linkedin.com/posts/")  # a post link from the search
    assert "unverified hypothesis" in agents["summary"]
    assert not any(i["title"].startswith("Founders posting") for i in items)
    assert not any(i["signals"].get("trending_on") for i in items)  # a citation is not measured popularity
    desk = export.build(ctx)
    assert {c["topic"] for c in desk["pulse"]["conversations"]} >= {
        "AI agents that report work they never did", "The model that refused to write a regex"}
    source = ctx.store.get("sources", pulse.SOURCE_ID)
    assert source["last_success_at"] and source["items_last_run"] == 2
    # Once a day: a fresh set later doesn't search again. The public log carries counts only.
    assert not pulse.due(ctx)
    out = capsys.readouterr().out
    assert "evidence-backed observations" in out and "Founders" not in out


def test_the_pulse_waits_when_paused_off_or_out_of_search_quota(make_ctx):
    ctx = make_ctx()
    from pbs.scout.sources import sync_seeds

    sync_seeds(ctx.store)
    assert pulse.due(ctx)
    ctx.store.update("sources", pulse.SOURCE_ID, active=False)
    assert not pulse.due(ctx)
    ctx.store.update("sources", pulse.SOURCE_ID, active=True)
    ctx.settings.pulse.enabled = False
    assert not pulse.due(ctx)
    ctx.settings.pulse.enabled = True
    ctx.llm.grounding_off_today = lambda: True
    assert pulse.due(ctx)  # public-feed observations do not require an AI search


def test_history_keeps_a_week(make_ctx):
    ctx = make_ctx()
    old = (timeutil.now() - dt.timedelta(days=12)).date().isoformat()
    ctx.store.set_setting(pulse.HISTORY_KEY, [{"date": old, "platform": "x", "topic": "Old news"}])
    pulse.run(ctx)
    topics = [c["topic"] for c in pulse.recent(ctx)["conversations"]]
    assert "Old news" not in topics and len(topics) == 2


def _pulse_ctx(make_ctx, **pulse_handler):
    from conftest import fake_providers as _fp

    from pbs.llm.base import LLMError
    from pbs.llm.fake import FakeProvider

    refused = LLMError("You exceeded your current quota", status=429, code="RESOURCE_EXHAUSTED", quota=True,
                       retryable=False)
    providers = {**_fp(), "gemini": FakeProvider("gemini", fail_with=refused)}
    if pulse_handler:
        providers["groq_search"] = FakeProvider("groq_search", handlers=pulse_handler, model="groq/compound")
    return make_ctx(providers=providers), providers


def test_retired_compound_search_is_not_called_when_gemini_is_unavailable(make_ctx):
    from pbs.llm import fake

    ctx, providers = _pulse_ctx(make_ctx, pulse=fake._pulse)
    res = pulse.run(ctx)
    assert res["found"] == 0
    assert not providers["groq_search"].calls
    assert ctx.llm.grounding_off_today("gemini")
    assert ctx.llm.search_engines() == [] and ctx.llm.grounding_off_today()
    status = ctx.store.get_setting(pulse.STATUS_KEY)
    assert not status["ok"] and status["error"] == "no_search"
    info = pulse.recent(ctx)
    assert not info["conversations"] and info["engines"] == []


def test_with_no_search_at_all_the_desk_is_told_why(make_ctx):
    ctx, _ = _pulse_ctx(make_ctx)
    ctx.llm._providers.pop("groq_search")  # no GROQ_API_KEY
    pulse.run(ctx)
    assert not pulse.due(ctx)  # already tried today
    ctx.store.set_setting(pulse.LAST_KEY, None)
    assert pulse.due(ctx) and ctx.store.get_setting(pulse.STATUS_KEY)["error"] == "no_search"
    assert pulse.recent(ctx)["engines"] == []


def test_only_links_from_the_pages_the_search_read_are_kept(make_ctx):
    from pbs.llm.base import LLMResponse
    from pbs.llm.fake import FakeProvider

    class Searching(FakeProvider):
        def generate(self, req):
            resp = super().generate(req)
            return LLMResponse(**{**resp.__dict__, "grounding": [
                {"url": "https://www.linkedin.com/posts/someone_ai-agents-activity-7300000000000000001", "title": "t"}]})

    ctx, providers = _pulse_ctx(make_ctx)
    from pbs.llm import fake

    providers["gemini"] = Searching("gemini", handlers={"pulse": fake._pulse})
    ctx = make_ctx(providers=providers)
    pulse.run(ctx)
    urls = {h["topic"]: h["url"] for h in ctx.store.get_setting(pulse.HISTORY_KEY)}
    assert urls["AI agents that report work they never did"].startswith("https://www.linkedin.com/posts/someone_")
    assert "The model that refused to write a regex" not in urls  # unread links cannot become evidence


def test_the_feeds_automatic_pause_never_stops_the_pulse_and_one_is_undone(make_ctx):
    from pbs.scout import scouting

    ctx = make_ctx()
    from pbs.scout.sources import sync_seeds

    sync_seeds(ctx.store)
    ctx.store.update("sources", pulse.SOURCE_ID, active=False, consecutive_failures=6,
                     paused_reason=f"{scouting.AUTO_PAUSE} 7 days (AllProvidersFailed)")
    assert pulse.due(ctx)
    source = ctx.store.get("sources", pulse.SOURCE_ID)
    assert source["active"] and source["paused_reason"] is None
    ctx.store.update("sources", pulse.SOURCE_ID, consecutive_failures=9, last_success_at="2026-01-01T00:00:00Z")
    scouting._auto_pause(ctx)
    assert ctx.store.get("sources", pulse.SOURCE_ID)["active"]
    ctx.store.update("sources", pulse.SOURCE_ID, active=False, paused_reason="Paused by you")
    assert not pulse.due(ctx)  # his own pause stays


def test_search_now_from_the_desk_runs_the_pulse(make_ctx):
    from conftest import fake_providers as _fp
    from conftest import write_inbox

    from pbs import tick

    ctx = make_ctx()
    ctx.store.set_setting(pulse.LAST_KEY, ctx.local_date_str())  # today's already ran
    ctx.store.save()
    write_inbox(ctx.data_root, [{"id": "p1", "type": "run.request", "tasks": ["pulse"]}])
    tick.run(ctx.data_root, llm_providers=_fp(), send_notifications=False, morning=lambda c: None)
    from pbs.store import Store

    status = Store.open(ctx.data_root).get_setting(pulse.STATUS_KEY)
    assert status and status["ok"] and status["found"] == 2
