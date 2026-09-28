"""Visuals: carousels, flowcharts, comparisons, lists, big numbers and quote cards drawn by the desk."""

from __future__ import annotations

import pytest
from conftest import write_inbox

from pbs import deliver, draft, inbox, stats, visuals
from pbs.visuals import VisualOut


def _card(ctx, platform="linkedin", status="suggested"):
    return ctx.store.select("cards", "platform = ? AND status = ?", (platform, status), order="rank")[0]


def _calls(ctx, task):
    return [c for p in ctx.llm._providers.values() for c in p.calls if c.task == task]


def _ask(ctx, card, kind="auto", note="", ev_id="v1"):
    write_inbox(ctx.data_root, [{"id": ev_id, "type": "card.visual", "card_id": card["id"], "kind": kind,
                                 "note": note}], name=ev_id)
    return inbox.ingest(ctx)


def _set_handler(ctx, fn):
    for p in ctx.llm._providers.values():
        p.handlers["visual"] = fn


def test_a_visual_is_requested_then_drawn_from_the_cards_text(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    assert _ask(ctx, card)["rejected"] == 0
    queued = ctx.store.get("cards", card["id"])
    assert queued["work"]["kind"] == "visual" and queued["work"]["visual_kind"] == "auto"
    assert queued["revision"] == card["revision"]  # not a new version of the text
    assert draft.process_work(ctx)["done"] == 1
    done = ctx.store.get("cards", card["id"])
    v = done["visual"]
    assert done["work"] is None and v["kind"] == "carousel"
    assert 3 <= len(v["items"]) <= 8 and v["title"] and v["alt_text"] and v["created_at"]
    assert v["sources"] == [0] and v["unsourced"] == []
    prompt = _calls(ctx, "visual")[0].prompt
    assert "Pick the kind that suits the post best" in prompt and "1080×1350" in prompt
    assert card["draft"]["text"][:60] in prompt
    types = [i["type"] for i in ctx.store.select("interactions", "card_id = ?", (card["id"],))]
    assert "visual_requested" in types and "visual_created" in types


@pytest.mark.parametrize("kind", ["flow", "compare", "list", "stat", "quote"])
def test_each_kind_can_be_asked_for(make_ctx, kind):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx, "x")
    _ask(ctx, card, kind=kind)
    draft.process_work(ctx)
    v = ctx.store.get("cards", card["id"])["visual"]
    assert v["kind"] == kind
    fewest, most = visuals.LIMITS[kind]
    assert fewest <= len(v["items"]) <= most
    assert "1600×900" in _calls(ctx, "visual")[0].prompt


def test_a_carousel_for_x_is_a_cover_and_three_slides(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx, "x")
    _ask(ctx, card, kind="carousel")
    draft.process_work(ctx)
    assert len(ctx.store.get("cards", card["id"])["visual"]["items"]) <= 3
    assert "X shows at most four images" in _calls(ctx, "visual")[0].prompt
    out = VisualOut(kind="carousel", items=[{"title": str(i)} for i in range(6)])
    assert len(visuals.clean(out, "carousel", 0, "x")["items"]) == 3
    assert len(visuals.clean(out, "carousel", 0, "linkedin")["items"]) == 6


def test_clean_fits_the_visual_to_what_can_be_drawn():
    long = "word " * 200
    out = VisualOut(kind="flow", title="T", items=[{"title": long, "body": long}] * 9)
    v = visuals.clean(out, "auto", 0)
    assert v["kind"] == "flow" and len(v["items"]) == 7
    assert len(v["items"][0]["title"]) <= visuals.TITLE_MAX["flow"]
    assert len(v["items"][0]["body"]) <= visuals.BODY_MAX["flow"]
    # The kind he asked for wins over the model's; unknown kinds become a carousel.
    assert visuals.clean(VisualOut(kind="flow", items=[{"title": "a"}] * 3), "list", 0)["kind"] == "list"
    assert visuals.clean(VisualOut(kind="poster", items=[{"title": "a"}] * 3), "auto", 0)["kind"] == "carousel"
    with pytest.raises(ValueError):
        visuals.clean(VisualOut(kind="compare", items=[{"title": "only one"}]), "auto", 0)
    cmp = visuals.clean(VisualOut(kind="compare", items=[
        {"title": "Demo", "points": ["- clean data", "2. happy path", "one", "two", "three", "four"]},
        {"title": "Production", "body": "• messy data\nexceptions"}]), "auto", 3)
    assert cmp["items"][0]["body"].split("\n") == ["clean data", "happy path", "one", "two", "three"]
    assert cmp["items"][1]["body"] == "messy data\nexceptions"
    assert visuals.clean(VisualOut(kind="stat", items=[{"title": "41%"}], sources=[0, 5, "1"]), "auto", 2)[
        "sources"] == [0, 1]


