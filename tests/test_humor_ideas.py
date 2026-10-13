"""Funny posts, quotes, excerpts and thoughts; five LinkedIn and ten X cards a morning."""

from __future__ import annotations

import datetime as dt
import json
import random

from conftest import fake_providers

from pbs import bandit, deliver, editing, guardrails, pools, posttypes, settings
from pbs.context import migrate_settings
from pbs.demo.web import wikiquote_answer
from pbs.rank import Candidate, allocate, build_candidates, build_memory
from pbs.scout.parsers import parse
from pbs.scout.scouting import run_scouts
from pbs.scout.sources import fetch_url, quote_pages, todays_quotes
from pbs.style import style_for
from pbs.topics import build_topics


def _calls(ctx, task):
    return [c for p in ctx.llm._providers.values() for c in p.calls if c.task == task]


# ---------------------------------------------------------------------------
# Pools
# ---------------------------------------------------------------------------


def test_each_pool_comes_round_in_turn_and_a_day_mixes_its_themes():
    for pool, n in ((pools.humor(), 4), (pools.thoughts(), 2), (pools.quotes(), 6)):
        assert len(pool) >= 70 and len({e["id"] for e in pool}) == len(pool)
        seen: set[str] = set()
        start = dt.date(2026, 1, 1)
        for d in range(len(pool) // n + 1):
            batch = pools.todays(pool, (start + dt.timedelta(days=d)).isoformat(), n)
            assert len(batch) == n
            seen.update(e["id"] for e in batch)
        assert seen == {e["id"] for e in pool}  # everything within a cycle
    groups = [{e["group"] for e in pools.todays(pools.humor(), f"2026-02-{d:02d}", 4)} for d in range(1, 8)]
    assert all(len(g) >= 2 for g in groups)
    # Entries carded recently are passed over for the next ones.
    first = pools.todays(pools.thoughts(), "2026-03-01", 2)
    later = pools.todays(pools.thoughts(), "2026-03-01", 2, skip={first[0]["id"]})
    assert first[0] not in later and first[1] in later


def test_life_premises_and_ideas_stay_on_x():
    assert {e["group"] for e in pools.humor() if "linkedin" in e["platforms"]} == {"work", "startups"}
    assert all(e["platforms"] == ("x",) for e in pools.humor() if e["group"] == "life")
    assert all(e["platforms"] == ("x",) for e in pools.thoughts())
    assert all(len(q["text"]) <= pools.QUOTE_MAX_CHARS for q in pools.quotes())


# ---------------------------------------------------------------------------
# Quotes, checked on Wikiquote
# ---------------------------------------------------------------------------

PAGE = """'''Alan Curtis Kay''' (born May 17, 1940) is an American [[w:computer scientist|computer scientist]].

== Quotes ==
* The best way to predict the future is to [[invent]] it.<ref>Meeting at PARC, 1971.</ref>
** As quoted in ''The Early History of Smalltalk''.
* People who are '''really''' serious about software should make their own hardware.

=== Disputed ===
* A change in perspective is worth 80 IQ points.

== Quotes about Kay ==
* Alan Kay is the father of the personal computer.

== External links ==
"""


def test_a_quote_counts_only_when_its_words_are_on_the_page_outside_the_doubtful_sections():
    assert pools.found_in("The best way to predict the future is to invent it.", PAGE)
    assert pools.found_in("people who are really serious about software should make their own hardware", PAGE)
    assert not pools.found_in("The best way to predict the future is to create it.", PAGE)  # near miss
    assert not pools.found_in("A change in perspective is worth 80 IQ points.", PAGE)  # disputed
    assert not pools.found_in("Alan Kay is the father of the personal computer.", PAGE)  # about him
    assert pools.lead_sentence(PAGE) == "Alan Curtis Kay (born May 17, 1940) is an American computer scientist."


def test_the_days_quotes_are_one_request_and_only_the_verified_ones_become_items(capsys):
    source = {"id": "wikiquote-quotes", "kind": "wikiquote_pool", "max_items": 6}
    day = "2026-10-14"
    url = fetch_url(source, day)
    assert url.startswith("https://en.wikiquote.org/w/api.php?") and "rvprop=content" in url
    assert quote_pages(day, 6) and len(quote_pages(day, 6)) <= 6
    body = wikiquote_answer(url)  # the demo's Wikiquote: one quote in seven sits under "Misattributed"
    wrong = [q for q in todays_quotes(day, 6) if not int(q["id"], 16) % 7]
    items = parse(source, json.dumps(body).encode(), day)
    assert len(items) == 6 - len(wrong)
    assert f"quotes: {len(items)} verified, {len(wrong)} not found on Wikiquote" in capsys.readouterr().out
    item = items[0]
    assert item["publisher"] == "Wikiquote" and item["published_at"] is None
    assert item["signals"] == {"evergreen": 1, "quote": 1, "x_only": 1, "solo": 1}
    assert item["url"].startswith("https://en.wikiquote.org/wiki/") and item["canonical"].startswith(item["url"])
    assert "word for word on Wikiquote" in item["summary"]


def _scouted(ctx):
    run_scouts(ctx)
    build_topics(ctx)
    return ctx.store.select("topics")


def test_quotes_reach_x_as_quote_posts_never_linkedin(make_ctx):
    ctx = make_ctx()
    topics = [t for t in _scouted(ctx) if (t.get("why_now") or {}).get("signals", {}).get("quote")]
    assert topics and all(len(t["item_ids"]) == 1 for t in topics)  # a quote never joins a news story
    assert all(t["why_now"]["note"] == "A quote, found word for word on Wikiquote; not news." for t in topics)
    cands = build_candidates(ctx, topics, build_memory(ctx), use_llm=False)
    assert all(c.post_type != "quote" for c in cands["linkedin"])
    quotes = [c for c in cands["x"] if c.post_type == "quote"]
    assert len(quotes) == len(topics)
    assert {(c.pillar, c.fmt, c.kind) for c in quotes} == {("ideas", "x_single", "news")}
    card = deliver.fill_card(ctx, deliver.card_from_candidate(ctx, quotes[0], None, 1), quotes[0])
    prompt = next(call.prompt for call in _calls(ctx, "draft") if card["title"] in call.prompt)
    assert "Post type: a quote." in prompt and "Never change, shorten or extend the quote" in prompt
    assert "Write analysis from the material" not in prompt
    assert card["post_type"] == "quote" and card["sources"][0]["publisher"] == "Wikiquote"
    assert card["draft"]["first_comment"].startswith(("Source: https://en.wikiquote.org/wiki/", "https://en.wikiquote"))


# ---------------------------------------------------------------------------
# Counts and allocation
# ---------------------------------------------------------------------------


def test_linkedin_gets_five_cards_with_at_least_one_funny_post_and_x_gets_ten(make_ctx):
    ctx = make_ctx()
    res = deliver.morning_delivery(ctx)
    assert res["counts"] == {"linkedin": 5, "x": 10}
    cards = ctx.store.select("cards", "delivery_id = ?", (res["id"],))
    li = [c for c in cards if c["platform"] == "linkedin"]
    assert any(c["pillar"] == "humor" and c["post_type"] in posttypes.HUMOROUS for c in li)
    funny = next(c for c in li if c["pillar"] == "humor")
    prompts = [c.prompt for c in _calls(ctx, "draft") if "Platform: linkedin" in c.prompt or "LinkedIn" in c.prompt]
    assert any("Post type: a relatable funny observation" in p and "work-safe and about the craft" in p
               for p in prompts)
    assert funny["sources"] == [] and not (funny["draft"] or {}).get("first_comment")


def _cand(i, pillar, base, post_type=None, platform="linkedin"):
    return Candidate(topic={"id": f"t{i}"}, platform=platform, pillar=pillar, fmt="li_text" if platform == "linkedin"
                     else "x_single", mode="external", base=base, parts={"momentum": 0.2}, post_type=post_type)


def test_the_daily_funny_post_is_kept_even_when_it_ranks_last(make_ctx):
    ctx = make_ctx()
    arms = bandit.compute_arms(ctx.store, ctx.settings)
    cands = [_cand(i, ["research", "industry"][i % 2], 1.0 - i / 100) for i in range(10)]
    cands.append(_cand(99, "humor", 0.01, "observation"))
    picked = allocate(ctx, "linkedin", cands, arms, random.Random(3))
    assert len(picked) == 5 and [c.pillar for c in picked].count("humor") == 1
    # A small fresh set is what he asked for: no slot kept.
    fresh = allocate(ctx, "linkedin", cands, arms, random.Random(3), slots=2)
    assert [c.pillar for c in fresh].count("humor") == 0


def test_x_has_no_kept_lanes_the_ranking_decides(make_ctx):
    ctx = make_ctx()
    assert not any(p.min_per_day for p in ctx.settings.pillars("x").values())
    arms = bandit.compute_arms(ctx.store, ctx.settings)
    cands = [_cand(i, ["tech", "startups", "affairs"][i % 3], 1.0 - i / 100, platform="x") for i in range(14)]
    picked = allocate(ctx, "x", cands, arms, random.Random(1))
    assert len(picked) == 10 and not {"humor", "ideas"} & {c.pillar for c in picked}


def test_a_set_mixes_kinds_of_post_in_a_lane(make_ctx):
    ctx = make_ctx()
    arms = bandit.compute_arms(ctx.store, ctx.settings)
    ideas = [_cand(i, "ideas", 0.6, "thought", "x") for i in range(3)] + [_cand(10 + i, "ideas", 0.58, "quote", "x")
                                                                          for i in range(3)]
    picked = [c for c in allocate(ctx, "x", ideas, arms, random.Random(5), slots=2)]
    assert {c.post_type for c in picked} == {"thought", "quote"}


def test_saved_slot_counts_move_to_the_new_defaults_once_and_only_if_untouched(make_ctx):
    ctx = make_ctx()
    ctx.store.set_setting("settings_migrations", [])
    ctx.store.set_setting("overrides", {"platforms": {"linkedin": {"slots": 3, "min_slots": 2},
                                                      "x": {"slots": 8, "min_slots": 4}},
                                        "llm": {"daily_cap": 60}})
    migrate_settings(ctx.store)
    saved = ctx.store.get_setting("overrides")
    assert saved["platforms"]["linkedin"] == {"slots": 5, "min_slots": 3}
    assert saved["platforms"]["x"] == {"slots": 8, "min_slots": 6}  # 8 was his choice
    assert saved["llm"]["daily_cap"] == 100
    ctx.store.set_setting("overrides", {"platforms": {"linkedin": {"slots": 3}}})  # set again after the change
    migrate_settings(ctx.store)
    assert ctx.store.get_setting("overrides")["platforms"]["linkedin"]["slots"] == 3
    s, warnings = settings.load({"platforms": {"x": {"slots": 4}}})
    assert not warnings and s.platforms.x.min_slots == 4


# ---------------------------------------------------------------------------
# Humour rules, post types and the quote check
# ---------------------------------------------------------------------------


def test_a_sensitive_topic_is_never_made_funny(make_ctx):
    def all_funny(req, data):
        topics = data.get("topics", []) if isinstance(data, dict) else data
        return {"topics": [{"id": t["id"], "summary_en": t.get("title"), "sensitive": "Stampede" in t.get("title", ""),
                            "linkedin": {"pillar": "humor", "angle_potential": 5, "angle": "a joke",
                                         "post_type": "funny_take"},
                            "x": {"lane": "humor", "angle_potential": 5, "angle": "a joke", "format": "x_single",
                                  "post_type": "funny_take"}} for t in topics]}

    ctx = make_ctx(providers=fake_providers(triage=all_funny))
    cands = build_candidates(ctx, _scouted(ctx), build_memory(ctx))
    stampede = [c for c in cands["x"] if "Stampede" in (c.topic.get("title") or "")]
    assert stampede and all(c.pillar == "affairs" and c.post_type is None for c in stampede)
    assert not [c for c in cands["linkedin"] if "Stampede" in (c.topic.get("title") or "")]
    assert any(c.post_type == "funny_take" and c.pillar == "humor" for c in cands["x"])
    triage = _calls(ctx, "triage")[0].prompt
    assert "A sensitive topic never goes to a humour lane" in triage
    assert "Never joke about religion, caste, gender" in _calls(ctx, "triage")[0].system


def test_from_news_a_quote_is_an_excerpt_and_unknown_types_fall_back():
    ideas = {"quote": "Quote", "excerpt": "Excerpt", "thought": "Thought"}
    assert posttypes.for_news(ideas, "quote") == "excerpt"
    assert posttypes.for_news(ideas, "nonsense") == "thought"
    assert posttypes.for_news({"funny_take": "Funny", "observation": "Relatable"}, "observation") == "funny_take"
    assert posttypes.for_news({}, "thought") is None


def test_a_changed_quote_is_flagged_and_the_editor_pass_leaves_quotes_alone(make_ctx):
    ctx = make_ctx()
    evidence = "John Gall: “A complex system that works is invariably found to have evolved from a simple system that worked.”"
    good = "“A complex system that works is invariably found to have evolved from a simple system that worked.” — John Gall"
    assert guardrails.quote_check(good, evidence, "quote") == []
    bad = good.replace("invariably", "always")
    assert guardrails.quote_check(bad, evidence, "quote") == [bad.split("”")[0].lstrip("“")]
    assert guardrails.quote_check("Complex systems grow from simple ones.", evidence, "quote") == [
        "the quote isn't in quotation marks"]
    assert guardrails.quote_check(bad, evidence, "thought") == []
    card = {"platform": "x", "format": "x_single", "post_type": "quote", "mode": "external"}
    norm = {"draft": {"text": good + "\n\nIt's not about speed, it's about trust.", "posts": []}}
    out = editing.polish(ctx, card, norm, style_for(ctx, "x", "ideas", "x_single"), evidence=evidence, personal=False)
    assert out["edit"] is None and not _calls(ctx, "edit")
    # The quote's own words never count as an AI tell; the writer's still do.
    assert guardrails.tell_kinds("“It's not about speed, it's about trust, said the old manual.”") == []


def test_triage_goes_in_batches_small_enough_for_every_provider(make_ctx):
    ctx = make_ctx()
    topics = _scouted(ctx)
    ctx.settings.scouting.shortlist_per_platform = 40
    many = topics * 3  # more topics than one batch takes
    for i, t in enumerate(many):
        many[i] = {**t, "id": f"{t['id']}_{i}"}
    build_candidates(ctx, many, build_memory(ctx))
    calls = _calls(ctx, "triage")
    sizes = [len(json.loads(c.prompt.split("<input>")[1].split("</input>")[0])) for c in calls]
    assert len(calls) >= 2 and max(sizes) <= 18 and sum(sizes) > 18
