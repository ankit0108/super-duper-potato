from __future__ import annotations

import pytest
from pydantic import BaseModel

from pbs.llm.base import AllProvidersFailed, BudgetExhausted, LLMError, LLMRequest, extract_json
from pbs.llm.fake import FakeProvider
from pbs.llm.router import Router
from pbs.settings import load


def _settings(**llm_patch):
    base = {
        "llm": {
            "daily_cap": 10,
            "max_calls_per_run": 8,
            "providers": {
                "a": {"kind": "fake", "model": "a", "daily_limit": 2, "rpm": 1000, "trains_on_inputs": True},
                "b": {"kind": "fake", "model": "b", "daily_limit": 5, "rpm": 1000, "trains_on_inputs": False},
            },
            "routes": {"draft": ["a", "b"], "draft_personal": ["a", "b"], "triage": ["a", "b"]},
        }
    }
    base["llm"].update(llm_patch)
    s, _ = load(base)
    return s


def test_extract_json_tolerates_fences_prose_and_trailing_commas():
    assert extract_json('```json\n{"a": 1,}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": [1, 2,]} hope this helps') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_falls_back_to_next_provider_on_quota(store):
    a = FakeProvider("a", fail_with=LLMError("daily quota reached", status=429, quota=True))
    b = FakeProvider("b")
    r = Router(_settings(), store, providers={"a": a, "b": b}, sleep=lambda s: None)
    resp = r.call(LLMRequest(task="draft", system="s", prompt="<input>{}</input>"))
    assert resp.provider == "b"
    assert r.usage.fallbacks == 1
    # provider a is now marked exhausted for the day and skipped without another call
    r.call(LLMRequest(task="draft", system="s", prompt="<input>{}</input>"))
    assert len(a.calls) == 1


def test_personal_tasks_prefer_non_training_providers(store):
    a, b = FakeProvider("a"), FakeProvider("b")
    r = Router(_settings(), store, providers={"a": a, "b": b}, sleep=lambda s: None)
    resp = r.call(LLMRequest(task="draft_personal", system="s", prompt="x", personal=True))
    assert resp.provider == "b"


def test_personal_tasks_can_forbid_training_fallback(store):
    a = FakeProvider("a")
    b = FakeProvider("b", fail_with=LLMError("daily", status=429, quota=True))
    r = Router(_settings(personal_allow_training_fallback=False), store, providers={"a": a, "b": b},
               sleep=lambda s: None)
    with pytest.raises(BudgetExhausted):
        r.call(LLMRequest(task="draft_personal", system="s", prompt="x", personal=True))
    assert not a.calls


def test_daily_limits_and_caps(store):
    a, b = FakeProvider("a"), FakeProvider("b")
    r = Router(_settings(), store, providers={"a": a, "b": b}, sleep=lambda s: None)
    for _ in range(7):
        r.call(LLMRequest(task="draft", system="s", prompt="x"))
    assert len(a.calls) == 2 and len(b.calls) == 5
    with pytest.raises(BudgetExhausted):
        r.call(LLMRequest(task="draft", system="s", prompt="x"))
    assert r.remaining("draft") == 0


def test_blocklist_terms_are_redacted_before_any_call(store):
    a = FakeProvider("a")
    r = Router(_settings(), store, blocklist=["Acme Bank"], providers={"a": a, "b": FakeProvider("b")},
               sleep=lambda s: None)
    r.call(LLMRequest(task="draft", system="We work at acme bank", prompt="Acme-Bank's rollout"))
    sent = a.calls[0]
    assert "acme" not in (sent.system + sent.prompt).lower()
    assert "[redacted]" in sent.prompt


class _Out(BaseModel):
    value: int


def test_call_json_repairs_invalid_output_once(store):
    replies = iter(["not json at all", '{"value": 3}'])
    a = FakeProvider("a", handlers={"draft": lambda req, data: next(replies)})
    r = Router(_settings(), store, providers={"a": a, "b": FakeProvider("b")}, sleep=lambda s: None)
    out, _ = r.call_json(LLMRequest(task="draft", system="s", prompt="x"), _Out)
    assert out.value == 3
    assert "could not be used" in a.calls[1].prompt


def test_rate_limit_retries_then_succeeds(store):
    state = {"n": 0}

    def flaky(req, data):
        state["n"] += 1
        if state["n"] == 1:
            raise LLMError("rate limited", status=429, rate_limited=True, retryable=True, retry_after=1)
        return {"ok": True}

    a = FakeProvider("a", handlers={"draft": flaky})
    waits: list[float] = []
    r = Router(_settings(), store, providers={"a": a, "b": FakeProvider("b")}, sleep=waits.append)
    resp = r.call(LLMRequest(task="draft", system="s", prompt="x"))
    assert resp.provider == "a" and 1 in waits


def test_fake_generate_raises_from_handler_are_classified(store):
    def boom(req, data):
        raise LLMError("auth", status=401, fatal_for_provider=True)

    a = FakeProvider("a", handlers={"draft": boom})
    r = Router(_settings(), store, providers={"a": a, "b": FakeProvider("b")}, sleep=lambda s: None)
    assert r.call(LLMRequest(task="draft", system="s", prompt="x")).provider == "b"
    assert r.call(LLMRequest(task="draft", system="s", prompt="x")).provider == "b"
    assert len(a.calls) == 1