def test_figures_the_sources_dont_have_are_flagged(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _set_handler(ctx, lambda req, data: {"kind": "stat", "title": "Agents at work",
                                         "items": [{"title": "93%", "body": "of teams, apparently"}]})
    _ask(ctx, card, kind="stat")
    draft.process_work(ctx)
    assert ctx.store.get("cards", card["id"])["visual"]["unsourced"] == ["93%"]


def test_a_visual_with_a_blocklist_term_is_not_kept(make_ctx, monkeypatch):
    monkeypatch.setenv("PBS_BLOCKLIST", "Contoso")
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _set_handler(ctx, lambda req, data: {"kind": "list", "title": "What Contoso learned",
                                         "items": [{"title": "a"}, {"title": "b"}, {"title": "c"}]})
    _ask(ctx, card, kind="list")
    draft.process_work(ctx)
    after = ctx.store.get("cards", card["id"])
    assert after.get("visual") is None and after["work"] is None
    assert any("blocklist" in n for n in after["flags"]["notes"])
    assert ctx.store.select("interactions", "type = 'visual_blocked'")


def test_visual_requests_are_rejected_when_they_cant_be_drawn(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    busy = _card(ctx)
    write_inbox(ctx.data_root, [{"id": "r1", "type": "card.rewrite", "card_id": busy["id"], "note": "Shorter"}],
                name="r1")
    inbox.ingest(ctx)
    assert _ask(ctx, busy, ev_id="v2")["rejected"] == 1
    empty = _card(ctx, "x")
    empty.update(draft=None, working=None)
    ctx.store.upsert("cards", empty)
    assert _ask(ctx, empty, ev_id="v3")["rejected"] == 1
    ctx.store.set_setting("overrides", {"visuals": {"enabled": False}})
    ctx.reload_settings()
    assert _ask(ctx, _card(ctx, "x"), ev_id="v4")["rejected"] == 1


def test_his_edits_to_the_visual_are_kept_until_a_new_visual_arrives(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _ask(ctx, card, kind="list")
    draft.process_work(ctx)
    base = ctx.store.get("cards", card["id"])["visual"]
    edited = {"kind": "list", "title": "My own headline", "items": [{"title": "One", "body": ""},
                                                                    {"title": "Two", "body": ""},
                                                                    {"title": "Three", "body": ""}],
              "alt_text": "A list of three"}
    write_inbox(ctx.data_root, [{"id": "e1", "type": "card.edit", "card_id": card["id"],
                                 "text": card["draft"]["text"], "visual": edited}], name="e1")
    assert inbox.ingest(ctx)["rejected"] == 0
    working = ctx.store.get("cards", card["id"])["working"]["visual"]
    assert working["title"] == "My own headline" and working["created_at"] == base["created_at"]
    _ask(ctx, card, kind="carousel", ev_id="v5")
    draft.process_work(ctx)
    after = ctx.store.get("cards", card["id"])
    assert after["visual"]["kind"] == "carousel" and after["working"]["visual"] is None


def test_posting_with_the_visual_is_learned_from(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    with_visual, without = _card(ctx), _card(ctx, "x")
    _ask(ctx, with_visual, kind="flow")
    draft.process_work(ctx)
    write_inbox(ctx.data_root, [
        {"id": "p1", "type": "card.posted", "card_id": with_visual["id"], "with_visual": True},
        {"id": "p2", "type": "card.posted", "card_id": without["id"]},
    ], name="p")
    assert inbox.ingest(ctx)["rejected"] == 0
    posts = {p["card_id"]: p for p in ctx.store.select("posts")}
    assert posts[with_visual["id"]]["features"]["visual"] == "flow"
    assert posts[without["id"]]["features"]["visual"] is None
    s = stats.compute(ctx)["visuals"]
    assert s["kinds"] == {"flow": 1} and s["made"] == 1
    assert s["linkedin"]["with"]["posts"] == 1 and s["x"]["without"]["posts"] == 1


def test_a_visual_for_his_own_words_goes_to_providers_that_dont_train_on_them(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    write_inbox(ctx.data_root, [{"id": "e2", "type": "card.edit", "card_id": card["id"],
                                 "text": "What I learned rebuilding our invoice bot."}], name="e2")
    inbox.ingest(ctx)
    _ask(ctx, card, ev_id="v6")
    draft.process_work(ctx)
    call = _calls(ctx, "visual")[0]
    assert call.personal and "What I learned rebuilding our invoice bot." in call.prompt


def test_a_visual_that_keeps_failing_says_so(make_ctx):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _set_handler(ctx, lambda req, data: {"kind": "list", "items": []})
    _ask(ctx, card, kind="list")
    for _ in range(3):
        draft.process_work(ctx)
    after = ctx.store.get("cards", card["id"])
    assert after["work"] is None and after.get("visual") is None
    assert "The visual failed three times; ask for another kind" in after["flags"]["notes"]
    assert after["status"] == "suggested"
