"""Analytics exports (LinkedIn's .xlsx, X's .csv): read exactly, matched to posts, and reviewed by the best model."""

from __future__ import annotations

import datetime as dt

import openpyxl
import pytest
from conftest import fake_providers, write_inbox

from pbs import analytics_files, export, inbox, learn, metrics, performance, tick, timeutil
from pbs.deliver import morning_delivery
from pbs.llm.fake import FakeProvider

LI = "https://www.linkedin.com/feed/update/urn:li:activity:{}/"


def linkedin_export(path, posts, *, followers=1234):
    """A content export laid out like LinkedIn's: overall numbers, a daily series, top posts in two tables side
    by side (by engagements and by impressions), followers and demographics."""
    book = openpyxl.Workbook()
    disc = book.active
    disc.title = "DISCOVERY"
    disc.append(["Overall Performance", "9/1/2026 - 9/27/2026"])
    disc.append(["Impressions", 18234])
    disc.append(["Members reached", 7012])
    eng = book.create_sheet("ENGAGEMENT")
    eng.append(["Date", "Impressions", "Engagements"])
    for i in range(14):
        eng.append([f"9/{i + 10}/2026", 500 + 40 * i, 12 + i])
    top = book.create_sheet("TOP POSTS")
    top.append(["Maximum of 50 posts available to include in this list"])
    top.append([])
    top.append(["Post URL", "Post publish date", "Engagements", None, "Post URL", "Post publish date", "Impressions"])
    by_eng = sorted(posts, key=lambda p: -p[2])
    by_imp = sorted(posts, key=lambda p: -p[3])
    for a, b in zip(by_eng, by_imp, strict=True):
        top.append([LI.format(a[0]), a[1], a[2], None, LI.format(b[0]), b[1], b[3]])
    fol = book.create_sheet("FOLLOWERS")
    fol.append(["Total followers on 9/27/2026:", followers])
    fol.append([])
    fol.append(["Date", "New followers"])
    fol.append(["9/26/2026", 4])
    fol.append(["9/27/2026", 7])
    dem = book.create_sheet("DEMOGRAPHICS")
    dem.append(["Top Demographics", "Value", "Percentage"])
    dem.append(["Job titles", "Software Engineer", 0.21])
    dem.append(["Locations", "Melbourne", "< 1%"])
    book.save(path)
    return path


def linkedin_post_export(path, activity, impressions=4321):
    """LinkedIn's export of one post's analytics: label and value pairs."""
    book = openpyxl.Workbook()
    sh = book.active
    sh.title = "PERFORMANCE"
    for row in (["Post URL", LI.format(activity)], ["Post Date", "9/22/2026"], ["Post Publish Time", "9:01 AM"],
                ["Impressions", impressions], ["Members reached", 2800], ["Profile viewers from this post", 9],
                ["Followers gained from this post", 3], ["Reactions", 61], ["Comments", 14], ["Reposts", 2],
                ["Saves", 5], ["Sends on LinkedIn", 1]):
        sh.append(row)
    book.save(path)
    return path


X_NEW = ("Post id,Date,Post text,Post Link,Impressions,Likes,Engagements,Bookmarks,Shares,New follows,Replies,"
         "Reposts,Profile visits,Detail Expands,URL Clicks,Hashtag Clicks,Permalink Clicks\n"
         '1971000000000000001,"Fri, Sep 25, 2026","Agents that say done when they are not",'
         "https://x.com/ankit/status/1971000000000000001,2400,30,61,4,1,2,6,3,5,11,0,0,1\n"
         '1971000000000000002,"Wed, Sep 23, 2026","Hot take: your AI bill is a design smell",'
         "https://x.com/ankit/status/1971000000000000002,1.1K,9,20,0,0,0,2,1,1,4,0,0,0\n")

X_OLD = ("Tweet id,Tweet permalink,Tweet text,time,impressions,engagements,engagement rate,retweets,replies,likes,"
         "user profile clicks,url clicks,hashtag clicks,detail expands,permalink clicks,app opens,app installs,"
         "follows,email tweet,dial phone,media views,media engagements\n"
         "1971000000000000003,https://twitter.com/ankit/status/1971000000000000003,Regex is a love language,"
         "2026-09-20 08:15 +0000,900,25,0.0278,2,3,15,1,0,0,4,0,0,0,1,0,0,0,0\n")


