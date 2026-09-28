"""Hashtags, the first comment, cross-posting between LinkedIn and X, and the researched platform guide."""

from __future__ import annotations

from conftest import write_inbox

from pbs import (
    bandit,
    deliver,
    draft,
    export,
    feedback,
    hashtags,
    inbox,
    learn,
    platform,
    stats,
    timeutil,
    voice,
)
from pbs.demo.build import platform_world
from pbs.style import style_for


def _card(ctx, platform_="linkedin", status="suggested", fmt=None):
    where, params = "platform = ? AND status = ?", [platform_, status]
    if fmt:
        where += " AND format = ?"
        params.append(fmt)
    return ctx.store.select("cards", where, params, order="rank")[0]


def _calls(ctx, task):
    return [c for p in ctx.llm._providers.values() for c in p.calls if c.task == task]


# ---------------------------------------------------------------------------
# Hashtags
# ---------------------------------------------------------------------------


def test_hashtags_are_normalized_and_cleaned():
    assert hashtags.normalize("#AI agents") == "#AIAgents"
    assert hashtags.normalize("process automation") == "#ProcessAutomation"
    assert hashtags.normalize("#RPA") == "#RPA"
    assert hashtags.normalize("#1") is None and hashtags.normalize("  ") is None
    assert hashtags.normalize("#" + "a" * 31) is None
    tags = hashtags.clean(["#AI", "ai", "#Innovation", "#ContosoCloud", " process automation ", "#Workflows"], 3,
                          avoid=["#Innovation"], blocklist=["Contoso"])
    assert tags == ["#AI", "#ProcessAutomation", "#Workflows"]  # deduplicated, avoided and blocked ones gone
    assert hashtags.clean(["#AI", "#ML"], 0) == []


def test_trailing_hashtags_are_split_from_the_post_but_not_numbers_in_it():
    assert hashtags.split_trailing("The point.\n\n#AI #Automation") == ("The point.", ["#AI", "#Automation"])
    assert hashtags.split_trailing("Short take #AI") == ("Short take", ["#AI"])
    assert hashtags.split_trailing("We ranked #1 in the test") == ("We ranked #1 in the test", [])
    assert hashtags.split_trailing("#AI") == ("#AI", [])  # nothing but a tag: left alone
    posts, tags = hashtags.strip_from_posts(["Post one #AI", "Post two", "Post three\n#Agents"])
    assert posts == ["Post one", "Post two", "Post three"] and sorted(tags) == ["#AI", "#Agents"]


