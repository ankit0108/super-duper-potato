"""The platform writers: plans before the drafts, same-lane swaps, and the platform checks after (pbs/agents/writer.py)."""

from __future__ import annotations

import json

from conftest import fake_providers

from pbs import editing, prompting
from pbs.agents import scout as scouts
from pbs.agents import writer as writers
from pbs.deliver import morning_delivery
from pbs.rank import Candidate, build_candidates, build_memory
from pbs.scout.scouting import run_scouts
from pbs.style import style_for
from pbs.topics import build_topics


def _calls(ctx, task):
    return [r for p in ctx.llm._providers.values() if hasattr(p, "calls") for r in p.calls if r.task == task]


def test_each_plain_post_is_planned_and_the_plan_reaches_its_draft(make_ctx):
    ctx = make_ctx()
    res = morning_delivery(ctx)
    cards = ctx.store.select("cards", "delivery_id = ?", (res["id"],))
    planned = [c for c in cards if c.get("brief")]
    assert planned, "the writers planned the morning's plain posts"
    for c in cards:
        if c.get("post_type") or c["mode"] == "interview":
            assert not c.get("brief"), "funny takes, quotes, thoughts and question cards keep their own craft"
    assert {c["platform"] for c in planned} == {"linkedin", "x"}
    assert len(_calls(ctx, "brief")) == 2, "one review per platform"
    # The plan is in the material each planned card was drafted from.
    drafts = {(d["platform"], d["topic"]): r for r in _calls(ctx, "draft") if "writer_plan" in r.prompt
              for d in [json.loads(prompting_input(r.prompt))]}
    for c in planned:
        if c.get("draft"):
            req = drafts[(c["platform"], c["title"])]
            data = json.loads(prompting_input(req.prompt))
            assert data["writer_plan"]["job"] == c["brief"]["job"]
            assert "scout_read" not in data or "why_it_could_travel_a_guess" in data["scout_read"]


def prompting_input(prompt: str) -> str:
    return prompt.split("<input>", 1)[1].split("</input>", 1)[0]


def _morning(ctx):
    run_scouts(ctx)
    build_topics(ctx)
    cands = build_candidates(ctx, ctx.store.select("topics"), build_memory(ctx), use_llm=False)
    return cands


def test_a_swap_stays_inside_its_lane(make_ctx):
    ctx = make_ctx()
    cands = _morning(ctx)["linkedin"]
    report = scouts.report(ctx, "linkedin", cands)
    plain = [c for c in cands if writers.plannable(c)]
    picks = plain[:2]
    bench_same = next(c for c in plain[2:] if c.pillar == picks[0].pillar and any(o["id"] == c.topic["id"] for o in report["opportunities"]))
    other = next((c for c in plain[2:] if c.pillar != picks[0].pillar and any(o["id"] == c.topic["id"] for o in report["opportunities"])), None)

    def swap_to(title_wanted):
        def handler(req, data):
            bench = {b["title"]: b["id"] for b in data["bench"]}
            plans = [{"id": p["id"], "job": "Say what it changes."} for p in data["picks"]]
            take = bench.get(title_wanted)
            plans.append({"id": take, "job": "The stronger story."})
            return {"plans": plans, "swaps": [{"drop": "P1", "take": take, "reason": "Nothing specific to add."}]}
        return handler

    title = lambda c: c.topic.get("title_en") or c.topic.get("title")  # noqa: E731
    ctx.llm._providers.update(fake_providers(brief=swap_to(title(bench_same))))
    out, info = writers.review(ctx, "linkedin", list(picks), cands, report)
    assert info["swapped"] == 1 and out[0].topic_key == bench_same.topic_key and out[0].pillar == picks[0].pillar
    assert out[0].brief["swapped_for"] == title(picks[0]) and out[0].brief["reason"]
    assert out[1].topic_key == picks[1].topic_key and out[1].brief["job"]
    if other is not None:
        ctx.llm._providers.update(fake_providers(brief=swap_to(title(other))))
        out, info = writers.review(ctx, "linkedin", list(picks), cands, report)
        assert info["swapped"] == 0 and [c.topic_key for c in out] == [c.topic_key for c in picks]


def test_no_plans_when_the_drafts_need_the_budget(make_ctx):
    ctx = make_ctx()
    ctx.settings.llm.daily_cap = 18
    res = morning_delivery(ctx)
    cards = ctx.store.select("cards", "delivery_id = ?", (res["id"],))
    assert cards and not any(c.get("brief") for c in cards)
    assert not _calls(ctx, "brief")


def test_the_writers_review_with_another_model_than_the_scouts(settings):
    assert settings.llm.routes["brief"][0] != settings.llm.routes["scout"][0]