def test_reads_linkedin_content_export(tmp_path):
    path = linkedin_export(tmp_path / "Content_2026-09-01_2026-09-27.xlsx", [
        (7370000000000000001, "9/22/2026", 80, 4100), (7370000000000000002, "9/15/2026", 30, 5200)])
    parsed = analytics_files.parse(path)
    assert parsed.platform == "linkedin"
    posts = {analytics_files.post_key(p.url): p for p in parsed.posts}
    assert len(posts) == 2  # one row per post, the two tables merged
    first = posts["7370000000000000001"]
    assert first.values == {"engagements": 80, "impressions": 4100} and first.date == "2026-09-22"
    assert posts["7370000000000000002"].values == {"engagements": 30, "impressions": 5200}
    assert parsed.totals == {"impressions": 18234, "members_reached": 7012}
    assert parsed.period == "9/1/2026 - 9/27/2026"
    assert len(parsed.days) == 14 + 2 and parsed.days["2026-09-27"] == {"followers_gained": 7}
    assert parsed.followers == ("2026-09-27", 1234)
    assert parsed.audience[0] == {"category": "Job titles", "value": "Software Engineer", "share": 21.0}


def test_reads_a_single_post_export(tmp_path):
    parsed = analytics_files.parse(linkedin_post_export(tmp_path / "post.xlsx", 7370000000000000009))
    (post,) = parsed.posts
    assert post.platform == "linkedin" and post.date == "2026-09-22"
    assert post.values["impressions"] == 4321 and post.values["saves"] == 5 and post.values["sends"] == 1
    assert post.values["followers_gained"] == 3 and post.values["profile_views"] == 9


@pytest.mark.parametrize("body,count", [(X_NEW, 2), (X_OLD, 1)])
def test_reads_x_exports(tmp_path, body, count):
    path = tmp_path / "account_analytics_content.csv"
    path.write_text(body, encoding="utf-8")
    parsed = analytics_files.parse(path)
    assert parsed.platform == "x" and len(parsed.posts) == count
    p = parsed.posts[-1] if count == 1 else parsed.posts[1]
    assert p.values["impressions"] in (900, 1100)
    assert "link_clicks" not in p.values or p.values["link_clicks"] == 0  # "Permalink Clicks" isn't a link click
    assert p.text and p.date


def test_reads_dates_and_numbers_in_their_usual_shapes():
    assert analytics_files.date("Fri, Sep 25, 2026") == "2026-09-25"
    assert analytics_files.date("2026-09-20 08:15 +0000") == "2026-09-20"
    assert analytics_files.date(dt.datetime(2026, 9, 1, 10)) == "2026-09-01"
    assert analytics_files.number("1.2K") == 1200 and analytics_files.number("3,456") == 3456
    assert analytics_files.number("12%") is None and analytics_files.number("-") is None
    assert analytics_files.post_key("https://www.linkedin.com/posts/ankit_agents-activity-7370000000000000001-AbCd") \
        == "7370000000000000001"
    assert analytics_files.column("Impressions (total)") == "impressions"
    assert analytics_files.column("Permalink clicks") is None


def _upload(ctx, name, upload_id="upl_f1"):
    write_inbox(ctx.data_root, [{"id": f"u_{upload_id}", "type": "metrics.upload", "upload_id": upload_id,
                                 "paths": [f"inbox/blobs/{name}"], "week": "2026-W40"}], name=upload_id)
    inbox.ingest(ctx)
    return metrics.process_uploads(ctx)


