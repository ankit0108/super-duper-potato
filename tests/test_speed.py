"""Fresh posts in minutes: per-call deadlines, cards drafted in parallel, checkpoints, reused triage."""

from __future__ import annotations

import json
import os
import stat
import threading
import time

import httpx
from conftest import fake_providers

from pbs import deliver
from pbs.llm.base import LLMError, LLMRequest
from pbs.llm.gemini import GeminiProvider
from pbs.rank import build_candidates, build_memory, triage
from pbs.scout.scouting import run_scouts
from pbs.settings import ProviderSpec
from pbs.topics import build_topics

REQ = LLMRequest(task="draft", system="s", prompt="p", timeout=5)


def test_a_model_that_doesnt_answer_in_time_counts_as_busy_and_the_next_one_answers(monkeypatch):
    monkeypatch.setenv("TEST_GEMINI_KEY", "k")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = request.url.path.rsplit("/", 1)[-1].split(":")[0]
        seen.append(model)
        if model == "gemini-3.6-flash":
            raise httpx.ReadTimeout("no bytes", request=request)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]},
                                                         "finishReason": "STOP"}], "modelVersion": model})

    spec = ProviderSpec(kind="gemini", model="gemini-3.6-flash", fallback_models=["gemini-3.5-flash"],
                        quota_per_model=True, api_key_env="TEST_GEMINI_KEY")
    p = GeminiProvider("gemini", spec, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert p.generate(REQ).model == "gemini-3.5-flash"
    assert seen == ["gemini-3.6-flash", "gemini-3.5-flash"]
    from pbs.llm.base import timeout_error

    err = timeout_error(httpx.ReadTimeout("x"), 50)
    assert isinstance(err, LLMError) and err.status == 504 and err.retryable


def test_every_call_gets_its_tasks_deadline(make_ctx):
    ctx = make_ctx()
    assert ctx.settings.llm.timeouts["draft"] == 50 and ctx.settings.llm.timeouts["default"] == 90
    req = LLMRequest(task="draft", system="s", prompt="p")
    ctx.llm.call(req)
    assert req.timeout == 50
    grounded = LLMRequest(task="search", system="s", prompt="p")
    ctx.llm.call(grounded)
    assert grounded.timeout == 90


def _slow(seconds: float):
    """A fake draft handler that takes a while, recording how many run at once."""
    state = {"now": 0, "most": 0}
    lock = threading.Lock()

    def handler(req, data):
        from pbs.llm.fake import DEFAULT_HANDLERS

        with lock:
            state["now"] += 1
            state["most"] = max(state["most"], state["now"])
        time.sleep(seconds)
        with lock:
            state["now"] -= 1
        return DEFAULT_HANDLERS["draft"](req, data)

    return handler, state


def test_cards_are_drafted_several_at_a_time_and_reach_the_desk_in_batches(make_ctx, tmp_path, monkeypatch):
    monkeypatch.delenv("PBS_SERIAL")
    calls = tmp_path / "checkpoints.txt"
    script = tmp_path / "push.sh"
    script.write_text(f'#!/bin/sh\necho "$1" >> "{calls}"\n', encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PBS_CHECKPOINT", str(script))
    handler, state = _slow(0.05)
    ctx = make_ctx(providers=fake_providers(draft=handler))
    ctx.settings.drafting.editor_pass = False
    res = deliver.morning_delivery(ctx)
    assert res["counts"] == {"linkedin": 5, "x": 10}
    cards = ctx.store.select("cards", "delivery_id = ?", (res["id"],))
    assert all(c["status"] in ("suggested", "needs_input", "blocked") for c in cards)
    assert 1 < state["most"] <= ctx.settings.drafting.parallel  # in parallel, never more than the setting
    lines = calls.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "pbs: checkpoint (3 of 15 cards drafted)" and len(lines) == 3  # 3, 8, 13 of 15
    desk = json.loads((ctx.data_root / "desk" / "desk.json").read_text(encoding="utf-8"))
    assert any(c.get("delivery_id") == res["id"] for c in desk["cards"])  # the desk had cards before the end
    # Same cards, same order, as one at a time.
    ranks = {c["platform"]: sorted(x["rank"] for x in cards if x["platform"] == c["platform"]) for c in cards}
    assert ranks == {"linkedin": [1, 2, 3, 4, 5], "x": list(range(1, 11))}


def test_without_a_checkpoint_command_nothing_is_pushed_mid_run(make_ctx, monkeypatch):
    monkeypatch.delenv("PBS_CHECKPOINT", raising=False)
    ctx = make_ctx()
    ctx.checkpoint("3 of 15")  # no-op
    assert not (ctx.data_root / "desk" / "desk.json").exists()
    assert "PBS_CHECKPOINT" not in os.environ


def test_a_fresh_set_reuses_the_mornings_triage(make_ctx):
    ctx = make_ctx()
    run_scouts(ctx)
    build_topics(ctx)
    topics = ctx.store.select("topics")[:10]
    first = triage(ctx, topics)

    def reread():
        return [ctx.store.get("topics", t["id"]) for t in topics]

    asked = sum(1 for p in ctx.llm._providers.values() for c in p.calls if c.task == "triage")
    again = triage(ctx, reread())
    assert again.keys() == first.keys()
    assert sum(1 for p in ctx.llm._providers.values() for c in p.calls if c.task == "triage") == asked  # no new call
    ctx.settings.ranking.triage_reuse_hours = 0
    triage(ctx, reread())
    assert sum(1 for p in ctx.llm._providers.values() for c in p.calls if c.task == "triage") == asked + 1
    cands = build_candidates(ctx, ctx.store.select("topics"), build_memory(ctx))
    assert cands["linkedin"] and cands["x"]
