from __future__ import annotations

import json

from conftest import fake_providers, write_inbox

from pbs import deliver, draft, inbox, learn, playbook, reflect, timeutil
from pbs.deliver import morning_delivery


def _delivered(make_ctx):
    ctx = make_ctx()
    morning_delivery(ctx)
    return ctx


def _interview_card(ctx, platform="linkedin"):
    """A card that asks for his experience: the Saturday batch always makes some."""
    deliver.weekly_batch(ctx)
    return ctx.store.select("cards", "kind = 'interview' AND platform = ?", (platform,), order="created_at")[0]


def _card(ctx, platform="linkedin", status="suggested", fmt=None):
    where = "platform = ? AND status = ?"
    params = [platform, status]
    if fmt:
        where += " AND format = ?"
        params.append(fmt)
    return ctx.store.select("cards", where, params, order="rank")[0]


def test_posting_records_edit_ratio_hook_and_features(make_ctx, tmp_path):
    ctx = _delivered(make_ctx)
    card = _card(ctx)
    hooks = card["hooks"]
    final = hooks[0]["text"] + "\n\n" + card["draft"]["text"].split("\n\n", 1)[1][:200]
    write_inbox(ctx.data_root, [
        {"id": "e1", "type": "card.status", "card_id": card["id"], "status": "editing"},
        {"id": "e2", "type": "card.posted", "card_id": card["id"], "text": final,
         "post_url": "https://www.linkedin.com/posts/x", "editing_seconds": 420},
    ])
    stats = inbox.ingest(ctx)
    assert stats["applied"] == 2 and stats["rejected"] == 0
    card = ctx.store.get("cards", card["id"])
    post = ctx.store.get("posts", card["post_id"])
    assert card["status"] == "posted"
    assert 0 < post["edit_ratio"] < 1
    assert post["hook_used"]["index"] == 0 and post["hook_used"]["type"] == hooks[0]["type"]
    assert post["features"]["pillar"] == card["pillar"] and post["features"]["weekday"]
    assert post["editing_seconds"] == 420 and post["time_to_post_minutes"] is not None
    types = [i["type"] for i in ctx.store.select("interactions", "card_id = ?", (card["id"],))]
    assert "picked" in types and "posted" in types
    assert list((ctx.data_root / "inbox").glob("*.json"))  # kept until the store is saved
    ctx.store.save()
    assert inbox.cleanup(ctx) == 1
    assert not list((ctx.data_root / "inbox").glob("*.json"))
    assert inbox.ingest(ctx)["files"] == 0


def test_events_apply_once(make_ctx):
    ctx = _delivered(make_ctx)
    card = _card(ctx, "x")
    ev = {"id": "dup-1", "type": "card.skip", "card_id": card["id"], "reason": "off_brand"}
    write_inbox(ctx.data_root, [ev], name="a")
    write_inbox(ctx.data_root, [ev], name="b")
    stats = inbox.ingest(ctx)
    assert stats["applied"] == 1 and stats["skipped"] == 1


def test_bad_events_are_rejected_with_reasons_not_fatal(make_ctx):
    ctx = _delivered(make_ctx)
    card = _card(ctx, "x")
    write_inbox(ctx.data_root, [
        {"id": "bad1", "type": "card.skip", "card_id": card["id"], "reason": "bogus"},
        {"id": "bad2", "type": "card.skip", "card_id": "nope", "reason": "off_brand"},
        {"id": "bad3", "type": "settings.update", "patch": {"platforms": {"x": {"slots": 99}}}},
        {"id": "ok1", "type": "card.skip", "card_id": card["id"], "reason": "wrong_timing", "note": "later"},
    ])
    (ctx.data_root / "inbox" / "garbage.json").write_text("{not json")
    stats = inbox.ingest(ctx)
    assert stats["applied"] == 1 and stats["rejected"] == 4
    errors = {r["id"]: r["error"] for r in ctx.store.select("processed_events", "status = 'rejected'")}
    assert "unknown card" in errors["bad2"] and "less than or equal" in errors["bad3"]
    assert (ctx.data_root / "inbox" / "rejected" / "garbage.json").exists()
    assert ctx.store.get("cards", card["id"])["skip"]["reason"] == "wrong_timing"


def test_answers_trigger_a_draft_from_answers_only(make_ctx):
    ctx = make_ctx()
    card = _interview_card(ctx)
    # Drafted right away from recent sources; the questions are optional.
    assert card["questions"] and card["status"] == "suggested" and card["draft_basis"] == "sources"
    assert card["sources"]
    q = card["questions"][0]["id"]
    write_inbox(ctx.data_root, [{"id": "a1", "type": "card.answers", "card_id": card["id"],
                                 "answers": [{"question_id": q, "answer": "We learned exception handling matters."}]}])
    inbox.ingest(ctx)
    assert "work" in ctx.hints
    draft.process_work(ctx)
    card = ctx.store.get("cards", card["id"])
    assert card["status"] == "suggested" and card["draft"]["text"] and card["draft_basis"] == "answers"
    assert "exception handling" in card["draft"]["text"]
    personal = [c for p in ctx.llm._providers.values() for c in p.calls if c.task == "draft_personal"]
    assert personal and personal[-1].personal
    assert '"sources"' in personal[-1].prompt and card["sources"][0]["url"] in personal[-1].prompt  # both used


