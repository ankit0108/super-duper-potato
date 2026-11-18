"""The platform editors: they choose and order the morning set inside his lane mix (pbs/agents/editor.py)."""

from __future__ import annotations

from conftest import fake_providers, write_inbox

from pbs import draft, inbox, prompting
from pbs.agents import editor as editors
from pbs.agents import scout as scouts
from pbs.deliver import morning_delivery
from pbs.rank import Candidate, build_candidates, build_memory
from pbs.scout.scouting import run_scouts
from pbs.topics import build_topics


def _calls(ctx, task):
    return [r for p in ctx.llm._providers.values() if hasattr(p, "calls") for r in p.calls if r.task == task]


def test_the_editor_orders_the_board_and_lists_runner_ups(make_ctx):
    ctx = make_ctx()
    res = morning_delivery(ctx)
    assert len(_calls(ctx, "editor")) == 2, "one editor per platform"
    for platform in ("linkedin", "x"):
        slate = ctx.store.get("editor_slates", editors.slate_id(platform, res["id"]))
        assert slate["status"] == "ok" and slate["picks"]
        cards = sorted(ctx.store.select("cards", "delivery_id = ? AND platform = ?", (res["id"], platform)),
                       key=lambda c: c["rank"])
        assert [c["topic_id"] for c in cards] == [p["id"] for p in slate["picks"]], "the board follows its order"
        assert all(c["editor"]["rank"] == c["rank"] for c in cards)
        assert any(c["editor"]["why"] for c in cards)
        assert len(slate["runners_up"]) <= ctx.settings.agents.runner_ups
        assert not {r["id"] for r in slate["runners_up"]} & {c["topic_id"] for c in cards}


def _setup(ctx):
    run_scouts(ctx)
    build_topics(ctx)
    cands = build_candidates(ctx, ctx.store.select("topics"), build_memory(ctx), use_llm=False)["linkedin"]
    scouts.report(ctx, "linkedin", cands)
    plain = [c for c in cands if scouts._eligible([c])]
    return cands, plain


def test_a_swap_stays_in_its_lane_and_exploration_stays(make_ctx):
    ctx = make_ctx()
    cands, plain = _setup(ctx)
    lane = plain[0].pillar
    same = [c for c in plain if c.pillar == lane]
    picks = [same[0], Candidate(**{**plain[-1].__dict__, "explore": True})]
    alts = editors.alternatives(picks, cands)
    title = lambda c: c.topic.get("title_en") or c.topic.get("title")  # noqa: E731
    target = next(i for i, a in enumerate(alts, 1) if a.pillar == lane)
    other = next((i for i, a in enumerate(alts, 1) if a.pillar != lane), None)

    def handler(req, data):
        swaps = [{"drop": "P1", "take": f"A{target}", "why": "Clearly stronger."},
                 {"drop": "P2", "take": f"A{other or target}", "why": "Exploration can't be swapped."}]
        return {"order": ["P2", "P1"], "swaps": swaps, "why": {"P2": "Worth a look."},
                "runners_up": [{"id": "A99", "why": "unknown"}]}

    ctx.llm._providers.update(fake_providers(editor=handler))
    out, slate = editors.choose(ctx, "linkedin", list(picks), cands, "dly_test")
    assert slate["swaps"] == 1
    assert out[0].explore and out[0].editor["rank"] == 1, "exploration keeps its slot, moved to the top"
    assert out[1].topic_key == alts[target - 1].topic_key and out[1].pillar == lane
    assert out[1].editor["swapped_for"] == title(same[0])
    assert all(r["id"] != alts[target - 1].topic["id"] for r in slate["runners_up"])
    assert len(slate["runners_up"]) == min(ctx.settings.agents.runner_ups, len(alts) - 1), "the rest fill the list"


def test_without_a_model_the_allocation_stands(make_ctx):
    ctx = make_ctx()
    cands, plain = _setup(ctx)
    picks = plain[:3]
    out, slate = editors.choose(ctx, "linkedin", list(picks), cands, "dly_test", use_llm=False)
    assert [c.topic_key for c in out] == [c.topic_key for c in picks]
    assert slate["status"] == "fallback" and slate["error"] and slate["runners_up"]
    assert not _calls(ctx, "editor")


def test_a_runner_up_can_be_drafted(make_ctx):
    ctx = make_ctx()
    res = morning_delivery(ctx)
    slate = next(s for s in ctx.store.select("editor_slates") if s["runners_up"])
    runner = slate["runners_up"][0]
    write_inbox(ctx.data_root, [{"id": "e1", "type": "editor.draft", "slate_id": slate["id"], "topic_id": runner["id"]}])
    assert inbox.ingest(ctx)["applied"] == 1
    card = next(c for c in ctx.store.select("cards", "topic_id = ?", (runner["id"],)) if c["platform"] == slate["platform"])
    assert card["work"]["kind"] == "draft" and card["editor"]["why"] == runner["why"] and card["pillar"] == runner["lane"]
    assert next(r for r in ctx.store.get("editor_slates", slate["id"])["runners_up"] if r["id"] == runner["id"])["card_id"] == card["id"]
    assert draft.process_work(ctx)["done"] == 1 and ctx.store.get("cards", card["id"])["draft"]
    write_inbox(ctx.data_root, [{"id": "e2", "type": "editor.draft", "slate_id": slate["id"], "topic_id": runner["id"]}],
                name="again")
    assert inbox.ingest(ctx)["rejected"] == 1
    assert res["id"]


def test_the_editor_prompt_fits_the_smallest_model(make_ctx):
    ctx = make_ctx()
    limit = min(p.max_input_tokens for p in ctx.settings.llm.providers.values() if p.max_input_tokens)
    long = "A detailed summary of the development, with the numbers, the names and what changed for whom. " * 6
    note = {"evidence": ["612 points and 388 comments on Hacker News", "covered by 3 outlets"], "why": long, "score": 0.7}
    lane = next(iter(ctx.settings.pillars("x")))

    def cand(i):
        return Candidate(topic={"id": f"top_{i}", "title": "A long headline about an AI agents platform launch " * 3,
                                "summary": long, "first_seen_at": "2026-09-27T08:00:00Z"}, platform="x", pillar=lane,
                         fmt="x_reply", mode="external", base=1.0, angle=long, scout=note)
    picks = {f"P{i}": cand(i) for i in range(1, 11)}
    alts = {f"A{i}": cand(100 + i) for i in range(1, editors.ALTERNATIVES + 1)}
    prompt = prompting.render("editor", display_name="Ankit", today="2026-11-18", platform_label="X",
                              platform_notes=editors.NOTES["x"], audience="engineers " * 20, results="“a post” " * 10,
                              recent_posts="a post; " * 8, feedback="- skipped: not my focus\n" * 6, n_runners=5,
                              input_json=editors.payload(ctx, picks, alts))
    need = editors.request(ctx, "x", prompt).estimated_input_tokens()
    assert need < limit, f"the editor's prompt is about {need} tokens; the smallest model takes {limit}"


def test_calibration_counts_posts_from_the_top_half():
    cards = [{"platform": "x", "delivery_id": "d1", "editor": {"rank": r}, "status": s}
             for r, s in ((1, "posted"), (2, "skipped"), (3, "posted"), (4, "expired"))]
    assert editors.calibration(cards) == {"x": {"posted_top_half": 1, "posted_bottom_half": 1}}
