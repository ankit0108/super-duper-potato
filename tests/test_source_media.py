"""Pictures from the sources: found in feeds and article pages, prepared, described, attached, edited, learned."""

from __future__ import annotations

import datetime as dt
import io

import feedparser
import httpx
from conftest import fake_providers, write_inbox
from PIL import Image

from pbs import draft, images, inbox, prompting, source_media, timeutil
from pbs.context import Ctx
from pbs.demo.web import MockWeb, demo_figure
from pbs.scout.parsers import feed_entry_images


def _png(w=1200, h=800, color=(40, 90, 200)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), color).save(out, "PNG")
    return out.getvalue()


def _webp(w=1000, h=700) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (200, 60, 60)).save(out, "WEBP")
    return out.getvalue()


PAGE = """<!doctype html><html><head><base href="https://news.example.com/2026/">
<meta property="og:image" content="https://cdn.example.com/hero.jpg"><meta property="og:image:alt" content="A data centre">
</head><body><header><img src="/static/site-logo.png" alt="Example"></header><article>
<figure><img src="charts/growth.png" srcset="charts/growth-480.png 480w, charts/growth-1600.png 1600w" width="1600"
height="900"><figcaption>Chart: agent adoption by quarter (%)</figcaption></figure>
<p><img src="https://cdn.example.com/inline.png" alt="Diagram of the approval flow"></p>
<p><img src="https://cdn.example.com/no-alt.png"></p>
<img src="https://cdn.example.com/tiny.png" alt="share" width="40" height="40">
<img src="data:image/png;base64,AAAA" alt="lazy">
</article></body></html>"""


def test_feed_entries_keep_their_pictures():
    xml = """<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>t</title>
    <item><title>A story</title><link>https://example.com/a</link>
    <description><![CDATA[<p>Text <img src="https://example.com/fig1.png" alt="Figure 1: results"></p>
    <img src="https://example.com/icons/rss-icon.png">]]></description>
    <media:content url="https://example.com/hero.jpg" medium="image" width="1200" height="800"/>
    <media:thumbnail url="https://example.com/thumb.jpg"/>
    <enclosure url="https://example.com/encl.jpg" type="image/jpeg" length="1"/>
    <enclosure url="https://example.com/a.mp3" type="audio/mpeg" length="1"/>
    </item></channel></rss>"""
    entry = feedparser.parse(xml.encode()).entries[0]
    urls = [i["url"] for i in feed_entry_images(entry)]
    assert urls[0] == "https://example.com/hero.jpg"
    assert "https://example.com/encl.jpg" in urls and "https://example.com/a.mp3" not in urls
    assert not any("icon" in u for u in urls) and len(urls) <= 4
    from pbs.scout.parsers import parse

    items = parse({"id": "s", "kind": "rss", "name": "Example"}, xml.encode())
    assert items[0]["signals"]["images"][0]["url"] == "https://example.com/hero.jpg"


def test_article_pages_give_their_figures_with_captions_and_leave_furniture_out():
    found = source_media.page_images(PAGE, "https://news.example.com/2026/story")
    by_url = {f["url"]: f for f in found}
    assert found[0] == {"url": "https://cdn.example.com/hero.jpg", "alt": "A data centre", "caption": None, "via": "og"}
    fig = by_url["https://news.example.com/2026/charts/growth-1600.png"]  # largest in srcset, relative to <base>
    assert fig["caption"] == "Chart: agent adoption by quarter (%)" and fig["via"] == "figure"
    assert by_url["https://cdn.example.com/inline.png"]["alt"] == "Diagram of the approval flow"
    assert "https://cdn.example.com/no-alt.png" not in by_url  # in the article with no words about it
    assert not any("logo" in u or "tiny" in u or u.startswith("data:") for u in by_url)


def test_which_pages_are_read():
    assert source_media.page_url("https://news.google.com/rss/articles/abc") is None
    assert source_media.page_url("https://arxiv.org/abs/2609.01234v2") == "https://arxiv.org/html/2609.01234v2"
    assert source_media.page_url("https://www.youtube.com/watch?v=x") is None
    assert source_media.page_url("https://example.com/post") == "https://example.com/post"
    assert source_media.junk("https://example.com/silicon-valley.jpg") is False
    assert source_media.junk("https://example.com/img/author-avatar.jpg") is True
    assert source_media.junk("https://example.com/a.svg") is True