def test_rewrite_uses_working_text_and_logs_feedback(make_ctx):
    ctx = _delivered(make_ctx)
    card = _card(ctx, "x", fmt="x_single") if ctx.store.count("cards", "format = 'x_single'") else _card(ctx, "x")
    write_inbox(ctx.data_root, [
        {"id": "w1", "type": "card.edit", "card_id": card["id"], "text": "My edited version."},
        {"id": "w2", "type": "card.rewrite", "card_id": card["id"], "note": "shorter", "chips": ["shorter"]},
    ])
    inbox.ingest(ctx)
    draft.process_work(ctx)
    card2 = ctx.store.get("cards", card["id"])
    assert card2["rewrite_count"] == 1 and card2["work"] is None and card2["working"] is None
    last = [c for p in ctx.llm._providers.values() for c in p.calls][-1]
    assert "My edited version." in last.prompt and "shorter" in last.prompt
    assert ctx.store.select("interactions", "type = 'rewrite_requested'")


def test_adapt_to_other_platform_creates_a_card(make_ctx):
    ctx = _delivered(make_ctx)
    card = _card(ctx, "linkedin")
    write_inbox(ctx.data_root, [{"id": "ad1", "type": "card.rewrite", "card_id": card["id"], "note": "",
                                 "target_platform": "x", "target_format": "x_thread"}])
    inbox.ingest(ctx)
    draft.process_work(ctx)
    adapted = ctx.store.select("cards", "kind = 'adapt'")
    assert len(adapted) == 1 and adapted[0]["platform"] == "x" and adapted[0]["format"] == "x_thread"
    assert adapted[0]["draft"]["posts"]


def test_requests_become_drafts(make_ctx):
    from pbs import requests

    ctx = _delivered(make_ctx)
    write_inbox(ctx.data_root, [{"id": "r1", "type": "request.create", "request_id": "req_1",
                                 "query": "enterprise agent platforms", "platforms": {"linkedin": 2, "x": 3}}])
    inbox.ingest(ctx)
    stats = requests.handle_requests(ctx)
    req = ctx.store.get("requests", "req_1")
    assert stats["done"] == 1 and req["status"] == "done" and len(req["card_ids"]) == 5
    cards = [ctx.store.get("cards", i) for i in req["card_ids"]]
    assert all(c["kind"] == "request" and c["draft"] for c in cards)
    assert {c["format"] for c in cards if c["platform"] == "x"} == {"x_single", "x_thread", "x_reply"}


def test_settings_profile_stance_source_events(make_ctx):
    from pbs import stances

    ctx = _delivered(make_ctx)
    stances.ensure_seeded(ctx)
    write_inbox(ctx.data_root, [
        {"id": "s1", "type": "settings.update", "patch": {"platforms": {"x": {"slots": 5}}}},
        {"id": "s2", "type": "profile.update", "text": "- Name: Ankit\n- Builds automation."},
        {"id": "s3", "type": "stance.upsert", "stance_id": "bihar-prohibition", "chosen_key": "reform"},
        {"id": "s4", "type": "source.upsert", "source_id": "my-feed", "name": "My feed", "kind": "rss",
         "url": "https://example.com/feed.xml", "scout": "tech"},
        {"id": "s5", "type": "source.upsert", "source_id": "bad-feed", "name": "Bad", "kind": "rss",
         "url": "ftp://x", "scout": "tech"},
        {"id": "s6", "type": "source.delete", "source_id": "npr-world"},
        {"id": "s7", "type": "account.stats", "date": "2026-09-27", "platform": "x", "followers": 12},
    ])
    stats = inbox.ingest(ctx)
    assert stats["applied"] == 6 and stats["rejected"] == 1
    assert ctx.settings.slots("x") == 5
    assert "Builds automation" in ctx.settings.profile
    stance = ctx.store.get("stances", "bihar-prohibition")
    assert stance["chosen"]["position_key"] == "reform" and stance["status"] == "active"
    assert ctx.store.get("sources", "my-feed")["added_by"] == "user"
    assert ctx.store.get("sources", "npr-world") is None
    assert "npr-world" in ctx.store.get_setting("deleted_sources")


