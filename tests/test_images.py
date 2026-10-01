"""AI images: an illustration for a post, or a background behind a carousel cover, big number or quote card."""

from __future__ import annotations

import json

import pytest
from conftest import write_inbox

from pbs import deliver, doctor, draft, export, images, inbox, learn, timeutil
from pbs.demo.web import MockWeb

CF = "api.cloudflare.com"


@pytest.fixture
def cloudflare(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
    for var in ("GEMINI_IMAGE_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def _card(ctx, platform="linkedin"):
    return ctx.store.select("cards", "platform = ? AND status = 'suggested'", (platform,), order="rank")[0]


def _ask(ctx, card, kind="image", ai_background=False, ev_id="v1"):
    write_inbox(ctx.data_root, [{"id": ev_id, "type": "card.visual", "card_id": card["id"], "kind": kind, "note": "",
                                 "ai_background": ai_background}], name=ev_id)
    return inbox.ingest(ctx)


def _rows(ctx):
    return ctx.store.select("images", order="created_at")


def test_an_ai_illustration_is_made_by_cloudflare_and_kept_with_the_visual(make_ctx, cloudflare, web):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    assert _ask(ctx, card)["rejected"] == 0
    assert draft.process_work(ctx)["done"] == 1
    v = ctx.store.get("cards", card["id"])["visual"]
    assert v["kind"] == "image" and v["items"] == []
    img = v["image"]
    assert img["provider"] == "cloudflare" and img["model"] == "@cf/black-forest-labs/flux-2-klein-4b"
    assert img["path"].startswith(f"media/ai/{card['id']}/") and img["content_type"] == "image/png"
    assert (img["width"], img["height"]) == (320, 400)  # read from the file, not assumed
    data = (ctx.data_root / img["path"]).read_bytes()
    assert images.sniff(data) == "image/png"
    assert v["alt_text"].startswith("AI-generated illustration: ")
    calls = [u for u in web.requests if CF in u]
    assert calls == ["https://api.cloudflare.com/client/v4/accounts/acct123/ai/run/@cf/black-forest-labs/flux-2-klein-4b"]
    assert [(r["provider"], r["status"], r["purpose"]) for r in _rows(ctx)] == [("cloudflare", "ok", "image")]
    made = ctx.store.select("interactions", "type = 'visual_created'")[0]["data"]
    assert made["image"] == "cloudflare" and made["background"] is False


def test_the_image_prompt_asks_for_no_words_and_keeps_blocklisted_names_out(make_ctx, cloudflare, monkeypatch):
    monkeypatch.setenv("PBS_BLOCKLIST", "Contoso")
    sent: list[bytes] = []
    web = MockWeb()
    original = web.handler

    def spy(request):
        if CF in str(request.url):
            sent.append(request.content)
        return original(request)

    web.handler = spy  # type: ignore[method-assign]
    ctx = make_ctx()
    ctx.transport = web.transport()
    res = images.generate(ctx, images.styled_prompt(ctx, "Contoso's warehouse at dawn", background=False,
                                                    accent="#4F46E5"), 1024, 1280, card_id="crd_x")
    assert res.path.startswith("media/ai/crd_x/")
    body = sent[0].decode("utf-8", "replace")
    assert "No text, letters, numbers" in body and "Contoso" not in body and "[redacted]" in body
    assert 'name="width"\r\n\r\n1024' in body and 'name="height"\r\n\r\n1280' in body


def test_a_background_goes_behind_a_carousel_and_its_words_are_still_drawn_and_checked(make_ctx, cloudflare):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _ask(ctx, card, kind="carousel", ai_background=True)
    assert ctx.store.get("cards", card["id"])["work"]["ai_background"] is True
    draft.process_work(ctx)
    v = ctx.store.get("cards", card["id"])["visual"]
    assert v["kind"] == "carousel" and len(v["items"]) >= 3 and v["image"]["provider"] == "cloudflare"
    assert v["alt_text"].endswith("(Background: an AI-generated image.)")
    assert _rows(ctx)[0]["purpose"] == "background"


def test_without_an_image_service_the_desk_is_told_and_requests_are_refused(make_ctx, monkeypatch):
    for var in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "GEMINI_IMAGE_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    assert _ask(ctx, card)["rejected"] == 1
    assert _ask(ctx, card, kind="stat", ai_background=True, ev_id="v2")["rejected"] == 1
    row = ctx.store.get("processed_events", "v1")
    assert "CLOUDFLARE_ACCOUNT_ID" in row["error"]
    assert images.status(ctx) == {"available": False, "providers": [], "used_today": 0, "daily_limit": 20,
                                  "last_error": None}
    assert _ask(ctx, card, kind="flow", ev_id="v3")["rejected"] == 0  # drawn visuals need no image service


def test_when_cloudflare_fails_the_next_service_answers(make_ctx, cloudflare, web, monkeypatch):
    monkeypatch.setenv("GEMINI_IMAGE_API_KEY", "paid-key")
    web.world[CF] = (500, "application/json", json.dumps({"success": False, "errors": [{"code": 3043, "message": "Internal"}]}))
    ctx = make_ctx()
    res = images.generate(ctx, "a calm shape", 1280, 720, card_id="crd_y")
    assert res.provider == "gemini_image" and res.model == "gemini-2.5-flash-image" and (res.width, res.height) == (400, 225)
    rows = [(r["provider"], r["status"]) for r in _rows(ctx)]
    # Cloudflare: both models, each tried twice (one retry for a server error), then Gemini.
    assert rows[-1] == ("gemini_image", "ok") and rows.count(("cloudflare", "failed")) == 2
    assert images.status(ctx)["providers"] == ["cloudflare", "gemini_image"]


def test_a_used_up_allowance_is_skipped_for_the_rest_of_the_day(make_ctx, cloudflare, web):
    web.world[CF] = (429, "application/json", json.dumps({"success": False, "errors": [
        {"code": 4006, "message": "you have used up your daily free allocation of 10,000 neurons"}]}))
    ctx = make_ctx()
    with pytest.raises(images.ImagesUnavailable, match="daily allowance used up"):
        images.generate(ctx, "x", 1024, 1280)
    asked = len([u for u in web.requests if CF in u])
    with pytest.raises(images.ImagesUnavailable):
        images.generate(ctx, "x", 1024, 1280)
    assert len([u for u in web.requests if CF in u]) == asked  # not asked again today
    assert images.status(ctx)["available"] is False
    assert images.status(ctx)["last_error"] == "cloudflare: daily allowance used up (HTTP 429 4006)"


def test_gemini_without_billing_says_so(make_ctx, web, monkeypatch):
    for var in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "XAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GEMINI_IMAGE_API_KEY", "free-key")
    web.world["flash-image"] = (429, "application/json", json.dumps({"error": {
        "code": 429, "status": "RESOURCE_EXHAUSTED",
        "message": "Quota exceeded for metric: generate_content_free_tier_requests, limit: 0"}}))
    ctx = make_ctx()
    with pytest.raises(images.ImagesUnavailable, match="no_free_tier"):
        images.generate(ctx, "x", 1024, 1280)


def test_xai_images(make_ctx, web, monkeypatch):
    for var in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "GEMINI_IMAGE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-key")
    ctx = make_ctx()
    res = images.generate(ctx, "x", 1024, 1280)
    assert res.provider == "xai" and res.model == "grok-imagine-image"


