"""The editor pass: a draft that reads as AI-written gets one more look, and the revision is kept only if better."""

from __future__ import annotations

import datetime as dt

import pytest
from conftest import fake_providers, write_inbox

from pbs import deliver, draft, editing, guardrails, inbox, learn, reflect, stats, style, timeutil, voice
from pbs.llm import fake
from pbs.style import Style

OPENING = "It's not about speed, it's about trust — and cost. Here's why: "  # contrast framing and a reveal
CLOSING = "\n\nIn short, test first — then scale."  # a summary closer and a second em dash


def _sounds_like_ai(req, data):
    """The usual fake draft, with the tells a model likes to add (LinkedIn posts and X threads)."""
    out = fake._draft(req, data)
    if out.get("text") and data.get("platform") == "linkedin":
        out["text"] = OPENING + out["text"] + CLOSING
    if out.get("posts"):
        out["posts"][0] = "It's not about speed, it's about trust. " + out["posts"][0]
    return out


def _ctx(make_ctx, **handlers):
    return make_ctx(providers=fake_providers(draft=_sounds_like_ai, draft_personal=_sounds_like_ai, **handlers))


def _calls(ctx, task):
    return [c for p in ctx.llm._providers.values() for c in p.calls if c.task == task]


def _linkedin(ctx):
    return ctx.store.select("cards", "platform = 'linkedin' AND status = 'suggested'", order="rank")[0]


def test_a_draft_that_sounds_like_ai_is_edited_and_the_better_version_kept(make_ctx, capsys):
    ctx = _ctx(make_ctx)
    deliver.morning_delivery(ctx)
    card = _linkedin(ctx)
    edit = card["llm"]["edit"]
    assert edit["kept"] and edit["after"] < edit["before"] and edit["provider"] == "groq"
    text = card["draft"]["text"]
    assert text.startswith("Speed matters less than trust, and cost.")
    assert "—" not in text and "Here's why" not in text and "In short" not in text
    assert not {t["kind"] for t in guardrails.ai_tells(text)} & {"contrast", "reveal", "closer", "dashes"}
    assert card["claims"][0]["text"] in text  # the facts survive
    # Edits are measured against the draft as shown, and any tells left are flagged on the card.
    assert card["draft_original"] == card["draft"]
    assert card["flags"]["ai_tells"] == guardrails.ai_tells(text)
    linkedin = ctx.store.count("cards", "platform = 'linkedin'")
    assert ctx.edits == len(_calls(ctx, "edit")) == linkedin + ctx.store.count("cards", "format = 'x_thread'")
    # The editor sees the tells it has to fix, and the draft as JSON.
    prompt = _calls(ctx, "edit")[0].prompt
    assert "contrast framing" in prompt and "It's not about speed, it's about trust" in prompt and "<input>" in prompt
    out = capsys.readouterr().out
    assert "edit: polished a linkedin draft (tells" in out
    assert "speed" not in out.lower()  # public logs carry counts, never the draft


def test_a_draft_without_tells_costs_no_call(make_ctx):
    ctx = make_ctx()
    card = {"platform": "linkedin", "format": "li_text"}
    norm = {"draft": {"text": "Acme cut claim handling from 9 days to 2. The queue stopped growing.", "posts": []}}
    assert editing.polish(ctx, card, norm, Style(), evidence="", personal=False)["edit"] is None
    assert not _calls(ctx, "edit") and ctx.edits == 0


def test_an_edit_that_adds_a_figure_is_thrown_away(make_ctx, capsys):
    def adds_a_figure(req, data):
        out = fake._edit(req, data)
        return {**out, "text": out["text"] + " Teams that tried it saw 73% fewer errors."}

    ctx = _ctx(make_ctx, edit=adds_a_figure)
    deliver.morning_delivery(ctx)
    card = _linkedin(ctx)
    assert card["llm"]["edit"]["kept"] is False
    assert card["llm"]["edit"]["reason"] == "added a figure the sources don't have"
    assert card["draft"]["text"].startswith(OPENING) and "73%" not in card["draft"]["text"]  # the original stays
    assert card["status"] == "suggested"
    assert "edit: kept the original draft of a linkedin card (added a figure" in capsys.readouterr().out