def test_pictures_are_prepared_to_post():
    big = source_media.prepare(_png(3200, 2000), 1600)
    assert big and big["content_type"] == "image/png" and (big["width"], big["height"]) == (1600, 1000)
    webp = source_media.prepare(_webp(), 1600)
    assert webp and webp["content_type"] == "image/jpeg" and images.sniff(webp["data"]) == "image/jpeg"
    assert source_media.prepare(_png(300, 200), 1600) is None  # too small
    assert source_media.prepare(_png(1600, 300), 1600) is None  # a strip, not a picture
    assert source_media.prepare(b"<html>not an image</html>", 1600) is None


def _card(ctx, card_id="crd_20260928_pics1", fmt="li_text", platform="linkedin", urls=None, **kw):
    now = timeutil.now_iso()
    card = {"id": card_id, "platform": platform, "mode": "external", "pillar": "industry", "format": fmt,
            "title": "Why agent benchmark numbers differ in production", "status": "suggested",
            "draft": {"text": "Draft.", "posts": [], "first_comment": "Source: https://example.dev/blog/evals-production"},
            "sources": [{"url": u, "title": "Evals in production", "publisher": "example.dev"}
                        for u in (urls or ["https://example.dev/blog/evals-production"])],
            "hooks": [], "hashtags": [], "created_at": now, "updated_at": now, "revision": 1, **kw}
    ctx.store.upsert("cards", card)
    return card


def test_a_new_draft_gets_the_pictures_in_its_sources_once(make_ctx):
    ctx = make_ctx()
    _card(ctx)
    _card(ctx, "crd_20260928_reply1", fmt="x_reply", platform="x")
    stats = source_media.collect(ctx)
    assert stats["cards"] == 1 and stats["attached"] == 2 and stats["vision"] == 1
    card = ctx.store.get("cards", "crd_20260928_pics1")
    kinds = [a["kind"] for a in card["attachments"]]
    assert kinds == ["chart", "diagram"]  # the site logo was left out; charts first
    first = card["attachments"][0]
    assert first["origin"] == "source" and first["publisher"] == "example.dev" and first["alt"]
    assert first["path"] == "media/sources/crd_20260928_pics1/1.png" and (ctx.data_root / first["path"]).exists()
    assert card["draft"]["first_comment"] == "Source: https://example.dev/blog/evals-production\nFigures: example.dev"
    assert card["draft"]["media_credit"] == "Figures: example.dev"
    assert ctx.store.get("cards", "crd_20260928_reply1")["source_media"] == []  # a reply carries no pictures
    # Looked at once: a second run neither fetches nor changes anything.
    assert source_media.collect(ctx)["cards"] == 0


def _pictures_transport(n=7):
    """A page with n distinct figures (and one repeated), each a real PNG."""
    figs = "".join(f'<figure><img src="https://cdn.example.com/fig{i}.png"><figcaption>Chart {i}: results (%)'
                   f"</figcaption></figure>" for i in range(n))
    page = f"<html><body><article>{figs}<figure><img src='https://cdn.example.com/again.png'>" \
           "<figcaption>Same chart again</figcaption></figure></article></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("again.png"):
            return httpx.Response(200, content=_png(color=(0, 0, 0)))
        if "cdn.example.com/fig" in url:
            i = int(url.rsplit("fig", 1)[1].split(".")[0])
            return httpx.Response(200, content=_png(color=(i * 30 % 255, 10, 10)) if i else _png(color=(0, 0, 0)))
        if "example.org/story" in url:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=page)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_at_most_four_go_with_the_post_two_more_wait_and_duplicates_are_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    ctx = Ctx.create(tmp_path / "data", transport=_pictures_transport(), llm_providers=fake_providers(),
                     sleep=lambda s: None)
    _card(ctx, urls=["https://example.org/story"])
    source_media.collect(ctx)
    card = ctx.store.get("cards", "crd_20260928_pics1")
    assert len(card["attachments"]) == 4 and len(card["source_media"]) == 6
    assert len({a["path"] for a in card["source_media"]}) == 6
    # fig0 and again.png are the same picture: only one of them is kept.
    assert sum(1 for a in card["source_media"] if a.get("caption") in ("Chart 0: results (%)", "Same chart again")) == 1