def test_manual_metrics_produce_relative_rewards(make_ctx):
    ctx = _delivered(make_ctx)
    posts = []
    for i, card in enumerate(ctx.store.select("cards", "platform = 'x' AND status = 'suggested'")[:3]):
        post = learn.record_post(ctx, card, text=f"post {i}", posts=None, post_url=None,
                                 posted_at=timeutil.now_iso(), editing_seconds=60, hook_index=None)
        posts.append(post)
    for i, post in enumerate(posts):
        write_inbox(ctx.data_root, [{"id": f"m{i}", "type": "post.metrics", "post_id": post["id"],
                                     "values": {"impressions": 100 * (i + 1), "comments": i, "reactions": 5 * i}}],
                    name=f"m{i}")
    inbox.ingest(ctx)
    assert learn.update_rewards(ctx) == 3
    rewards = [ctx.store.get("posts", p["id"])["reward"] for p in posts]
    assert rewards[0] < rewards[1] < rewards[2]
    assert all(0 < ctx.store.get("posts", p["id"])["perf"] < 1 for p in posts)


def test_expiry_rules(make_ctx):
    ctx = _delivered(make_ctx)
    news = _card(ctx, "x")
    interview = _interview_card(ctx)
    timeutil.freeze("2026-09-28T19:45:00Z")  # next morning
    learn.expire_cards(ctx)
    assert ctx.store.get("cards", news["id"])["status"] == "expired"
    assert ctx.store.get("cards", interview["id"])["status"] == interview["status"] != "expired"  # lasts a week


def test_reflection_writes_playbook_experiments_and_report(make_ctx):
    ctx = _delivered(make_ctx)
    for card in ctx.store.select("cards", "status = 'suggested'")[:5]:
        learn.record_post(ctx, card, text=(card["draft"]["text"] or "\n\n".join(card["draft"]["posts"]))[:150],
                          posts=None, post_url=None, posted_at=timeutil.now_iso(), editing_seconds=100, hook_index=None)
    result = reflect.weekly_reflection(ctx)
    report = ctx.store.get("system_reports", result["id"])
    assert report and "source_yield" in report["sections"] and report["sections"]["reflection"]["summary"]
    active = playbook.active(ctx)
    assert active["version"] >= 2 and any(r["source"] == "reflection" for r in active["rules"])
    assert ctx.store.select("experiments", "status = 'active'")


def test_proposal_approval_applies_settings(make_ctx):
    ctx = make_ctx()
    pid = playbook.create_proposal(ctx, kind="pillar_weights", title="More affairs", detail=None,
                                   payload={"patch": {"strategy": {"x": {"affairs": {"weight": 0.4}}}}})
    write_inbox(ctx.data_root, [{"id": "p1", "type": "proposal.decide", "proposal_id": pid, "decision": "approve"}])
    inbox.ingest(ctx)
    assert ctx.store.get("proposals", pid)["status"] == "applied"
    assert ctx.settings.pillar("x", "affairs").weight == 0.4


def test_metrics_screenshot_extraction_matches_posts(make_ctx):
    from pbs import metrics

    ctx = _delivered(make_ctx)
    card = _card(ctx, "linkedin")
    post = learn.record_post(ctx, card, text="Agents need approval steps before they touch the back office.",
                             posts=None, post_url=None, posted_at=timeutil.now_iso(), editing_seconds=None,
                             hook_index=None)
    blob = ctx.data_root / "inbox" / "blobs" / "shot1.png"
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(json.dumps({"platform": "linkedin", "posts": [
        {"text_snippet": "Agents need approval steps before they touch", "impressions": "1.2K", "comments": 7,
         "confidence": 0.9},
        {"text_snippet": "Something we never posted", "impressions": 50, "confidence": 0.9}],
        "account": {"followers": 3120}}).encode())
    write_inbox(ctx.data_root, [{"id": "u1", "type": "metrics.upload", "upload_id": "upl_1",
                                 "paths": ["inbox/blobs/shot1.png"], "week": "2026-W40"}])
    inbox.ingest(ctx)
    stats = metrics.process_uploads(ctx)
    assert stats["metrics"] == 2 and stats["needs_review"] == 1
    confirmed = ctx.store.select("metrics", "status = 'confirmed'")
    assert confirmed[0]["post_id"] == post["id"] and confirmed[0]["impressions"] == 1200
    assert ctx.store.get("account_stats", f"acs_linkedin_{ctx.local_date_str()}")["followers"] == 3120
    assert (ctx.data_root / "media" / "metrics" / "2026-W40" / "shot1.png").exists()
    assert ctx.store.get("metric_uploads", "upl_1")["status"] == "processed"


def test_personal_draft_goes_to_non_training_provider_first(make_ctx):
    ctx = make_ctx(providers=fake_providers())
    _ = ctx.llm  # build the router
    chain = ctx.llm.chain("draft_personal", personal=True)
    assert chain[0] == "groq"
    assert not ctx.settings.llm.providers[chain[0]].trains_on_inputs


def test_voice_learns_phrases_not_function_words_or_punctuation():
    from pbs.voice import _ngrams

    grams = _ngrams("Does your team know ? Bottom line : the details matter more than the headline . "
                    "It ' s a really important shift")
    assert {"bottom line", "details matter", "really", "important shift"} <= grams
    assert not {"does your", "your team", "more than", "line : the details", "s a really", "matter more"} & grams