def test_export_rows_match_posts_and_the_rest_are_history(make_ctx):
    ctx = make_ctx()
    morning_delivery(ctx)
    card = ctx.store.select("cards", "platform = 'linkedin' AND status = 'suggested'", order="rank")[0]
    by_link = learn.record_post(ctx, card, text="Agents need approval steps.", posts=None,
                                post_url="https://www.linkedin.com/posts/ankit_agents-activity-7370000000000000001-AbCd",
                                posted_at="2026-09-22T00:30:00Z", editing_seconds=None, hook_index=None)
    blobs = ctx.data_root / "inbox" / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    linkedin_export(blobs / "upl_f1_1.xlsx", [
        (7370000000000000001, "9/22/2026", 80, 4100), (7370000000000000002, "8/15/2026", 30, 5200)])
    stats = _upload(ctx, "upl_f1_1.xlsx")
    assert stats["metrics"] == 2 and stats["needs_review"] == 0
    rows = {m["status"]: m for m in ctx.store.select("metrics")}
    assert rows["confirmed"]["post_id"] == by_link["id"] and rows["confirmed"]["impressions"] == 4100
    assert rows["confirmed"]["source"] == "file" and rows["confirmed"]["engagements"] == 80
    assert rows["history"]["post_id"] is None and rows["history"]["impressions"] == 5200
    assert ctx.store.get("account_stats", "acs_linkedin_2026-09-27")["followers"] == 1234
    assert "2026-09-27" in ctx.store.get_setting(metrics.DAYS_KEY)["linkedin"]
    upload = ctx.store.get("metric_uploads", "upl_f1")
    assert upload["status"] == "processed" and upload["results"]["files"][0]["history"] == 1
    assert (ctx.data_root / "media" / "metrics" / "2026-W40" / "upl_f1_1.xlsx").exists()
    assert "analysis" in ctx.hints

    # The same export again (a re-upload): the same rows, updated, not doubled.
    linkedin_export(blobs / "upl_f2_1.xlsx", [
        (7370000000000000001, "9/22/2026", 95, 4600), (7370000000000000002, "8/15/2026", 30, 5200)])
    _upload(ctx, "upl_f2_1.xlsx", "upl_f2")
    assert ctx.store.count("metrics") == 2
    assert ctx.store.get("metrics", rows["confirmed"]["id"])["impressions"] == 4600

    # History rows stay out of the learner's rewards and the desk's metrics list.
    state = export.build(ctx)
    assert all(m["status"] != "history" for m in state["metrics"])
    assert next(p for p in state["posts"] if p["id"] == by_link["id"])["latest_metrics"]["impressions"] == 4600


def test_a_post_near_one_of_pbs_posts_waits_for_review(make_ctx):
    ctx = make_ctx()
    morning_delivery(ctx)
    cards = ctx.store.select("cards", "platform = 'x' AND status = 'suggested'", order="rank")
    for i, card in enumerate(cards[:2]):
        learn.record_post(ctx, card, text=f"Something else entirely {i}", posts=None, post_url=None,
                          posted_at="2026-09-25T02:00:00Z", editing_seconds=None, hook_index=None)
    blobs = ctx.data_root / "inbox" / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    (blobs / "upl_x_1.csv").write_text(X_NEW, encoding="utf-8")
    stats = _upload(ctx, "upl_x_1.csv", "upl_x")
    assert stats["metrics"] == 2
    statuses = sorted(m["status"] for m in ctx.store.select("metrics"))
    assert statuses == ["history", "needs_review"]  # 25 Sep has two PBS posts: which one is his to say
    queued = ctx.store.select("metrics", "status = 'needs_review'")[0]
    write_inbox(ctx.data_root, [{"id": "r1", "type": "metrics.review", "metric_id": queued["id"],
                                 "action": "history"}], name="review")
    inbox.ingest(ctx)
    assert ctx.store.get("metrics", queued["id"])["status"] == "history"


def test_rejects_other_file_types(make_ctx):
    ctx = make_ctx()
    write_inbox(ctx.data_root, [{"id": "u1", "type": "metrics.upload", "upload_id": "upl_bad",
                                 "paths": ["inbox/blobs/upl_bad_1.exe"]}])
    inbox.ingest(ctx)
    assert ctx.store.get("metric_uploads", "upl_bad") is None