def test_a_provider_that_throws_anything_is_switched_off_and_the_next_one_answers(store, capsys):
    import json

    def broken(req, data):  # what a retired API answering with a web page used to cause
        raise json.JSONDecodeError("Expecting value", "<html>", 0)

    a = FakeProvider("a", handlers={"draft": broken})
    r = Router(_settings(), store, providers={"a": a, "b": FakeProvider("b")}, sleep=lambda s: None)
    assert r.call(LLMRequest(task="draft", system="s", prompt="x")).provider == "b"
    assert r.call(LLMRequest(task="draft", system="s", prompt="x")).provider == "b"
    assert len(a.calls) == 1
    assert r.usage.provider_errors == {"a": "request failed (JSONDecodeError)"}
    assert "llm: a switched off for this run: request failed (JSONDecodeError)" in capsys.readouterr().out


def test_when_every_provider_fails_the_error_says_so_and_is_remembered(store):
    a = FakeProvider("a", fail_with=LLMError("gone", status=404, code="NOT_FOUND", model_gone=True))
    b = FakeProvider("b", fail_with=LLMError("bad key", status=401, code="invalid_api_key", fatal_for_provider=True))
    r = Router(_settings(), store, providers={"a": a, "b": b}, sleep=lambda s: None)
    with pytest.raises(AllProvidersFailed):
        r.call(LLMRequest(task="draft", system="s", prompt="x"))
    with pytest.raises(AllProvidersFailed):  # later calls fail fast, without calling anyone
        r.call(LLMRequest(task="triage", system="s", prompt="x"))
    assert len(a.calls) == 1 and len(b.calls) == 1 and r.usage.all_failed and r.chain_broken("draft")
    assert r.usage.provider_errors == {"a": "model not available (HTTP 404 NOT_FOUND)",
                                       "b": "key rejected (HTTP 401 invalid_api_key)"}
    row = store.get("quota", f"a:{r._day()}")
    assert row["last_error_at"] and not row.get("last_ok_at") and not row.get("requests")


def test_an_overloaded_provider_sits_out_the_rest_of_the_run_after_two_calls(store, capsys):
    busy = LLMError("server error 503", status=503, code="UNAVAILABLE", retryable=True)
    a = FakeProvider("a", fail_with=busy)
    b = FakeProvider("b")
    waits: list[float] = []
    r = Router(_settings(max_calls_per_run=20, daily_cap=40), store, providers={"a": a, "b": b}, sleep=waits.append)
    for _ in range(4):
        assert r.call(LLMRequest(task="draft", system="s", prompt="x")).provider == "b"
    # One short retry on each of the first two calls, then a is skipped without being called.
    assert len(a.calls) == 4 and len(b.calls) == 4
    assert [w for w in waits if w >= 1] == [2.0, 2.0]  # pacing aside: one 2 s retry wait per call, then none
    assert "llm: a overloaded (server error (HTTP 503 UNAVAILABLE)); using the next provider" in capsys.readouterr().out
    assert not r.chain_broken("draft")


def test_an_overloaded_provider_gets_another_go_when_nothing_else_can_answer(store):
    busy = LLMError("server error 503", status=503, retryable=True)
    state = {"n": 0}

    def recovering(req, data):
        state["n"] += 1
        if state["n"] <= 4:
            raise busy
        return {"ok": True}

    a = FakeProvider("a", handlers={"draft": recovering})
    b = FakeProvider("b")
    r = Router(_settings(max_calls_per_run=20, daily_cap=40), store, providers={"a": a, "b": b}, sleep=lambda s: None)
    r.call(LLMRequest(task="draft", system="s", prompt="x"))
    r.call(LLMRequest(task="draft", system="s", prompt="x"))
    assert r._overloaded == {"a": "server error (HTTP 503)"}
    b.fail_with = LLMError("daily", status=429, quota=True)
    resp = r.call(LLMRequest(task="draft", system="s", prompt="x"))
    assert resp.provider == "a" and r._overloaded == {}  # it recovered, so it's back in the rotation


def test_out_of_quota_everywhere_is_budget_not_failure(store):
    a = FakeProvider("a", fail_with=LLMError("daily", status=429, quota=True))
    b = FakeProvider("b", fail_with=LLMError("daily", status=429, quota=True))
    r = Router(_settings(), store, providers={"a": a, "b": b}, sleep=lambda s: None)
    with pytest.raises(BudgetExhausted) as err:
        r.call(LLMRequest(task="draft", system="s", prompt="x"))
    assert not isinstance(err.value, AllProvidersFailed)


def test_routes_skip_providers_that_no_longer_exist(store):
    s = _settings()
    s.llm.routes["draft"] = ["retired", "a", "b"]
    r = Router(s, store, providers={"a": FakeProvider("a"), "b": FakeProvider("b")}, sleep=lambda s: None)
    assert r.chain("draft") == ["a", "b"]


def test_json_rows_accepts_the_wrapped_and_the_bare_list_shapes():
    from pbs.llm.base import json_rows

    assert json_rows({"items": [{"id": 1}, "junk"]}, "items") == [{"id": 1}]
    assert json_rows([{"id": 2}], "items") == [{"id": 2}]
    assert json_rows({"other": []}, "items") == [] and json_rows(None, "items") == [] and json_rows("x", "items") == []