def test_without_the_vision_model_captions_say_what_a_picture_is(make_ctx):
    ctx = make_ctx()
    ctx.settings.media.vision_per_day = 0
    _card(ctx)
    stats = source_media.collect(ctx)
    card = ctx.store.get("cards", "crd_20260928_pics1")
    assert stats["vision"] == 0
    assert [a["kind"] for a in card["attachments"]] == ["chart", "diagram"]
    assert card["attachments"][0]["alt"].startswith("Benchmark chart")


def test_the_credit_line_names_who_the_pictures_belong_to():
    att = [{"origin": "source", "publisher": "Epoch AI", "kind": "chart"}]
    assert source_media.credit_line(att) == "Chart: Epoch AI"
    att.append({"origin": "source", "publisher": "The Verge", "kind": "photo"})
    assert source_media.credit_line(att) == "Images: Epoch AI, The Verge"
    assert source_media.credit_line([{"origin": "upload", "kind": "photo"}]) is None
    card = {"format": "li_text", "attachments": att[:1],
            "draft": {"first_comment": "Source: https://x.test\nChart: Old", "media_credit": "Chart: Old"}}
    source_media.apply_credit(card)
    assert card["draft"]["first_comment"] == "Source: https://x.test\nChart: Epoch AI"
    card["attachments"] = []
    source_media.apply_credit(card)
    assert card["draft"]["first_comment"] == "Source: https://x.test" and card["draft"]["media_credit"] is None
    # A rewrite brings a new draft without the line: it goes back on.
    card["attachments"] = att[:1]
    card["draft"] = {"first_comment": "Source: https://x.test"}
    source_media.apply_credit(card)
    assert card["draft"]["first_comment"].endswith("\nChart: Epoch AI")
    reply = {"format": "x_reply", "attachments": att, "draft": {"first_comment": ""}}
    source_media.apply_credit(reply)
    assert reply["draft"]["first_comment"] == ""


def test_a_redraft_keeps_the_pictures_credit(make_ctx):
    ctx = make_ctx()
    _card(ctx)
    source_media.collect(ctx)
    card = ctx.store.get("cards", "crd_20260928_pics1")
    card["draft_state"] = "full"
    draft.rewrite(ctx, card, {"kind": "rewrite", "instruction": "shorter"})
    card = ctx.store.get("cards", "crd_20260928_pics1")
    assert card["draft"]["first_comment"].endswith("Figures: example.dev")


def _media_event(items, card_id="crd_20260928_pics1", ev_id="m1"):
    return {"id": ev_id, "type": "card.media", "card_id": card_id, "items": items}


def test_he_removes_moves_adds_back_and_uploads_pictures(make_ctx):
    ctx = make_ctx()
    _card(ctx)
    source_media.collect(ctx)
    card = ctx.store.get("cards", "crd_20260928_pics1")
    chart, diagram = (a["path"] for a in card["attachments"])
    # Remove the chart, keep the diagram with his alt text.
    write_inbox(ctx.data_root, [_media_event([{"path": diagram, "alt": "My words"}])], name="a")
    assert inbox.ingest(ctx)["applied"] == 1
    card = ctx.store.get("cards", "crd_20260928_pics1")
    assert [a["path"] for a in card["attachments"]] == [diagram] and card["attachments"][0]["alt"] == "My words"
    assert card["draft"]["first_comment"].endswith("\nDiagram: example.dev")
    assert {a["path"] for a in card["source_media"]} == {chart, diagram}
    # Upload one, add the chart back first.
    blob = ctx.data_root / "inbox" / "blobs" / "crd_20260928_pics1_up.jpg"
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(_png(900, 600))
    write_inbox(ctx.data_root, [_media_event([{"path": chart}, {"path": diagram},
                                              {"path": "inbox/blobs/crd_20260928_pics1_up.jpg"}], ev_id="m2")], name="b")
    assert inbox.ingest(ctx)["applied"] == 1
    card = ctx.store.get("cards", "crd_20260928_pics1")
    up = card["attachments"][2]
    assert [a["path"] for a in card["attachments"][:2]] == [chart, diagram]
    assert up["origin"] == "upload" and up["path"] == "media/uploads/crd_20260928_pics1/1.jpg"
    assert (up["width"], up["height"]) == (900, 600) and not blob.exists()
    assert card["draft"]["first_comment"].endswith("\nFigures: example.dev")  # his upload needs no credit
    types = [i["type"] for i in ctx.store.select("interactions", "type LIKE 'media_%'", order="at")]
    assert types.count("media_removed") == 1 and types.count("media_added") == 1 and "media_uploaded" in types
    # A picture that isn't the card's is refused; so is a change to a posted card.
    write_inbox(ctx.data_root, [_media_event([{"path": "media/sources/other/1.png"}], ev_id="m3")], name="c")
    assert inbox.ingest(ctx)["rejected"] == 1
    card["status"] = "posted"
    ctx.store.upsert("cards", card)
    write_inbox(ctx.data_root, [_media_event([], ev_id="m4")], name="d")
    assert inbox.ingest(ctx)["rejected"] == 1