def test_an_edit_that_changes_nothing_is_not_kept(make_ctx):
    ctx = _ctx(make_ctx, edit=lambda req, data: {"text": data["text"], "posts": data["posts"]})
    deliver.morning_delivery(ctx)
    edit = _linkedin(ctx)["llm"]["edit"]
    assert edit["kept"] is False and edit["reason"] == "no fewer tells" and edit["before"] == edit["after"]


EVIDENCE = "Acme cut claim handling from 9 days to 2 days in 2025, a 41% saving, according to its annual report."
BEFORE = ("It's not about speed, it's about trust. Acme cut claim handling from 9 days to 2 days, a 41% saving.\n\n"
          "Here's why: the queue stopped growing.")
FIXED = ("Trust matters more than speed. Acme cut claim handling from 9 days to 2 days, a 41% saving.\n\n"
         "The queue stopped growing.")
LONG = FIXED + "\n\n" + " ".join(["queues grow when handoffs stall and nobody owns the next step"] * 60) + "."


@pytest.mark.parametrize(("after", "reason"), [
    (FIXED, None),
    ("", "empty"),
    (BEFORE, "no fewer tells"),
    (FIXED + " Teams saw 73% fewer errors.", "added a figure the sources don't have"),
    (FIXED.replace(", a 41% saving", ""), "dropped a figure"),
    (FIXED + " Contoso agrees.", "blocklist term"),
    (FIXED + " It's a game-changer.", "an avoided phrase"),
    (FIXED + " I've seen this at work.", "claimed an experience"),
    (LONG, "too long"),
    ("Handoffs decide it. Acme went from 9 days to 2 days, a 41% saving, by fixing who owns each claim next.",
     "rewrote too much"),
])
def test_a_revision_must_pass_every_check_the_draft_passed(make_ctx, after, reason):
    ctx = make_ctx()
    ctx.blocklist = ["Contoso"]
    card = {"platform": "linkedin", "format": "li_text", "mode": "external"}
    tells = len(guardrails.ai_tells(BEFORE))
    assert tells == 2
    got = editing.reject_reason(ctx, card, {"text": BEFORE, "posts": []}, {"text": after, "posts": []},
                                evidence=EVIDENCE, style=Style(avoid=["game-changer"]), tells_before=tells)
    assert got == reason


def test_first_hand_experience_may_stay_in_a_draft_from_answers(make_ctx):
    ctx = make_ctx()
    card = {"platform": "linkedin", "format": "li_text", "mode": "interview", "draft_basis": "answers",
            "answers": [{"question_id": "q1", "answer": "I've seen this at work."}]}
    assert editing.reject_reason(ctx, card, {"text": BEFORE, "posts": []},
                                 {"text": FIXED + " I've seen this at work.", "posts": []},
                                 evidence=EVIDENCE + " I've seen this at work.", style=Style(), tells_before=2) is None


def test_a_thread_keeps_its_length_and_loses_the_numbering(make_ctx):
    def numbered(req, data):
        out = fake._edit(req, data)
        return {"text": "", "posts": [f"{i}/{len(out['posts'])} {p}" for i, p in enumerate(out["posts"], 1)]}

    ctx = _ctx(make_ctx, edit=numbered)
    deliver.morning_delivery(ctx)
    card = ctx.store.select("cards", "format = 'x_thread'")[0]
    assert card["llm"]["edit"]["kept"]
    posts = card["draft"]["posts"]
    assert len(posts) == len(card["draft_original"]["posts"]) == 3
    assert posts[0].startswith("Speed matters less than trust.") and not posts[0][0].isdigit()
    before = {"text": "", "posts": ["It's not X, it's Y. One.", "Two.", "Three."]}
    after = {"text": "", "posts": ["Y. One.", "Two and three."]}
    assert editing.reject_reason(ctx, card, before, after, evidence="", style=Style(),
                                 tells_before=1) == "changed the thread's length"