def test_performance_review_uses_the_strongest_model_first(make_ctx, tmp_path):
    providers = {**fake_providers(), "gemini_pro": FakeProvider("gemini_pro", model="gemini-3-pro-preview")}
    ctx = make_ctx(providers=providers)
    blobs = ctx.data_root / "inbox" / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    linkedin_export(blobs / "upl_p_1.xlsx", [
        (7370000000000000001, "9/22/2026", 80, 4100), (7370000000000000002, "9/15/2026", 30, 5200),
        (7370000000000000003, "9/8/2026", 12, 900), (7370000000000000004, "9/1/2026", 50, 2100)])
    _upload(ctx, "upl_p_1.xlsx", "upl_p")
    result = performance.run(ctx)
    assert result["status"] == "ok" and result["posts"] == 4
    assert [r.task for r in providers["gemini_pro"].calls] == ["analysis"]
    assert not any(r.task == "analysis" for n, p in providers.items() if n != "gemini_pro" for r in p.calls)
    review = performance.latest(ctx)
    assert review["model"] == "gemini-3-pro-preview" and review["provider"] == "gemini_pro"
    assert review["findings"] and "impressions" in review["findings"][0]["evidence"]
    summary = performance.summarise(performance._post_rows(ctx))["linkedin"]
    assert summary["median_impressions"] == 3100 and summary["posts"] == 4
    assert summary["best_rate"][0]["engagement_rate"] == round(100 * 50 / 2100, 2)
    state = export.build(ctx)
    assert state["performance"]["model"] == "gemini-3-pro-preview"


def test_review_falls_back_when_pro_is_out_of_quota(make_ctx):
    from pbs.llm.base import LLMError

    pro = FakeProvider("gemini_pro", fail_with=LLMError("quota", status=429, code="RESOURCE_EXHAUSTED", quota=True))
    providers = {**fake_providers(), "gemini_pro": pro}
    ctx = make_ctx(providers=providers)
    for i in range(3):
        ctx.store.insert("metrics", {"id": f"met_h{i}", "platform": "x", "impressions": 100 * (i + 1),
                                     "reactions": i, "status": "history", "source": "file",
                                     "captured_at": timeutil.now_iso(), "created_at": timeutil.now_iso(),
                                     "raw": {"url": f"https://x.com/a/status/{i}", "posted_date": f"2026-09-0{i + 1}"}})
    assert performance.run(ctx)["status"] == "ok"
    assert performance.latest(ctx)["provider"] == "gemini"


def test_too_little_to_review(make_ctx):
    ctx = make_ctx()
    assert performance.run(ctx)["status"] == "too_little"
    assert performance.latest(ctx)["status"] == "too_little"


def test_the_tick_reviews_after_an_upload(make_ctx, tmp_path):
    ctx = make_ctx()
    blobs = ctx.data_root / "inbox" / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    (blobs / "upl_t_1.csv").write_text(X_NEW + X_OLD.split("\n", 1)[1].replace(
        "https://twitter.com", "https://x.com"), encoding="utf-8")
    write_inbox(ctx.data_root, [{"id": "u1", "type": "metrics.upload", "upload_id": "upl_t",
                                 "paths": ["inbox/blobs/upl_t_1.csv"]}])
    summary = tick.run(ctx.data_root, llm_providers=fake_providers(), send_notifications=False,
                       morning=lambda c: None)
    assert summary["status"] in ("ok", "partial")
    from pbs.store import Store

    review = Store.open(ctx.data_root).get_setting(performance.KEY)
    assert review and review["posts"] >= 2


