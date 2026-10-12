"""Takes that fit the story (not every post about automation), and Bihar stories from history to now."""

from __future__ import annotations

import datetime as dt
import json
from importlib import resources

from conftest import fake_providers

from pbs import deliver, draft, playbook, timeutil
from pbs.demo.web import MockWeb, build_world, story_world
from pbs.scout.parsers import parse
from pbs.scout.sources import fetch_url, pool_titles, story_pool

OLD_RULE = "Say what changes in practice for people automating real work, not just what was announced."


def _calls(ctx, task):
    return [c for p in ctx.llm._providers.values() for c in p.calls if c.task == task]


# ---------------------------------------------------------------------------
# Takes
# ---------------------------------------------------------------------------


def test_a_playbook_still_carrying_the_old_automation_rule_gets_the_new_wording(make_ctx):
    ctx = make_ctx()
    old = [{"id": "r1", "text": OLD_RULE, "platform": "linkedin", "pillar": None, "source": "seed"},
           {"id": "r2", "text": OLD_RULE, "platform": "x", "pillar": None, "source": "reflection"}]
    playbook.new_version(ctx, old, [{"op": "seed", "count": 2}], source="seed")
    current = playbook.ensure_seed(ctx)
    assert current["version"] == 2
    texts = {r["id"]: r["text"] for r in current["rules"]}
    assert texts["r1"] == playbook.UPDATED_SEED_RULES[OLD_RULE]
    assert texts["r2"] == OLD_RULE  # a rule the reflection wrote is its own
    assert current["changes"] == [{"op": "modify", "rule_id": "r1", "text": texts["r1"]}]
    assert playbook.ensure_seed(ctx)["version"] == 2  # once


def test_new_playbooks_and_prompts_dont_bend_every_take_toward_automation(make_ctx):
    ctx = make_ctx()
    rules = " ".join(r["text"] for r in playbook.ensure_seed(ctx)["rules"])
    assert "automat" not in rules.casefold()
    profile = resources.files("pbs.defaults").joinpath("profile.md").read_text(encoding="utf-8")
    assert "explains research for people automating real work" not in profile
    assert "automat" not in (draft.ANGLE_FALLBACK["research"] + draft.ANGLE_FALLBACK["industry"]).casefold()
    research = ctx.settings.pillar("linkedin", "research").description
    assert "people automating real work" not in research
    deliver.morning_delivery(ctx)
    triage = _calls(ctx, "triage")[0].prompt
    assert "never bend a chip, model, funding, policy or research story toward enterprise or process automation" in triage
    assert "only someone with his background" not in triage
    system = _calls(ctx, "draft")[0].system
    assert "this is background, not the subject of every post" in system


# ---------------------------------------------------------------------------
# Bihar stories
# ---------------------------------------------------------------------------


def test_the_bihar_pool_comes_round_in_turn_and_mixes_eras_each_day():
    pool = story_pool("bihar")
    assert len(pool) > 100 and len(set(pool)) == len(pool)
    seen: set[str] = set()
    day = timeutil.parse("2026-01-01T00:00:00Z")
    batches = []
    for d in range(len(pool) // 3 + 1):
        local = (day + dt.timedelta(days=d)).date().isoformat()
        batches.append(pool_titles("bihar", local, 3))
        seen.update(batches[-1])
    assert seen == set(pool)  # every article within a cycle
    assert batches[0] != batches[1]
    # One article from each theme in turn: the first batch spans ancient Magadha to today.
    assert story_pool("bihar")[:3] == ["Magadha", "Nalanda", "Karnat dynasty"]


def test_the_wikipedia_batch_is_one_request_and_missing_articles_are_skipped():
    source = {"kind": "wikipedia_pool", "query": "bihar", "max_items": 3}
    url = fetch_url(source, "2026-09-28")
    assert url.startswith("https://en.wikipedia.org/w/api.php?") and "exintro=1" in url and "redirects=1" in url
    assert all(t.replace(" ", "+") in url for t in pool_titles("bihar", "2026-09-28", 3))
    assert fetch_url({"kind": "wikipedia_pool", "query": "nowhere"}, "2026-09-28") == ""
    body = story_world()["en.wikipedia.org/w/api.php"][2]
    items = parse(source, body.encode(), "2026-09-28")
    assert [i["title"] for i in items] == ["Vikramashila: Buddhist monastery and centre of learning in Bihar",
                                           "Champaran Satyagraha: 1917 movement in Bihar led by Mahatma Gandhi"]
    assert all(i["published_at"] is None and i["signals"] == {"evergreen": 1} for i in items)
    assert items[0]["url"] == "https://en.wikipedia.org/wiki/Vikramashila"
    assert parse(source, json.dumps({"query": {"pages": {"5": {"title": "X", "missing": ""}}}}).encode()) == []


def test_bihar_stories_arrive_as_story_threads_that_keep_for_days(monkeypatch, tmp_path):
    from pbs.context import Ctx

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    web = MockWeb(world={**build_world(), **story_world()})
    ctx = Ctx.create(tmp_path / "data", transport=web.transport(), llm_providers=fake_providers(),
                     sleep=lambda s: None)
    deliver.morning_delivery(ctx)
    topic = next(t for t in ctx.store.select("topics", "tier = 'bihar'") if t["title"].startswith("Champaran"))
    assert topic["why_now"]["note"] == "A story from history to now, not today's news."
    stories = ctx.store.select("cards", "affairs_type = 'story' AND kind = 'evergreen'")
    assert stories, "a Bihar story is in the morning set"
    card = stories[0]
    assert card["platform"] == "x" and card["pillar"] == "affairs" and card["format"] in ("x_single", "x_thread")
    assert card["expires_at"] > timeutil.iso(timeutil.now() + dt.timedelta(days=3))
    assert card["sources"][0]["published_at"] is None and card["sources"][0]["publisher"] == "Wikipedia"
    prompt = next(c.prompt for c in _calls(ctx, "draft") if card["title"] in c.prompt)
    assert "Affairs post type: a story from history to now, not today's news" in prompt
    # On this day is a story too, and never a reply angle.
    otd = [c for c in ctx.store.select("cards") if c["title"].startswith("On this day")]
    assert all(c["affairs_type"] == "story" and c["format"] != "x_reply" for c in otd)