@pytest.mark.parametrize("setup, reason", [
    (lambda ctx: setattr(ctx.settings.drafting, "editor_pass", False), "off"),
    (lambda ctx: ctx.run.degrade("fewer_cards"), "degraded run"),
    (lambda ctx: setattr(ctx, "edits", ctx.settings.drafting.editor_max_per_run), "run limit"),
    (lambda ctx: setattr(ctx.llm, "remaining", lambda task, personal=False: ctx.settings.drafting.editor_reserve),
     "budget"),
])
def test_the_pass_is_skipped_when_off_or_short_on_calls(make_ctx, setup, reason):
    ctx = make_ctx()
    setup(ctx)
    card = {"platform": "linkedin", "format": "li_text"}
    norm = {"draft": {"text": BEFORE, "posts": []}}
    out = editing.polish(ctx, card, norm, Style(), evidence=EVIDENCE, personal=False)
    assert out["edit"] == {"before": 2, "after": 2, "kept": False, "kinds": ["contrast", "reveal"], "skipped": reason}
    assert out["draft"]["text"] == BEFORE and not _calls(ctx, "edit")


def test_the_run_limit_caps_edits_and_drafts_still_arrive(make_ctx):
    ctx = _ctx(make_ctx)
    ctx.settings.drafting.editor_max_per_run = 1
    deliver.morning_delivery(ctx)
    cards = ctx.store.select("cards", "platform = 'linkedin'")
    edits = [c["llm"]["edit"] for c in cards]
    assert sum(1 for e in edits if e.get("kept")) == 1 and len(_calls(ctx, "edit")) == 1
    assert all(e.get("skipped") == "run limit" for e in edits if not e.get("kept"))
    assert all(c["status"] == "suggested" and c["draft"]["text"] for c in cards)


def test_a_failed_edit_leaves_the_draft_as_it_was(make_ctx):
    ctx = _ctx(make_ctx, edit=lambda req, data: "Sorry, I can't help with that.")
    deliver.morning_delivery(ctx)
    card = _linkedin(ctx)
    assert card["llm"]["edit"]["skipped"] and card["llm"]["edit"]["kept"] is False
    assert card["draft"]["text"].startswith(OPENING) and card["status"] == "suggested"


def test_drafts_from_answers_are_edited_with_personal_routing(make_ctx):
    ctx = _ctx(make_ctx)
    deliver.weekly_batch(ctx)
    card = ctx.store.select("cards", "kind = 'interview' AND platform = 'linkedin'", order="created_at")[0]
    assert all(not c.personal for c in _calls(ctx, "edit"))  # drafts from sources: no personal content
    q = card["questions"][0]["id"]
    write_inbox(ctx.data_root, [{"id": "a1", "type": "card.answers", "card_id": card["id"],
                                 "answers": [{"question_id": q, "answer": "We learned exception handling matters."}]}])
    inbox.ingest(ctx)
    draft.process_work(ctx)
    card = ctx.store.get("cards", card["id"])
    assert card["draft_basis"] == "answers" and card["llm"]["edit"]["kept"]
    assert "exception handling" in card["draft"]["text"]
    last = max(_calls(ctx, "edit"), key=lambda c: "exception handling" in c.prompt)
    assert "exception handling" in last.prompt and last.personal


# ---------------------------------------------------------------------------
# Learning from what gets posted
# ---------------------------------------------------------------------------


def _post(ctx, card, text, at="2026-09-27T21:00:00Z"):
    return learn.record_post(ctx, card, text=text, posts=None, post_url=None, posted_at=at, editing_seconds=60,
                             hook_index=None)


def test_tells_taken_out_of_drafts_again_and_again_become_style_rules(make_ctx):
    ctx = _ctx(make_ctx)
    ctx.settings.drafting.editor_pass = False  # drafts arrive with their tells
    deliver.morning_delivery(ctx)
    cards = ctx.store.select("cards", "platform = 'linkedin' AND status = 'suggested'")
    assert len(cards) == 3
    for card in cards:  # the em dashes and the "Here's why:" go; the rest stays
        _post(ctx, card, card["draft"]["text"].replace(" — ", ", ").replace("Here's why: ", ""))
    post = ctx.store.select("posts", "platform = 'linkedin'")[0]
    assert {"contrast", "dashes", "reveal", "closer"} <= set(post["edit_stats"]["tells_draft"])
    assert "dashes" not in post["edit_stats"]["tells_final"] and "contrast" in post["edit_stats"]["tells_final"]
    profile = voice.update_voice(ctx)
    tells = profile["stats"]["linkedin"]["tells"]
    assert tells["cut"] == {"dashes": 3, "reveal": 3} and tells["avoid"] == ["dashes", "reveal"]
    assert tells["per_draft"] > tells["per_post"]
    assert "On LinkedIn, don't use em dashes: use a comma, a full stop or brackets." in profile["rules"]
    assert any(r.startswith("On LinkedIn, make the point without a label") for r in profile["rules"])
    assert not any("it's not X" in r for r in profile["rules"])  # kept in what was posted: no rule
    # Posts recorded before tells were: worked out from the card.
    stats = {k: v for k, v in post["edit_stats"].items() if not k.startswith("tells_")}
    ctx.store.update("posts", post["id"], edit_stats=stats)
    assert learn.post_tells(ctx, ctx.store.get("posts", post["id"])) == (post["edit_stats"]["tells_draft"],
                                                                         post["edit_stats"]["tells_final"])


