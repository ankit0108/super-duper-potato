from __future__ import annotations

import json

from conftest import write_inbox

from pbs import contracts as C
from pbs import export, inbox, studio, timeutil


def _save_event(card_id="crd_20260928_studio1", **kw):
    ev = {"id": f"ev_{card_id}", "type": "studio.save", "card_id": card_id, "platform": "linkedin",
          "format": "li_text", "title": "The demo took a week",
          "text": "The demo took a week.\n\nGetting it to work on a Tuesday took the rest of the quarter.",
          "hooks": ["Agents don't fail in demos.", ""], "hashtags": ["#AI", "AIAgents"],
          "first_comment": "Source: https://example.com/agents", "pillar": "industry",
          "sources": [{"title": "Agents in production", "url": "https://example.com/agents"},
                      {"title": "Not a link", "url": "javascript:alert(1)"}],
          "evidence": "Agents in production", "model": "gemini-flash-latest", "kit_version": "abc123"}
    ev.update(kw)
    return ev


def _blob(ctx, name="crd_20260928_studio1_1.jpg"):
    path = ctx.data_root / "inbox" / "blobs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8\xff\xe0 not really a jpeg")
    return f"inbox/blobs/{name}"


def test_the_studio_kit_carries_the_same_rules_and_style_as_the_drafter(make_ctx):
    ctx = make_ctx()
    kit = studio.kit(ctx)
    name = ctx.settings.display_name
    system = kit["system"]
    assert "{{" not in system and "}}" not in system
    assert f"This is the Studio: a chat with {name} directly" in system
    # The system rules come first, then the Studio's own instructions and both platforms' style guides.
    assert system.index("This is the Studio") > 0
    assert "LinkedIn style guide:" in system and "X style guide:" in system
    assert f"Rules learned from {name}'s edits" in system
    # The visual rules are the pipeline's own (one source of truth for what the desk can draw).
    assert "4 to 8 slides after the cover" in system and "  - image:" not in system
    assert "Kinds of post:" in system and "funny_take" in system
    assert kit["x_limit"] == ctx.settings.x_char_limit()
    assert set(kit["pillars"]) == {"linkedin", "x"} and "industry" in kit["pillars"]["linkedin"]
    # desk.json carries it, and it fits the contract the desk is generated from.
    assert export.build(ctx)["studio"]["version"] == kit["version"]
    C.StudioKit.model_validate(kit)


def test_a_studio_post_saved_to_the_board_becomes_a_card_with_its_pictures(make_ctx):
    ctx = make_ctx()
    path = _blob(ctx)
    visual = {"kind": "carousel", "title": "Shipping an AI agent", "subtitle": "The boring parts",
              "items": [{"title": "Write the questions first", "body": "Real questions, before any prompt."},
                        {"title": "Check every release", "body": "Run the list before each change."},
                        {"title": "Log every tool call", "body": "Trace a wrong answer in minutes."}],
              "caption": "", "alt_text": "A carousel", "photo": 0}
    write_inbox(ctx.data_root, [_save_event(images=[{"path": path, "width": 1200, "height": 900}], visual=visual)])
    stats = inbox.ingest(ctx)
    assert stats["applied"] == 1 and stats["rejected"] == 0
    card = ctx.store.get("cards", "crd_20260928_studio1")
    assert card["kind"] == "studio" and card["status"] == "suggested" and card["draft_state"] == "full"
    assert card["draft"]["text"].startswith("The demo took a week.")
    assert card["draft"]["first_comment"].startswith("Source:")
    assert card["hashtags"] == ["#AI", "#AIAgents"]
    assert [h["text"] for h in card["hooks"]] == ["Agents don't fail in demos."]
    assert [s["url"] for s in card["sources"]] == ["https://example.com/agents"]
    assert card["llm"] == {"provider": "studio", "model": "gemini-flash-latest"}
    # The picture moved out of inbox/ to the card's media folder, and sits behind the carousel cover.
    kept = "media/studio/crd_20260928_studio1/1.jpg"
    assert card["attachments"] == [{"path": kept, "content_type": "image/jpeg", "width": 1200, "height": 900}]
    assert (ctx.data_root / kept).exists() and not (ctx.data_root / path).exists()
    assert card["visual"]["image"]["path"] == kept and card["visual"]["image"]["provider"] == "your photo"
    assert len(card["visual"]["items"]) == 3
    # It's a card like any other: in desk.json (which is checked against the contract), and today's.
    shown = next(c for c in export.build(ctx)["cards"] if c["id"] == card["id"])
    assert shown["attachments"][0]["path"] == kept and shown["kind"] == "studio"
    assert card["delivered_at"][:10] == timeutil.now_iso()[:10]