def test_a_review_that_waits_for_quota_is_tried_again_on_the_next_run(make_ctx):
    from pbs.llm.base import BudgetExhausted

    ctx = make_ctx()
    for i in range(3):
        ctx.store.insert("metrics", {"id": f"met_w{i}", "platform": "linkedin", "impressions": 500 + i,
                                     "reactions": 5, "status": "history", "source": "file",
                                     "captured_at": timeutil.now_iso(), "created_at": timeutil.now_iso(),
                                     "raw": {"url": LI.format(7370000000000000100 + i), "posted_date": "2026-09-1" + str(i)}})

    def no_budget(req, schema=None, repair=True):
        raise BudgetExhausted("per-run LLM call cap reached")

    real = ctx.llm.call_json
    ctx.llm.call_json = no_budget
    assert performance.run(ctx)["status"] == "waiting"
    assert performance.due(ctx) and performance.latest(ctx)["status"] == "waiting"
    ctx.llm.call_json = real
    assert performance.run(ctx)["status"] == "ok"
    assert not performance.due(ctx)

    # A good review stays up, with a note, when the next one can't be written.
    ctx.llm.call_json = no_budget
    performance.run(ctx)
    kept = performance.latest(ctx)
    assert kept["status"] == "ok" and kept["findings"] and "quota" in kept["error"]


def test_a_pbs_post_with_a_different_link_isnt_a_candidate(make_ctx):
    ctx = make_ctx()
    morning_delivery(ctx)
    card = ctx.store.select("cards", "platform = 'linkedin' AND status = 'suggested'", order="rank")[0]
    learn.record_post(ctx, card, text="Agents need approval steps.", posts=None,
                      post_url=LI.format(7370000000000000555), posted_at="2026-09-22T00:30:00Z",
                      editing_seconds=None, hook_index=None)
    blobs = ctx.data_root / "inbox" / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    linkedin_export(blobs / "upl_d_1.xlsx", [(7370000000000000001, "9/22/2026", 80, 4100)])
    _upload(ctx, "upl_d_1.xlsx", "upl_d")
    (row,) = ctx.store.select("metrics")
    assert row["status"] == "history"  # same day, but PBS's post links to another post


SLUG = "https://www.linkedin.com/posts/ankit-singh-808521149_{}-share-{}-AbCd"


def _li_post(ctx, card, text, tags, when, url=None):
    post = learn.record_post(ctx, card, text=text, posts=None, post_url=url, posted_at=when, editing_seconds=None,
                             hook_index=None)
    ctx.store.update("posts", post["id"], hashtags=tags)
    return post


def test_the_words_in_linkedins_links_tell_same_day_posts_apart(make_ctx):
    """His real export: links carry the post's hashtags (or opening words), several posts a day, none of PBS's
    posts with a link saved. Each exported post goes to the right PBS post, none to two, and links are saved."""
    ctx = make_ctx()
    morning_delivery(ctx)
    cards = ctx.store.select("cards", "platform = 'linkedin' AND status = 'suggested'", order="rank")
    day = "2026-09-28T00:30:00Z"  # Monday morning in Melbourne
    reg = _li_post(ctx, cards[0], "Regulators want logs of every agent action.", ["#AI", "#AIRegulation", "#TechGovernance"], day)
    fin = _li_post(ctx, cards[1], "Banks are letting agents draft advice.", ["#AI", "#EnterpriseAutomation", "#FinancialAdvice"], day)
    paper = _li_post(ctx, cards[2], "A new paper released on Hugging Face breaks down LLM foundations.", ["#AI"], day)
    blobs = ctx.data_root / "inbox" / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    book = openpyxl.Workbook()
    top = book.active
    top.title = "TOP POSTS"
    top.append(["Post URL", "Post Publish Date", "Engagements", "", "Post URL", "Post Publish Date", "Impressions"])
    rows = [("ai-enterpriseautomation-financialadvice", "7521000000000000001", "9/28/2026", 3, 85),
            ("ai-airegulation-techgovernance", "7521000000000000002", "9/28/2026", 2, 318),
            ("a-new-paper-released-on-hugging-face-breaks", "7521000000000000003", "9/27/2026", 5, 151),  # a day off
            ("finally-made-it-guys-linkedin-has-decided", "7521000000000000004", "9/28/2026", 1, 281),  # his own
            ("excited-to-share-that-im-starting-a-new", "7249000000000000005", "10/8/2024", 0, 1)]  # old, still seen
    for slug, pid, d, e, i in rows:
        url = SLUG.format(slug, pid)
        top.append([url, d, e, "", url, d, i])
    disc = book.create_sheet("DISCOVERY")
    disc.append(["Overall Performance", "9/1/2026 - 9/28/2026"])
    disc.append(["Impressions", "6213"])
    book.save(blobs / "upl_s_1.xlsx")
    _upload(ctx, "upl_s_1.xlsx", "upl_s")
    by_post = {m["post_id"]: m for m in ctx.store.select("metrics", "status = 'confirmed'")}
    assert by_post[reg["id"]]["impressions"] == 318 and by_post[fin["id"]]["impressions"] == 85
    assert by_post[paper["id"]]["impressions"] == 151
    assert ctx.store.count("metrics", "status = 'history'") == 2 and ctx.store.count("metrics", "status = 'needs_review'") == 0
    assert ctx.store.get("posts", reg["id"])["post_url"].endswith("7521000000000000002-AbCd")  # the link is kept
    file = ctx.store.get("metric_uploads", "upl_s")["results"]["files"][0]
    assert file["matched"] == 3 and file["links_saved"] == 3

    # The review knows the export's own period, and which posts were published before it.
    data = performance.gather(ctx)
    old = [p for p in data["posts"] if p.get("date") == "2024-10-08"]
    assert old and old[0]["published_before_period"]
    assert performance.run(ctx)["status"] == "ok"
    assert performance.latest(ctx)["period"] == "9/1/2026 - 9/28/2026"