def test_a_tell_that_keeps_going_into_posts_by_hand_is_left_alone(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    for card in ctx.store.select("cards", "platform = 'x' AND status = 'suggested'")[:3]:
        _post(ctx, card, "Approval steps first — then the agents — then the back office.")
    voice.update_voice(ctx)
    assert style.style_for(ctx, "x", "tech", "x_single").own_tells == ["dashes"]
    assert style.style_for(ctx, "linkedin", "tech", "li_text").own_tells == []
    x, li = style.style_for(ctx, "x", "tech", "x_single"), style.style_for(ctx, "linkedin", "tech", "li_text")
    text = "Approval steps first — then the agents — then the back office. Here's why: audits."
    assert [t["kind"] for t in editing.tells_in(text, x)] == ["reveal"]
    assert [t["kind"] for t in editing.tells_in(text, li)] == ["dashes", "reveal"]


def test_voice_examples_are_the_posts_with_fewest_tells_and_most_words_written_by_hand(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    cards = ctx.store.select("cards", "platform = 'x' AND status = 'suggested'", order="rank")[:4]
    ai = _post(ctx, cards[0], "It's not about speed, it's about trust. Here's why: queues grow.",
               at="2026-09-27T20:00:00Z")
    as_drafted = _post(ctx, cards[1], cards[1]["draft"]["text"] or "\n\n".join(cards[1]["draft"]["posts"]),
                       at="2026-09-27T20:10:00Z")
    by_hand = _post(ctx, cards[2], "Approval steps saved a week of back-office rework, and nobody missed the old queue.",
                    at="2026-09-27T20:20:00Z")
    newest_ai = _post(ctx, cards[3], "In today's world, agents matter. Ultimately, trust wins.",
                      at="2026-09-27T20:30:00Z")
    assert [p["id"] for p in style.example_posts(ctx, "x", 3)] == [by_hand["id"], as_drafted["id"], newest_ai["id"]]
    assert style.recent_examples(ctx, "x", 1) == [by_hand["final_text"]]
    assert voice.update_voice(ctx)["examples"]["x"] == [by_hand["id"], as_drafted["id"], newest_ai["id"]]
    assert ai["id"] not in voice.update_voice(ctx)["examples"]["x"]


def test_insights_and_the_weekly_reflection_see_the_tells(make_ctx):
    ctx = _ctx(make_ctx)
    deliver.morning_delivery(ctx)
    card = _linkedin(ctx)
    _post(ctx, card, card["draft"]["text"] + " It's not hype, it's plumbing.")
    writing = stats.compute(ctx)["writing"]
    week = writing["weekly"][-1]
    drafted = ctx.store.count("cards", "delivered_at IS NOT NULL")
    assert week["week"] == "2026-W40" and week["drafts"] == drafted
    assert week["tells_before"] > week["tells_shown"]
    assert week["posts"] == 1 and week["tells_posted"] == 1 and week["edit_ratio_median"] > 0
    kinds = {k["kind"]: k["count"] for k in writing["kinds"]}
    polished = ctx.store.count("cards", "platform = 'linkedin'") + ctx.store.count("cards", "format = 'x_thread'")
    assert kinds["contrast"] == polished and writing["edits"] == {"polished": polished, "kept_as_written": 0,
                                                                  "skipped": 0}
    end = timeutil.now()
    week_input = reflect._week_input(ctx, end - dt.timedelta(days=7), end + dt.timedelta(hours=2))
    post = week_input["posts"][0]
    assert post["ai_tells_in_draft"] == [] and post["ai_tells_posted"] == ["contrast"]
    assert week_input["writing"]["editor_kept"] == polished
    assert week_input["writing"]["tells_before_editor"] > week_input["writing"]["tells_after_editor"]