def test_drafts_carry_hashtags_and_a_first_comment_outside_the_text(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    li, x = _card(ctx, "linkedin"), _card(ctx, "x")
    assert 1 <= len(li["hashtags"]) <= 5 and all(t.startswith("#") for t in li["hashtags"])
    assert "#" not in li["draft"]["text"].split("\n")[-1]
    assert len(x["hashtags"]) <= 2
    assert li["draft"]["first_comment"].endswith(li["sources"][0]["url"])
    prompt = _calls(ctx, "draft")[0].prompt
    assert "What works on" in prompt and '"hashtags"' in prompt and '"first_comment"' in prompt


def test_normalize_output_moves_stray_tags_and_drops_blocked_and_invented_links(make_ctx, monkeypatch):
    monkeypatch.setenv("PBS_BLOCKLIST", "Contoso")
    ctx = make_ctx()
    card = {"id": "crd_t", "platform": "linkedin", "format": "li_text", "title": "Agents at work", "pillar": "industry"}
    sources = [{"url": "https://example.com/report", "title": "Report"}]
    out = draft.DraftOut(text="The point.\n\nMore detail.\n\n#AI #ContosoAgents", hashtags=["ProcessAutomation", "#AI"],
                         first_comment="Full study: https://invented.example/x")
    norm = draft.normalize_output(ctx, card, out, sources)
    assert norm["draft"]["text"] == "The point.\n\nMore detail."
    assert norm["hashtags"] == ["#ProcessAutomation", "#AI"]
    assert norm["draft"]["first_comment"] == "Full study: https://example.com/report"
    reply = {**card, "platform": "x", "format": "x_reply"}
    norm = draft.normalize_output(ctx, reply, draft.DraftOut(text="Good point.", hashtags=["#AI"],
                                                             first_comment="x"), sources)
    assert norm["hashtags"] == [] and "first_comment" not in norm["draft"]


def test_first_comment_keeps_only_the_cards_own_sources():
    src = [{"url": "https://example.com/a"}, {"url": "https://example.com/b"}]
    assert draft.first_comment("Source: https://example.com/b", src) == "Source: https://example.com/b"
    assert draft.first_comment("Read more: https://fake.example/x.", src) == "Read more: https://example.com/a"
    assert draft.first_comment("", src) == "Source: https://example.com/a"
    assert draft.first_comment("Link: https://fake.example/x", []) == ""


def test_hashtags_can_be_turned_off(make_ctx):
    ctx = make_ctx()
    ctx.store.set_setting("overrides", {"hashtags": {"enabled": False}})
    ctx.reload_settings()
    style = style_for(ctx, "linkedin", "industry", "li_text")
    assert draft.hashtag_rule(ctx, "linkedin", "li_text", style).startswith("[]")
    card = {"id": "crd_t", "platform": "linkedin", "format": "li_text", "title": "t", "pillar": "industry"}
    norm = draft.normalize_output(ctx, card, draft.DraftOut(text="Text.", hashtags=["#AI"]), [])
    assert norm["hashtags"] == []


def test_posted_tags_are_recorded_and_dont_count_as_edits(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx, "linkedin")
    kept = card["hashtags"][:2]
    text = f"{card['draft']['text']}\n\n{' '.join(kept)}"
    write_inbox(ctx.data_root, [{"id": "p1", "type": "card.posted", "card_id": card["id"], "text": text,
                                 "hashtags": kept}])
    assert inbox.ingest(ctx)["rejected"] == 0
    post = ctx.store.select("posts", "card_id = ?", (card["id"],))[0]
    assert post["edit_ratio"] == 0.0
    assert post["hashtags"] == kept
    assert post["features"]["hashtags_offered"] == card["hashtags"]
    assert post["features"]["hashtags_used"] == len(kept)
    body, found = learn.posted_body("li_text", text, [])
    assert body == card["draft"]["text"] and found == kept


def test_tags_deleted_before_posting_are_not_counted_as_used(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx, "linkedin")
    # The desk said which tags were chosen, but he deleted the tag line in the Posted dialog.
    write_inbox(ctx.data_root, [{"id": "p3", "type": "card.posted", "card_id": card["id"],
                                 "text": card["draft"]["text"], "hashtags": card["hashtags"]}])
    inbox.ingest(ctx)
    post = ctx.store.select("posts", "card_id = ?", (card["id"],))[0]
    assert post["hashtags"] == [] and post["features"]["hashtags_used"] == 0
    assert post["features"]["hashtags_offered"] == card["hashtags"]


def test_voice_learns_which_tags_he_keeps_and_retires_the_old_no_hashtags_rule():
    posts = [{"features": {"hashtags_offered": ["#AI", "#Automation", "#RPA"]}, "hashtags": ["#AI", "#RPA", "#UiPath"]}
             for _ in range(3)] + [{"features": {}, "hashtags": []}]
    s = voice._hashtag_stats(posts)
    assert s["offered_posts"] == 3 and s["keep_rate"] == 0.67
    assert s["kept"][:2] == ["#AI", "#RPA"] and s["dropped"] == ["#Automation"] and s["added"] == ["#UiPath"]
    stats_ = {"x": {"posts": 6, "hashtags": {"offered_posts": 5, "keep_rate": 0.0}}}
    assert "He removes the suggested hashtags on X: suggest none." in voice.deterministic_rules(stats_)
    assert not any(r.startswith("No hashtags on") for r in voice.deterministic_rules(stats_))
    assert "No hashtags on X.".startswith(voice.RETIRED_RULES)


def test_the_drafter_hears_which_tags_he_keeps_and_drops(make_ctx):
    ctx = make_ctx()
    style = style_for(ctx, "linkedin", "industry", "li_text")
    style.hashtags_kept, style.hashtags_dropped = ["#AI"], ["#Automation"]
    rule = draft.hashtag_rule(ctx, "linkedin", "li_text", style)
    assert "3 to 5 hashtags" in rule and "keeps #AI" in rule and "removes #Automation" in rule
    assert draft.hashtag_rule(ctx, "x", "x_reply", style).startswith("[]")


def test_where_he_removes_nearly_all_tags_none_are_suggested(make_ctx):
    ctx = make_ctx()
    assert not hashtags.mostly_removed({"offered_posts": 3, "keep_rate": 0.0})  # too few posts to tell
    assert hashtags.mostly_removed({"offered_posts": 4, "keep_rate": 0.1})
    style = style_for(ctx, "x", "tech", "x_single")
    style.hashtags_off = True
    assert draft.hashtag_rule(ctx, "x", "x_single", style).startswith("[] (he removes the suggested ones on X")
    card = {"id": "crd_t", "platform": "x", "format": "x_single", "title": "t", "pillar": "tech"}
    norm = draft.normalize_output(ctx, card, draft.DraftOut(text="Short take. #AI", hashtags=["#AI"]), [], style)
    assert norm["hashtags"] == [] and norm["draft"]["text"] == "Short take."


# ---------------------------------------------------------------------------
# Cross-posting
# ---------------------------------------------------------------------------


def test_crosspost_both_makes_a_learnable_card_for_the_other_platform(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    source = _card(ctx, "linkedin")
    write_inbox(ctx.data_root, [{"id": "xp1", "type": "card.crosspost", "card_id": source["id"],
                                 "target_platform": "x", "target_format": "x_thread", "mode": "both",
                                 "note": "Works as a thread too"}])
    assert inbox.ingest(ctx)["rejected"] == 0
    assert ctx.store.get("cards", source["id"])["work"]["crosspost"] == "both"
    draft.process_work(ctx)
    made = ctx.store.select("cards", "crosspost_of = ?", (source["id"],))
    assert len(made) == 1
    card = made[0]
    assert card["platform"] == "x" and card["format"] == "x_thread" and card["kind"] == "adapt"
    assert card["status"] == "suggested" and card["draft"]["posts"]
    assert card["delivery_id"] == source["delivery_id"] and card["arm"] == f"x:{card['pillar']}:x_thread"
    assert len(card["hashtags"]) <= 2
    original = ctx.store.get("cards", source["id"])
    assert original["status"] == "suggested" and original["work"] is None
    assert any("Adapt this LinkedIn post for X" in c.prompt for c in _calls(ctx, "draft_personal"))
    rows = feedback.recent_feedback(ctx)
    assert rows[0]["kind"] == "crosspost" and rows[0]["to"] == "x"
    assert "on X too" in feedback.render(rows)
    assert stats.compute(ctx)["crossposts"] == {"linkedin_to_x": 1, "x_to_linkedin": 0, "both": 1, "switch": 0,
                                                "made": 1, "posted": 0}


def test_crosspost_switch_skips_the_original_as_the_wrong_platform(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    source = _card(ctx, "x", fmt="x_single")
    write_inbox(ctx.data_root, [{"id": "xp2", "type": "card.crosspost", "card_id": source["id"],
                                 "target_platform": "linkedin", "mode": "switch", "note": "Needs more room"}])
    inbox.ingest(ctx)
    original = ctx.store.get("cards", source["id"])
    assert original["status"] == "skipped" and original["skip"]["reason"] == "wrong_platform"
    assert original["skip"]["note"] == "Needs more room"
    value = bandit.observation_value(original, None, ctx.settings, set(), {})
    assert value == ctx.settings.learning.skip_values["wrong_platform"] == 0.3  # milder than "not interesting"
    draft.process_work(ctx)
    card = ctx.store.select("cards", "crosspost_of = ?", (source["id"],))[0]
    assert card["platform"] == "linkedin" and card["format"] == "li_text" and card["status"] == "suggested"
    rows = feedback.recent_feedback(ctx)
    assert [r["kind"] for r in rows if r["card_id"] == source["id"]] == ["crosspost"]  # not listed twice
    assert "right topic, wrong platform" in feedback.render(rows)
    assert stats.compute(ctx)["crossposts"]["switch"] == 1


def test_crosspost_to_the_same_platform_is_rejected_and_a_posted_card_keeps_both(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx, "linkedin")
    write_inbox(ctx.data_root, [
        {"id": "xp3", "type": "card.crosspost", "card_id": card["id"], "target_platform": "linkedin"},
        {"id": "xp4", "type": "card.crosspost", "card_id": card["id"], "target_platform": "x",
         "target_format": "li_text"},
        {"id": "p2", "type": "card.posted", "card_id": card["id"]},
        {"id": "xp5", "type": "card.crosspost", "card_id": card["id"], "target_platform": "x", "mode": "switch"},
    ])
    res = inbox.ingest(ctx)
    assert res["rejected"] == 2
    after = ctx.store.get("cards", card["id"])
    assert after["status"] == "posted" and after["work"]["crosspost"] == "both"


def test_a_failed_crosspost_is_retried_on_the_same_card(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    source = _card(ctx, "linkedin")
    write_inbox(ctx.data_root, [{"id": "xp6", "type": "card.crosspost", "card_id": source["id"],
                                 "target_platform": "x"}])
    inbox.ingest(ctx)
    good = {name: dict(p.handlers) for name, p in ctx.llm._providers.items()}
    for p in ctx.llm._providers.values():
        p.handlers["draft"] = p.handlers["draft_personal"] = lambda req, data: {"text": "", "posts": []}
    assert draft.process_work(ctx)["failed"] == 1
    failed = ctx.store.select("cards", "crosspost_of = ?", (source["id"],))
    assert len(failed) == 1 and failed[0]["status"] == "failed"
    assert ctx.store.get("cards", source["id"])["work"]["attempts"] == 1
    for name, p in ctx.llm._providers.items():
        p.handlers = good[name]
    assert draft.process_work(ctx)["done"] == 1
    made = ctx.store.select("cards", "crosspost_of = ?", (source["id"],))
    assert [c["id"] for c in made] == [failed[0]["id"]] and made[0]["status"] == "suggested"


def test_rewrites_keep_his_chosen_hashtags_in_view(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx, "linkedin")
    write_inbox(ctx.data_root, [
        {"id": "e1", "type": "card.edit", "card_id": card["id"], "text": card["draft"]["text"],
         "hashtags": ["#AI", "#RPA"]},
        {"id": "r1", "type": "card.rewrite", "card_id": card["id"], "note": "Shorter", "chips": []},
    ])
    inbox.ingest(ctx)
    assert ctx.store.get("cards", card["id"])["working"]["hashtags"] == ["#AI", "#RPA"]
    draft.process_work(ctx)
    rewrites = [c.prompt for c in _calls(ctx, "draft_personal") + _calls(ctx, "draft") if "His note:" in c.prompt]
    assert len(rewrites) == 1
    assert '"#AI"' in rewrites[0].rsplit('"current_hashtags"', 1)[1][:40] and "start from \"current_hashtags\"" in rewrites[0]


# ---------------------------------------------------------------------------
# Platform guide and monthly research
# ---------------------------------------------------------------------------


def test_the_guide_reaches_drafts_for_the_right_platform_and_format(make_ctx):
    ctx = make_ctx()
    rules = platform.current_rules(ctx)
    ids_ = [r["id"] for r in rules]
    assert len(ids_) == len(set(ids_)) and {"li-fold", "x-first", "x-thread-hook"} <= set(ids_)
    li = platform.rules_for(ctx, "linkedin", "li_text")
    thread = platform.rules_for(ctx, "x", "x_thread")
    single = platform.rules_for(ctx, "x", "x_single")
    assert any("210 characters" in r for r in li) and not any("210 characters" in r for r in thread)
    assert any("first post must stand alone" in r for r in thread)
    assert not any("first post must stand alone" in r for r in single)
    assert style_for(ctx, "x", "tech", "x_thread").platform_rules == thread


def test_approved_guide_changes_apply_in_order(make_ctx):
    ctx = make_ctx()
    assert platform.apply_update(ctx, {"op": "add", "platform": "x", "text": "Answer replies in the first hour.",
                                       "sources": ["https://example.com/a"]}) is None
    assert platform.apply_update(ctx, {"op": "modify", "rule_id": "li-tags", "text": "Two or three hashtags."}) is None
    assert platform.apply_update(ctx, {"op": "remove", "rule_id": "x-small"}) is None
    assert platform.apply_update(ctx, {"op": "remove", "rule_id": "x-small"}) is not None  # already gone
    assert platform.apply_update(ctx, {"op": "add", "platform": "x", "text": "  "}) is not None
    rules = {r["id"]: r for r in platform.current_rules(ctx)}
    added = [r for r in rules.values() if r["text"] == "Answer replies in the first hour."][0]
    assert added["source"] == "research" and added["sources"] == ["https://example.com/a"]
    assert rules["li-tags"]["text"] == "Two or three hashtags." and "x-small" not in rules
    assert "Answer replies in the first hour." in platform.rules_for(ctx, "x", "x_single")


def test_monthly_research_proposes_changes_citing_only_the_articles_it_read(make_ctx, web):
    web.world.update(platform_world(timeutil.now()))
    ctx = make_ctx()
    assert platform.research_due(ctx)

    def research(req, data):
        ids_ = [a["id"] for a in data]
        return {"summary": "Comments matter more.", "changes": [
            {"op": "modify", "rule_id": "li-save", "text": "Aim for saves and thoughtful comments.",
             "evidence": [ids_[0], "A99"], "confidence": "medium", "why": "Reported this month."},
            {"op": "add", "platform": "x", "text": "Unsupported claim.", "evidence": ["A99"]},
            {"op": "remove", "rule_id": "no-such-rule", "evidence": [ids_[0]]},
        ]}

    for p in ctx.llm._providers.values():
        p.handlers["research"] = research
    res = platform.research(ctx)
    assert res == {"articles": 4, "proposals": 1}
    proposal = ctx.store.select("proposals", "kind = 'platform_guide'")[0]
    urls = {f"https://news.google.com/rss/articles/{s}" for s in ("li-feed-comments", "li-documents", "x-first-hour",
                                                                    "x-links")}
    change = proposal["payload"]["guide_change"]
    assert change["op"] == "modify" and change["rule_id"] == "li-save" and change["platform"] == "linkedin"
    assert change["sources"] and set(change["sources"]) <= urls and proposal["evidence"] == change["sources"]
    assert [a["url"] for a in change["articles"]] == change["sources"]
    assert change["articles"][0]["title"].startswith("What creators are seeing in LinkedIn's feed")
    assert "Replaces:" in proposal["detail"]
    assert not platform.research_due(ctx)
    assert ctx.store.get_setting("platform_research_summary")["proposals"] == 1

    write_inbox(ctx.data_root, [{"id": "d1", "type": "proposal.decide", "proposal_id": proposal["id"],
                                 "decision": "approve"}])
    assert inbox.ingest(ctx)["rejected"] == 0
    rule = {r["id"]: r for r in platform.current_rules(ctx)}["li-save"]
    assert rule["text"] == "Aim for saves and thoughtful comments." and rule["source"] == "research"
    assert rule["articles"] == change["articles"]


def test_research_without_coverage_changes_nothing_and_waits_a_month(make_ctx):
    ctx = make_ctx()
    assert platform.research(ctx) == {"articles": 0, "proposals": 0}
    assert not platform.research_due(ctx) and not ctx.store.select("proposals")
    assert not _calls(ctx, "research")


def test_the_desk_gets_the_guide_and_research_summary(make_ctx):
    ctx = make_ctx()
    ctx.store.set_setting("platform_research_summary", {"month": "2026-09", "summary": "s", "articles": 2,
                                                        "proposals": 0})
    guide = export.build(ctx)["platform_guide"]
    assert guide["reviewed"] and len(guide["rules"]) == len(platform.current_rules(ctx))
    assert guide["research"]["month"] == "2026-09"