def test_a_wrong_guess_is_corrected_by_the_link_and_his_choices_stand_otherwise(make_ctx):
    ctx = make_ctx()
    morning_delivery(ctx)
    cards = ctx.store.select("cards", "platform = 'linkedin' AND status = 'suggested'", order="rank")
    meta = _li_post(ctx, cards[0], "Meta's new models read raw bytes.", ["#GenerativeAI", "#AI", "#MachineLearning"],
                    "2026-09-28T00:30:00Z")
    blobs = ctx.data_root / "inbox" / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)

    def export(name, rows):
        book = openpyxl.Workbook()
        top = book.active
        top.append(["Post URL", "Post Publish Date", "Impressions"])
        for url, imp in rows:
            top.append([url, "9/28/2026", imp])
        book.save(blobs / name)

    # Links without words, two posts that day and one of PBS's: only a guess, which he confirms (wrongly).
    feed = "https://www.linkedin.com/feed/update/urn:li:activity:{}/"
    export("upl_w_1.xlsx", [(feed.format("7519944248188903001"), 168), (feed.format("7519940078022901761"), 361)])
    _upload(ctx, "upl_w_1.xlsx", "upl_w")
    (guess,) = ctx.store.select("metrics", "status = 'needs_review'")
    assert guess["post_id"] == meta["id"] and ctx.store.count("metrics") == 2
    write_inbox(ctx.data_root, [{"id": "c1", "type": "metrics.review", "metric_id": guess["id"], "action": "confirm",
                                 "post_id": meta["id"]}], name="confirm")
    inbox.ingest(ctx)
    assert ctx.store.get("metrics", guess["id"])["raw"]["reviewed"] == "confirmed"

    # A later export links to the posts with their words: PBS's post is certain, his guess gives way.
    posts = "https://www.linkedin.com/posts/ankit_{}-activity-{}-AbCd"
    export("upl_w_2.xlsx", [(posts.format("aiagents-multimodalai", "7519944248188903001"), 170),
                            (posts.format("generativeai-ai-machinelearning", "7519940078022901761"), 380)])
    _upload(ctx, "upl_w_2.xlsx", "upl_w2")
    rows = {m["raw"]["key"]: m for m in ctx.store.select("metrics")}
    assert ctx.store.count("metrics") == 2  # one row per exported post, updated, not added again
    assert rows["7519940078022901761"]["post_id"] == meta["id"] and rows["7519940078022901761"]["status"] == "confirmed"
    assert rows["7519940078022901761"]["impressions"] == 380
    assert rows["7519944248188903001"]["post_id"] is None and rows["7519944248188903001"]["status"] == "history"