def _card(platform, fmt):
    return {"platform": platform, "format": fmt}


def test_check_finds_the_platform_basics():
    li = _card("linkedin", "li_text")
    kinds = lambda card, text, posts=None: [t["kind"] for t in writers.check(card, {"text": text, "posts": posts or []})]  # noqa: E731
    good = "Agents now close 40% of invoices without a person.\n\nThe catch is the other 60%.\n\nWhich exceptions would you route first?"
    assert kinds(li, good) == []
    assert kinds(li, "In today's fast-moving world, agents matter.\n\nMore.") == ["preamble"]
    assert kinds(li, ("A " * 130) + "long opening.\n\nNext.") == ["buried_opening"]
    assert kinds(li, "A point.\n\nRead it: https://example.com/a") == ["link_in_body"]
    assert kinds(li, "A point.\n\nThoughts?") == ["generic_ending"]
    x = _card("x", "x_single")
    assert kinds(x, "BREAKING: a model shipped") == ["headline_prefix"]
    assert kinds(_card("x", "x_reply"), "Great post! Also the eval set leaks.") == ["flattery"]
    assert kinds(_card("x", "x_quote"), "Worth reading https://x.com/a/status/1") == []
    assert kinds(_card("x", "x_thread"), "", ["NEW: three things", "Two", "Three"]) == ["headline_prefix"]
    assert writers.label("link_in_body").startswith("A link")


def test_a_draft_missing_only_a_basic_gets_one_editor_pass(make_ctx):
    ctx = make_ctx()
    card = {"id": "crd_t", "platform": "linkedin", "format": "li_text", "pillar": "industry", "mode": "external"}
    style = style_for(ctx, "linkedin", "industry", "li_text")
    text = "Agents now close 40% of invoices.\n\nThe rest still need a person.\n\nThoughts?"

    def edit(req, data):
        assert "generic closing question" in req.prompt
        return {"text": text.replace("Thoughts?", "Which exceptions would you route to a person first?"), "posts": []}

    ctx.llm._providers.update(fake_providers(edit=edit))
    out = editing.polish(ctx, card, {"draft": {"text": text, "posts": []}}, style, evidence="40% of invoices",
                         personal=False)
    assert out["edit"]["kept"] and out["edit"]["before"] == 1 and out["edit"]["after"] == 0
    assert out["edit"]["kinds"] == ["generic_ending"]
    assert out["draft"]["text"].endswith("first?") and len(_calls(ctx, "edit")) == 1


def test_writer_prompts_fit_the_smallest_models_input(make_ctx):
    """Ten X picks and the bench, each at the longest the writer sends, fit Groq's input (the brief route's first
    model), by the router's own estimate."""
    ctx = make_ctx()
    groq = ctx.settings.llm.providers["groq"].max_input_tokens
    long = "A detailed summary of the development, with the numbers, the names and what changed for whom. " * 8
    note = {"evidence": ["612 points and 388 comments on Hacker News", "covered by 3 outlets",
                         "found in 2 public LinkedIn posts"], "evidence_level": "observed", "why": long,
            "opening": long, "reply_to": long, "score": 0.72}
    for platform, n in (("linkedin", 5), ("x", 10)):
        lane = next(iter(ctx.settings.pillars(platform)))
        def cand(i, platform=platform, lane=lane):
            return Candidate(topic={"id": f"top_{i}", "title": "A long headline about an AI agents platform launch " * 3,
                                    "summary": long}, platform=platform, pillar=lane,
                             fmt="x_reply" if platform == "x" else "li_text", mode="external", base=1.0, angle=long,
                             scout=note)
        picks = {f"P{i}": cand(i) for i in range(1, n + 1)}
        bench = {f"B{i}": cand(100 + i) for i in range(1, writers.BENCH + 1)}
        prompt = prompting.render(f"writer_{platform}", display_name="Ankit", today="2026-11-17",
                                  shapes=", ".join(writers.SHAPES[platform]),
                                  input_json=writers.payload(ctx, picks, bench, {}))
        need = writers.request(platform, prompt).estimated_input_tokens()
        assert need < groq, f"the {platform} writer's prompt is about {need} tokens; Groq takes {groq}"


def test_plannable_matches_the_scouts_judgement():
    topic = {"id": "top_1", "title": "T", "why_now": {"signals": {}}}
    plain = Candidate(topic=topic, platform="x", pillar="tech", fmt="x_single", mode="external", base=1.0)
    assert writers.plannable(plain)
    assert not writers.plannable(Candidate(**{**plain.__dict__, "post_type": "thought"}))
    assert not writers.plannable(Candidate(**{**plain.__dict__, "mode": "interview"}))