def test_the_daily_limit_stops_images(make_ctx, cloudflare):
    ctx = make_ctx()
    ctx.store.set_setting("overrides", {"images": {"daily_limit": 1}})
    ctx.reload_settings()
    images.generate(ctx, "x", 1024, 1280)
    with pytest.raises(images.ImagesUnavailable, match="Today's limit of 1 AI images"):
        images.generate(ctx, "x", 1024, 1280)


def test_a_background_that_fails_leaves_the_visual_drawn_without_it(make_ctx, cloudflare, web):
    web.world[CF] = (503, "application/json", json.dumps({"success": False, "errors": [{"code": 3040, "message": "busy"}]}))
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _ask(ctx, card, kind="quote", ai_background=True)
    assert draft.process_work(ctx)["done"] == 1
    after = ctx.store.get("cards", card["id"])
    assert after["visual"]["kind"] == "quote" and after["visual"].get("image") is None and after["work"] is None
    assert any("drawn without it" in n for n in after["flags"]["notes"])


def test_an_illustration_that_keeps_failing_is_retried_then_explained(make_ctx, cloudflare, web):
    web.world[CF] = (502, "application/json", "{}")
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _ask(ctx, card)
    draft.process_work(ctx)
    assert ctx.store.get("cards", card["id"])["work"]["attempts"] == 1  # still queued for the next run
    draft.process_work(ctx)
    draft.process_work(ctx)
    after = ctx.store.get("cards", card["id"])
    assert after["work"] is None and after.get("visual") is None
    assert "The visual failed three times; ask for another kind" in after["flags"]["notes"]