def test_a_kind_he_keeps_removing_stops_being_attached(make_ctx):
    ctx = make_ctx()
    for _ in range(8):
        draft.log_interaction(ctx, "media_removed", None, kind="diagram", card_id="crd_x")
    draft.log_interaction(ctx, "media_posted", None, kinds=["chart"], card_id="crd_y")
    prefs = source_media.preferences(ctx)
    assert prefs["diagram"]["dropped"] and prefs["diagram"]["rate"] == 0.0 and not prefs["chart"]["dropped"]
    _card(ctx)
    source_media.collect(ctx)
    card = ctx.store.get("cards", "crd_20260928_pics1")
    assert [a["kind"] for a in card["attachments"]] == ["chart"]
    assert [a["kind"] for a in card["source_media"]] == ["chart", "diagram"]  # still one tap away
    assert source_media.summary(ctx)["diagram"]["no_longer_attached"] is True


def test_posting_records_which_pictures_went_out(make_ctx):
    ctx = make_ctx()
    _card(ctx)
    source_media.collect(ctx)
    write_inbox(ctx.data_root, [{"id": "p1", "type": "card.posted", "card_id": "crd_20260928_pics1",
                                 "text": "Draft.", "post_url": "https://www.linkedin.com/feed/update/1"}])
    inbox.ingest(ctx)
    posted = ctx.store.select("interactions", "type = 'media_posted'")
    assert posted and posted[0]["data"]["kinds"] == ["chart", "diagram"]


def test_pictures_nothing_needs_are_pruned(make_ctx):
    ctx = make_ctx()
    _card(ctx)
    source_media.collect(ctx)
    folder = ctx.data_root / "media" / "sources" / "crd_20260928_pics1"
    (folder / "9.png").write_bytes(b"x")  # on no card
    gone = ctx.data_root / "media" / "sources" / "crd_gone"
    gone.mkdir(parents=True)
    (gone / "1.png").write_bytes(b"x")
    assert images.prune_media(ctx) == 2
    assert sorted(p.name for p in folder.iterdir()) == ["1.png", "2.png"] and not gone.exists()
    card = ctx.store.get("cards", "crd_20260928_pics1")
    card.update(status="skipped", status_changed_at=timeutil.iso(timeutil.now() - dt.timedelta(days=15)))
    ctx.store.upsert("cards", card)
    assert images.prune_media(ctx) == 2 and not folder.exists()


def test_the_vision_prompt_fits_the_model_and_the_demo_pictures_are_real(make_ctx):
    pictures = [{"index": i, "source": "A long article title " * 4, "publisher": "Publisher", "caption": "c" * 300,
                 "page_alt": "a" * 300, "found_in": "figure"} for i in range(6)]
    prompt = prompting.render("media_vision", input_json={"story": "t" * 200, "pictures": pictures})
    assert len(prompt) / 3 < 5000
    data, ctype = demo_figure("https://img.demo.example/chart/x.png")
    assert ctype == "image/png" and source_media.prepare(data, 1600)
    assert MockWeb().handler(httpx.Request("GET", "https://example.dev/blog/evals-production")).status_code == 200