def test_saving_twice_keeps_one_card(make_ctx):
    ctx = make_ctx()
    write_inbox(ctx.data_root, [_save_event()], name="a")
    inbox.ingest(ctx)
    write_inbox(ctx.data_root, [{**_save_event(), "id": "ev_again", "text": "Something else"}], name="b")
    stats = inbox.ingest(ctx)
    assert stats["rejected"] == 0
    cards = ctx.store.select("cards", "kind = 'studio'")
    assert len(cards) == 1 and cards[0]["draft"]["text"].startswith("The demo took a week.")


def test_pictures_must_come_from_the_inbox_and_ids_must_be_plain(make_ctx):
    ctx = make_ctx()
    (ctx.data_root / "db").mkdir(parents=True, exist_ok=True)
    write_inbox(ctx.data_root, [
        _save_event("crd_a", images=[{"path": "db/cards/2026-09.jsonl"}]),
        _save_event("crd_b", images=[{"path": "inbox/blobs/../../db/x.jpg"}]),
        _save_event("crd_c", images=[{"path": "inbox/blobs/never_uploaded.jpg"}]),
        _save_event("../escape"),
    ])
    stats = inbox.ingest(ctx)
    assert stats["applied"] == 0 and stats["rejected"] == 4
    errors = {r["id"]: r["error"] for r in ctx.store.select("processed_events", "status = 'rejected'")}
    assert "inbox/blobs" in errors["ev_crd_a"] and "inbox/blobs" in errors["ev_crd_b"]
    assert "hasn't arrived" in errors["ev_crd_c"]
    assert "pattern" in errors["ev_../escape"]
    assert not ctx.store.select("cards", "kind = 'studio'")


def test_a_studio_post_that_names_a_guard_term_is_blocked(make_ctx, monkeypatch):
    monkeypatch.setenv("PBS_BLOCKLIST", "Contoso")
    ctx = make_ctx()
    write_inbox(ctx.data_root, [_save_event(text="What we learned shipping agents at Contoso this quarter.")])
    inbox.ingest(ctx)
    card = ctx.store.get("cards", "crd_20260928_studio1")
    assert card["status"] == "blocked"


def test_a_studio_thread_and_a_bad_pillar(make_ctx):
    ctx = make_ctx()
    write_inbox(ctx.data_root, [_save_event(platform="x", format="x_thread", text="ignored",
                                            posts=["First post.", " ", "Second post."], pillar="nope",
                                            post_type="funny_take")])
    inbox.ingest(ctx)
    card = ctx.store.get("cards", "crd_20260928_studio1")
    assert card["format"] == "x_thread" and card["draft"] == {"text": "", "posts": ["First post.", "Second post."],
                                                              "first_comment": "Source: https://example.com/agents"}
    assert card["pillar"] in ctx.settings.pillars("x") and card["post_type"] == "funny_take"


def test_posting_a_studio_card_is_learned_from_like_any_other(make_ctx):
    ctx = make_ctx()
    write_inbox(ctx.data_root, [_save_event()], name="a")
    inbox.ingest(ctx)
    write_inbox(ctx.data_root, [{"id": "p1", "type": "card.posted", "card_id": "crd_20260928_studio1",
                                 "text": "The demo took a week. The rest took a quarter."}], name="b")
    stats = inbox.ingest(ctx)
    assert stats["applied"] == 1
    posts = ctx.store.select("posts", "card_id = ?", ("crd_20260928_studio1",))
    assert len(posts) == 1 and posts[0]["edit_ratio"] > 0
    assert json.dumps(ctx.store.get("cards", "crd_20260928_studio1")["status"]) == '"posted"'