def test_his_edits_to_the_words_keep_the_same_picture(make_ctx, cloudflare):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _ask(ctx, card)
    draft.process_work(ctx)
    base = ctx.store.get("cards", card["id"])["visual"]
    write_inbox(ctx.data_root, [{"id": "e1", "type": "card.edit", "card_id": card["id"], "text": card["draft"]["text"],
                                 "visual": {"kind": "image", "title": "My headline", "items": [], "alt_text": "A picture"}}],
                name="e1")
    assert inbox.ingest(ctx)["rejected"] == 0
    working = ctx.store.get("cards", card["id"])["working"]["visual"]
    assert working["title"] == "My headline" and working["image"] == base["image"]


def test_the_desk_gets_image_status_and_the_visual_with_its_picture(make_ctx, cloudflare):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _ask(ctx, card)
    draft.process_work(ctx)
    export.write(ctx)
    desk = json.loads((ctx.data_root / "desk" / "desk.json").read_text())
    assert desk["images"] == {"available": True, "providers": ["cloudflare"], "used_today": 1, "daily_limit": 20}
    shown = next(c for c in desk["cards"] if c["id"] == card["id"])
    assert shown["visual"]["image"]["path"].startswith("media/ai/")


def test_old_and_replaced_images_are_pruned(make_ctx, cloudflare):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _ask(ctx, card)
    draft.process_work(ctx)
    first = ctx.store.get("cards", card["id"])["visual"]["image"]["path"]
    timeutil.freeze("2026-09-28T00:00:00Z")
    _ask(ctx, card, ev_id="v2")
    draft.process_work(ctx)
    second = ctx.store.get("cards", card["id"])["visual"]["image"]["path"]
    orphan = ctx.data_root / "media" / "ai" / "crd_gone" / "20260901T000000Z-abc.png"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(images.demo_png("x", 4, 4))
    screenshot = ctx.data_root / "media" / "metrics" / "2026-W39" / "linkedin-week.png"
    screenshot.parent.mkdir(parents=True)
    screenshot.write_bytes(images.demo_png("y", 4, 4))
    timeutil.freeze("2026-09-30T00:00:00Z")
    assert learn.prune(ctx)["media"] == 2  # the replaced picture and the card that no longer exists
    assert not (ctx.data_root / first).exists() and (ctx.data_root / second).exists()
    assert not orphan.parent.exists()
    assert screenshot.exists()  # analytics screenshots live beside the AI images and are never pruned here


def test_the_doctor_makes_a_test_image(make_ctx, cloudflare, monkeypatch):
    ctx = make_ctx()
    report = doctor.run_doctor(ctx, probe_llm=True, probe_sources=False)
    check = next(c for c in report["checks"] if c["name"].startswith("Images: cloudflare"))
    assert check["status"] == "ok" and "test image" in check["detail"]
    for var in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
        monkeypatch.delenv(var)
    report = doctor.run_doctor(make_ctx(), probe_llm=True, probe_sources=False)
    assert next(c for c in report["checks"] if c["name"] == "AI images")["status"] == "skip"


def test_image_headers_give_the_real_size():
    png = images.demo_png("x", 30, 20)
    assert images.dimensions(png) == (30, 20)
    jpeg = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xc0\x00\x11\x08\x05\x00\x04\x00\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xd9")
    assert images.sniff(jpeg) == "image/jpeg" and images.dimensions(jpeg) == (1024, 1280)
    assert images.sniff(b"<html>") is None


def test_let_it_choose_with_a_background_picks_a_kind_that_can_carry_one(make_ctx, cloudflare):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _ask(ctx, card, kind="auto", ai_background=True)
    draft.process_work(ctx)
    prompt = next(c for p in ctx.llm._providers.values() for c in p.calls if c.task == "visual").prompt
    assert "A background picture was asked for, so pick carousel, stat or quote." in prompt
    assert "- flow:" not in prompt and "- carousel:" in prompt and '"image_prompt"' in prompt
    assert ctx.store.get("cards", card["id"])["visual"]["image"]


def test_a_background_on_a_kind_that_cant_carry_one_says_so(make_ctx, cloudflare):
    ctx = make_ctx()
    deliver.morning_delivery(ctx)
    card = _card(ctx)
    _ask(ctx, card, kind="flow", ai_background=True)
    draft.process_work(ctx)
    after = ctx.store.get("cards", card["id"])
    assert after["visual"]["kind"] == "flow" and after["visual"].get("image") is None
    assert any("drawn without one" in n for n in after["flags"]["notes"])
    assert not _rows(ctx)  # no image was made for nothing
