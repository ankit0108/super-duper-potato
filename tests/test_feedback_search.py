"""Skip reasons that feed the ranking, edited openings, planned search, drafts from sources, stances."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json

from conftest import fake_providers, write_inbox

from pbs import deliver, draft, feedback, guardrails, inbox, rank, requests, stats, timeutil
from pbs.context import Ctx
from pbs.demo.web import MockWeb, atom, build_world, rss
from pbs.llm.base import LLMError, LLMRequest
from pbs.scout import search
from pbs.scout.sources import seed_sources


def _suggested(ctx, platform="linkedin"):
    return ctx.store.select("cards", "platform = ? AND status = 'suggested'", (platform,), order="rank")[0]


# ---------------------------------------------------------------------------
# Skip reasons
# ---------------------------------------------------------------------------


def test_a_skip_reason_reaches_tomorrows_triage_and_similar_topics_rank_lower(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _suggested(ctx)
    note = "industrial automation, not my focus: I mean automating business processes"
    write_inbox(ctx.data_root, [{"id": "sk1", "type": "card.skip", "card_id": card["id"], "reason": "other",
                                 "note": note}])
    inbox.ingest(ctx)
    rows = feedback.recent_feedback(ctx)
    assert rows[0]["card_id"] == card["id"] and rows[0]["note"] == note
    assert card["id"] in {r["card_id"] for r in stats.compute(ctx)["feedback"]}  # shown on the desk

    topics = ctx.store.select("topics", "origin = 'scout'", limit=3)
    rank.triage(ctx, topics)
    prompt = [c for p in ctx.llm._providers.values() for c in p.calls if c.task == "triage"][-1].prompt
    assert note in prompt and card["title"][:40] in prompt

    memory = rank.build_memory(ctx)
    assert memory.other  # the skipped title, remembered
    topic = ctx.store.get("topics", card["topic_id"])
    with_note = rank.prescore(ctx, topic, "linkedin", memory)
    without = rank.prescore(ctx, topic, "linkedin", dataclasses.replace(memory, other=[]))
    assert with_note and without and with_note[1]["novelty"] < without[1]["novelty"]


def test_not_interesting_also_holds_back_similar_topics(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _suggested(ctx)
    write_inbox(ctx.data_root, [{"id": "sk2", "type": "card.skip", "card_id": card["id"], "reason": "not_interesting"}])
    inbox.ingest(ctx)
    memory = rank.build_memory(ctx)
    topic = ctx.store.get("topics", card["topic_id"])
    dull = rank.prescore(ctx, topic, "linkedin", memory)[1]["novelty"]
    fresh = rank.prescore(ctx, topic, "linkedin", dataclasses.replace(memory, dull=[]))[1]["novelty"]
    assert dull == round(fresh * 0.6, 3)


def test_a_reason_added_after_a_one_tap_skip_updates_the_same_skip(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _suggested(ctx, "x")
    write_inbox(ctx.data_root, [{"id": "t1", "type": "card.skip", "card_id": card["id"], "reason": "wrong_timing"}],
                name="a")
    inbox.ingest(ctx)
    first = ctx.store.get("cards", card["id"])["skip"]
    write_inbox(ctx.data_root, [{"id": "t2", "type": "card.skip", "card_id": card["id"], "reason": "wrong_timing",
                                 "note": "a big launch drowns everything today"}], name="b")
    inbox.ingest(ctx)
    skip = ctx.store.get("cards", card["id"])["skip"]
    assert skip["note"] == "a big launch drowns everything today" and skip["at"] == first["at"]
    types = [i["type"] for i in ctx.store.select("interactions", "card_id = ?", (card["id"],))]
    assert types.count("skipped") == 1 and "skip_reason" in types


# ---------------------------------------------------------------------------
# Openings he edits or writes
# ---------------------------------------------------------------------------


def test_edited_and_own_openings_are_kept_typed_and_learned(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _suggested(ctx)
    hooks = card["hooks"]
    own = "Last week I rebuilt a reconciliation bot from scratch."
    edited = [{"type": hooks[0]["type"], "text": hooks[0]["text"] + " Really."}, *hooks[1:],
              {"type": "custom", "text": own}]
    body = card["draft"]["text"].split("\n\n", 1)[1]
    write_inbox(ctx.data_root, [
        {"id": "h1", "type": "card.edit", "card_id": card["id"], "text": f"{own}\n\n{body}", "hook_index": 3,
         "hooks": edited},
        {"id": "h2", "type": "card.hook", "card_id": card["id"], "hook_index": 3, "text": own},
        {"id": "h3", "type": "card.posted", "card_id": card["id"], "text": f"{own}\n\n{body}", "hook_index": 3},
    ])
    assert inbox.ingest(ctx)["rejected"] == 0
    after = ctx.store.get("cards", card["id"])
    kept = after["working"]["hooks"]
    assert kept[0]["type"] == hooks[0]["type"] and kept[3] == {"type": "story", "text": own}
    swap = ctx.store.select("interactions", "type = 'hook_swapped' AND card_id = ?", (card["id"],))[0]
    assert swap["data"]["hook_type"] == "story" and swap["data"]["edited"] is True
    post = ctx.store.get("posts", after["post_id"])
    assert post["hook_used"] == {"index": 3, "type": "story", "method": "explicit", "similarity": 1.0}


# ---------------------------------------------------------------------------
# Search that understands what he means
# ---------------------------------------------------------------------------


def _search_world() -> dict[str, tuple[int, str, str]]:
    now = timeutil.now()
    world = build_world()
    world["news.google.com/rss/search?q=AI%20automation"] = (200, "application/rss+xml", rss("Google News", [
        {"title": "Banks put AI agents on back-office reconciliation", "url": "https://news.example/banks-agents",
         "publisher": "Finance Weekly", "summary": "Agents now handle exceptions in reconciliation workflows.",
         "at": now - dt.timedelta(days=1)},
        {"title": "Industrial automation: new robot arms for factory lines", "url": "https://news.example/robots",
         "publisher": "Plant Today", "summary": "", "at": now - dt.timedelta(days=2)},
        {"title": "AI automation, a look back at the last decade", "url": "https://news.example/old",
         "publisher": "Archive", "summary": "", "at": now - dt.timedelta(days=400)},
    ]))
    world["hn.algolia.com/api/v1/search?query=AI%20automation"] = (200, "application/json", json.dumps({"hits": [
        {"title": "Show HN: Open-source workflow automation with LLM agents", "url": "https://example.dev/flows",
         "points": 12, "num_comments": 4, "created_at": timeutil.iso(now - dt.timedelta(days=2)),
         "objectID": "42000001"}]}))
    world["export.arxiv.org/api/query?search_query=abs%3A%22AI%20automation%22"] = (
        200, "application/atom+xml", atom("arXiv", [
            {"title": "LLM agents for business process automation: a benchmark",
             "url": "https://arxiv.org/abs/2609.00001", "summary": "We evaluate agents on 40 back-office processes.",
             "at": now - dt.timedelta(days=10)}]))
    return world


def _ctx(tmp_path, world=None, providers=None) -> tuple[Ctx, MockWeb]:
    web = MockWeb(world if world is not None else _search_world())
    ctx = Ctx.create(tmp_path / "data", transport=web.transport(), llm_providers=providers or fake_providers(),
                     sleep=lambda s: None)
    return ctx, web


def test_search_plan_keeps_his_meaning_and_recent_results(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    ctx, web = _ctx(tmp_path)
    res = search.run_search(ctx, "AI automation")
    assert res.plan.source == "model" and "industrial" in res.plan.exclude
    titles = [item["title"] for _, item in res.found]
    assert "Banks put AI agents on back-office reconciliation" in titles
    assert "Show HN: Open-source workflow automation with LLM agents" in titles
    assert "LLM agents for business process automation: a benchmark" in titles
    assert not any("robot arms" in t or "look back" in t for t in titles)  # wrong meaning, too old
    gnews = [u for u in web.requests if "news.google.com/rss/search" in u]
    assert gnews and all("when%3A14d" in u and "-industrial" in u for u in gnews)
    assert res.checked and res.summary()["interpretation"].startswith("AI automation, for teams")


def test_without_a_model_the_plan_comes_from_his_pillar_keywords(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")

    def down(req, data):
        raise LLMError("server error 503", status=503)

    ctx, _ = _ctx(tmp_path, providers=fake_providers(search_plan=down, search_rerank=down))
    plan = search.plan_search(ctx, "AI automation")
    assert plan.source == "fallback" and plan.queries[0] == "AI automation"
    assert any("rpa" in q and "workflow" in q for q in plan.queries[1:])
    assert "firsthand receipts" in plan.interpretation.casefold()
    res = search.run_search(ctx, "AI automation", plan=plan)
    assert res.found and not res.checked


def test_grounding_that_says_no_is_skipped_for_the_rest_of_the_day(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")

    def no_quota(req, data):
        raise LLMError("rate limited: RESOURCE_EXHAUSTED", status=429, rate_limited=True, retryable=True,
                       retry_after=20)

    ctx, _ = _ctx(tmp_path, providers=fake_providers(search=no_quota))
    plan = search.fallback_plan(ctx, "AI automation")
    assert search.grounded_search(ctx, plan) == [] and search.grounded_search(ctx, plan) == []
    calls = [c for c in ctx.llm._providers["gemini"].calls if c.task == "search"]
    assert len(calls) == 1 and ctx.llm.grounding_off_today()
    assert ctx.llm.call(LLMRequest(task="draft", system="s", prompt="<input>{}</input>")).provider  # others unaffected


def test_a_request_records_what_it_understood_and_drafts_stay_on_it(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    ctx, _ = _ctx(tmp_path)
    write_inbox(ctx.data_root, [{"id": "rq1", "type": "request.create", "request_id": "req_1", "query": "AI automation",
                                 "platforms": {"linkedin": 1, "x": 1}}])
    inbox.ingest(ctx)
    assert requests.handle_requests(ctx)["done"] == 1
    row = ctx.store.get("requests", "req_1")
    assert row["status"] == "done" and row["search"]["interpretation"].startswith("AI automation, for teams")
    assert row["search"]["queries"] and row["search"]["kept"] >= 3 and row["search"]["items"] >= 3
    cards = [ctx.store.get("cards", i) for i in row["card_ids"]]
    assert all("Understood as: AI automation, for teams" in c["why_now"] for c in cards)
    assert all(not any("robot" in s["title"] for s in c["sources"]) for c in cards)
    prompt = [c for p in ctx.llm._providers.values() for c in p.calls if c.task == "draft"][-1].prompt
    assert "Understood as" in prompt


def test_seed_sources_are_unique_https_and_include_the_major_labs():
    rows = seed_sources()
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert all(r["url"].startswith("https://") for r in rows if r.get("url"))
    for wanted in ("anthropic-news", "openai-news", "deepmind-blog", "google-research", "huggingface-blog",
                   "gnews-xai", "amazon-science", "uber-engineering", "microsoft-research", "nvidia-blog",
                   "gnews-bpa", "arxiv-business-process"):
        assert wanted in ids


# ---------------------------------------------------------------------------
# Cards with questions: drafted from sources; answering is optional
# ---------------------------------------------------------------------------


def test_a_card_with_nothing_recent_to_draft_from_waits_for_answers(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    ctx, _ = _ctx(tmp_path, world={})
    deliver.weekly_batch(ctx)
    card = ctx.store.select("cards", "kind = 'interview'", order="created_at")[0]
    assert card["status"] == "needs_input" and not card.get("draft") and len(card["questions"]) <= 2
    write_inbox(ctx.data_root, [{"id": "dn1", "type": "card.draft_now", "card_id": card["id"]}])
    inbox.ingest(ctx)
    draft.process_work(ctx)
    card = ctx.store.get("cards", card["id"])
    assert not card.get("draft") and card["work"] is None
    assert any("No recent sources" in n for n in card["flags"]["notes"])


def test_an_unanswered_opinion_card_is_drafted_neutrally(make_ctx):
    ctx = make_ctx()
    now = timeutil.now_iso()
    card = {"id": "crd_op", "kind": "interview", "platform": "x", "mode": "interview", "pillar": "affairs",
            "format": "x_single", "affairs_type": "opinion", "title": "Bihar's special status demand",
            "sources": [{"url": "https://news.example/status", "title": "Centre responds to special status demand",
                         "publisher": "Example News", "published_at": now, "summary": "The finance ministry replied."}],
            "questions": [{"id": "q1", "q": "Where do you stand?", "kind": "stance"}], "flags": {},
            "status": "needs_input", "created_at": now, "revision": 0, "draft_state": "pending"}
    draft.save_card(ctx, card)
    card = draft.draft_from_sources(ctx, card)
    prompt = [c for p in ctx.llm._providers.values() for c in p.calls if c.task == "draft"][-1].prompt
    assert "Affairs post type: future outlook" in prompt and "Use ONLY his recorded stance" not in prompt
    assert "hasn't answered the questions yet" in prompt
    assert card["status"] == "suggested" and card["draft_basis"] == "sources" and card["questions"]


def test_experiences_in_a_draft_he_did_not_answer_are_flagged(settings):
    base = {"platform": "linkedin", "format": "li_text", "mode": "interview", "title": "t", "hooks": [],
            "draft": {"text": "I built a bot that reconciles invoices overnight.", "posts": []}}
    kw = {"settings": settings, "blocklist": [], "evidence": "", "avoid_phrases": [], "bait_phrases": []}
    assert guardrails.check_card({**base, "draft_basis": "sources"}, **kw).flags["first_person"]
    assert guardrails.check_card(base, **kw).flags["first_person"]  # no answers: nothing he said to draw on
    answered = {**base, "draft_basis": "answers", "answers": [{"question_id": "q1", "answer": "I built a bot."}]}
    assert not guardrails.check_card(answered, **kw).flags["first_person"]


# ---------------------------------------------------------------------------
# Stances
# ---------------------------------------------------------------------------


def test_own_words_then_a_position_then_clear(make_ctx):
    from pbs import stances

    ctx = make_ctx()
    stances.ensure_seeded(ctx)
    sid = "bihar-prohibition"
    write_inbox(ctx.data_root, [
        {"id": "st1", "type": "stance.upsert", "stance_id": sid, "chosen_key": None,
         "custom_text": "  Keep the goal, fix enforcement first.  "}], name="a")
    inbox.ingest(ctx)
    row = ctx.store.get("stances", sid)
    assert row["chosen"] == {"position_key": None, "custom_text": "Keep the goal, fix enforcement first."}
    assert row["status"] == "active" and draft.stance_text(row).endswith("fix enforcement first.")
    write_inbox(ctx.data_root, [
        {"id": "st2", "type": "stance.upsert", "stance_id": sid, "chosen_key": "reform", "custom_text": None},
        {"id": "st3", "type": "stance.upsert", "stance_id": "stn_new", "issue": "Four-day week in Indian IT",
         "tier": "india", "custom_text": "Worth piloting where output is measurable."}], name="b")
    inbox.ingest(ctx)
    assert ctx.store.get("stances", sid)["chosen"] == {"position_key": "reform", "custom_text": None}
    new = ctx.store.get("stances", "stn_new")
    assert new["chosen"]["custom_text"] == "Worth piloting where output is measurable." and new["tier"] == "india"
    write_inbox(ctx.data_root, [{"id": "st4", "type": "stance.upsert", "stance_id": sid, "clear_choice": True}],
                name="c")
    inbox.ingest(ctx)
    assert ctx.store.get("stances", sid)["chosen"] is None


def test_work_cards_draft_from_sources_but_personal_life_cards_wait_for_answers(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    ctx, _ = _ctx(tmp_path)
    deliver.weekly_batch(ctx)
    cards = ctx.store.select("cards", "kind = 'interview'")
    work = [c for c in cards if c["pillar"] in ("receipts", "learning")]
    life = [c for c in cards if c["pillar"] == "life"]
    assert work and life
    assert all(c["draft_basis"] == "sources" and c["status"] == "suggested" and c["questions"] for c in work)
    assert all(c["status"] == "needs_input" and not c.get("draft") for c in life)