def test_his_choice_stands_when_nothing_certain_says_otherwise(make_ctx):
    ctx = make_ctx()
    morning_delivery(ctx)
    cards = ctx.store.select("cards", "platform = 'x' AND status = 'suggested'", order="rank")
    for i, card in enumerate(cards[:2]):
        learn.record_post(ctx, card, text=f"Something else entirely {i}", posts=None, post_url=None,
                          posted_at="2026-09-25T02:00:00Z", editing_seconds=None, hook_index=None)
    blobs = ctx.data_root / "inbox" / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    (blobs / "upl_h_1.csv").write_text(X_NEW, encoding="utf-8")
    _upload(ctx, "upl_h_1.csv", "upl_h")
    queued = ctx.store.select("metrics", "status = 'needs_review'")[0]
    chosen = ctx.store.select("posts", "platform = 'x'", order="posted_at")[0]["id"]
    write_inbox(ctx.data_root, [{"id": "c2", "type": "metrics.review", "metric_id": queued["id"], "action": "confirm",
                                 "post_id": chosen}], name="choose")
    inbox.ingest(ctx)
    (blobs / "upl_h_2.csv").write_text(X_NEW, encoding="utf-8")
    _upload(ctx, "upl_h_2.csv", "upl_h2")
    again = ctx.store.get("metrics", queued["id"])
    assert again["status"] == "confirmed" and again["post_id"] == chosen


def test_the_week_is_only_ever_a_week(make_ctx):
    ctx = make_ctx()
    blobs = ctx.data_root / "inbox" / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    (blobs / "upl_k_1.csv").write_text(X_NEW, encoding="utf-8")
    write_inbox(ctx.data_root, [{"id": "u1", "type": "metrics.upload", "upload_id": "upl_k",
                                 "paths": ["inbox/blobs/upl_k_1.csv"], "week": "../../Last 28 days"}])
    inbox.ingest(ctx)
    assert ctx.store.get("metric_uploads", "upl_k")["week"] is None
    metrics.process_uploads(ctx)
    assert (ctx.data_root / "media" / "metrics" / timeutil.iso_week(ctx.local_date()) / "upl_k_1.csv").exists()


def test_exports_already_uploaded_are_matched_again_once(make_ctx):
    ctx = make_ctx()
    folder = ctx.data_root / "media" / "metrics" / "Last 28 days"
    folder.mkdir(parents=True)
    linkedin_export(folder / "upl_old_1.xlsx", [(7370000000000000001, "9/22/2026", 80, 4100)])
    assert metrics.rematch_due(ctx)
    stats = metrics.rematch(ctx)
    assert stats["files"] == 1 and not metrics.rematch_due(ctx) and "analysis" in ctx.hints
    assert ctx.store.count("metrics") == 1


def test_the_review_says_which_stronger_models_were_passed_over_and_retries_a_busy_one(make_ctx):
    from pbs.llm.base import LLMError

    busy = LLMError("server error 503", status=503, code="UNAVAILABLE", retryable=True)
    quota = LLMError("daily quota reached", status=429, code="RESOURCE_EXHAUSTED", quota=True)
    providers = {**fake_providers(), "gemini_pro": FakeProvider("gemini_pro", fail_with=quota),
                 "gemini": FakeProvider("gemini", fail_with=busy)}
    ctx = make_ctx(providers=providers)
    for i in range(3):
        ctx.store.insert("metrics", {"id": f"met_b{i}", "platform": "linkedin", "impressions": 100 + i,
                                     "reactions": 2, "status": "history", "source": "file",
                                     "captured_at": timeutil.now_iso(), "created_at": timeutil.now_iso(),
                                     "raw": {"url": LI.format(7370000000000000200 + i), "posted_date": "2026-09-2" + str(i)}})
    performance.run(ctx)
    review = performance.latest(ctx)
    assert review["provider"] not in ("gemini_pro", "gemini")
    assert review["passed_over"][:2] == [{"provider": "gemini_pro", "why": "quota"}, {"provider": "gemini", "why": "busy"}]
    assert review["retry"] and performance.due(ctx)
    performance.run(ctx)  # still busy: no more tries today
    assert not performance.due(ctx)
