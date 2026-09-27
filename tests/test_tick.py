from __future__ import annotations

import json

from conftest import fake_providers, write_inbox

from pbs import requests as req_mod
from pbs import tick, timeutil
from pbs.context import Ctx
from pbs.contracts import DeskState
from pbs.deliver import delivery_due, weekly_batch_due
from pbs.reflect import reflection_due


def _run(tmp_path, web, **kw):
    return tick.run(tmp_path / "data", transport=web.transport(), llm_providers=fake_providers(),
                    sleep=lambda s: None, send_notifications=False, **kw)


def test_tick_delivers_once_and_exports_a_valid_desk(tmp_path, web, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    first = _run(tmp_path, web, trigger="schedule", hints={"morning"})
    assert first["status"] == "ok" and first["delivery"]["counts"] == {"linkedin": 3, "x": 6}
    desk = json.loads((tmp_path / "data" / "desk" / "desk.json").read_text())
    DeskState.model_validate(desk)
    assert desk["meta"]["schema_version"] == 1 and desk["delivery"]["id"] == first["delivery"]["id"]
    assert len(desk["stances"]) == 10 and desk["playbook"]["version"] == 1
    assert desk["runs"][0]["id"] == first["run_id"]

    second = _run(tmp_path, web, trigger="schedule")
    assert "delivery" not in second  # already delivered today
    desk2 = json.loads((tmp_path / "data" / "desk" / "desk.json").read_text())
    assert len([c for c in desk2["cards"] if c.get("delivery_id") == first["delivery"]["id"]]) == 9


def test_desk_events_round_trip_through_a_tick(tmp_path, web, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    _run(tmp_path, web, trigger="schedule")
    desk = json.loads((tmp_path / "data" / "desk" / "desk.json").read_text())
    card = next(c for c in desk["cards"] if c["status"] == "suggested")
    write_inbox(tmp_path / "data", [
        {"id": "ev_post_1", "type": "card.posted", "card_id": card["id"], "text": "Final words."},
        {"id": "ev_req_1", "type": "request.create", "request_id": "req_a", "query": "MCP servers",
         "platforms": {"x": 1}},
    ])
    out = _run(tmp_path, web, trigger="dispatch")
    assert out["status"] == "ok"
    desk = json.loads((tmp_path / "data" / "desk" / "desk.json").read_text())
    assert "ev_post_1" in desk["processed_event_ids"] and "ev_req_1" in desk["processed_event_ids"]
    assert any(p["card_id"] == card["id"] for p in desk["posts"])
    req = next(r for r in desk["requests"] if r["id"] == "req_a")
    assert req["status"] == "done" and len(req["card_ids"]) == 1


def test_a_failing_step_does_not_stop_the_tick(tmp_path, web, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")

    def boom(ctx, **kw):
        raise RuntimeError("search is down")

    monkeypatch.setattr(req_mod, "handle_requests", boom)
    out = _run(tmp_path, web, trigger="schedule")
    assert out["status"] == "partial" and out["delivery"]["counts"]["linkedin"] == 3
    desk = json.loads((tmp_path / "data" / "desk" / "desk.json").read_text())
    run = desk["runs"][0]
    assert run["status"] == "partial" and run["errors"][0]["where"] == "requests"


def test_daylight_saving_change_neither_skips_nor_doubles(tmp_path, make_ctx):
    # Morning cron 18:11 UTC: Sat 3 Oct is AEST (04:11 local), Sun 4 Oct is AEDT (05:11 local).
    timeutil.freeze("2026-10-02T18:11:00Z")
    ctx = make_ctx()
    assert ctx.local_date_str() == "2026-10-03" and delivery_due(ctx)
    timeutil.freeze("2026-10-03T18:11:00Z")
    ctx2 = make_ctx()
    assert ctx2.local_date_str() == "2026-10-04" and ctx2.local_now().strftime("%H:%M") == "05:11"
    assert delivery_due(ctx2)


def test_delivery_not_due_before_earliest_time(make_ctx):
    timeutil.freeze("2026-09-27T16:30:00Z")  # 02:30 AEST
    assert not delivery_due(make_ctx())


def test_weekly_schedules(make_ctx):
    timeutil.freeze("2026-10-03T08:00:00Z")  # Sat 18:00 AEST
    assert not weekly_batch_due(make_ctx())
    timeutil.freeze("2026-10-03T09:30:00Z")  # Sat 19:30 AEST
    assert weekly_batch_due(make_ctx())
    timeutil.freeze("2026-10-04T06:00:00Z")  # Sun afternoon: reflection only on request
    assert not reflection_due(make_ctx())
    timeutil.freeze("2026-10-04T18:30:00Z")  # Mon 05:30 AEDT: fallback
    assert reflection_due(make_ctx())


def test_run_request_force_gives_another_set(tmp_path, web, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    _run(tmp_path, web, trigger="schedule")
    write_inbox(tmp_path / "data", [{"id": "more", "type": "run.request", "tasks": ["morning"], "force": True}])
    out = _run(tmp_path, web, trigger="dispatch", hints={"morning"}, force=True)
    assert out["delivery"]["id"].endswith("_2")


def test_offline_ctx_has_no_real_network(make_ctx, web):
    ctx: Ctx = make_ctx()
    tick.run(ctx.data_root, transport=web.transport(), llm_providers=fake_providers(), sleep=lambda s: None,
             send_notifications=False)
    assert web.requests and all("http" in u for u in web.requests)


def test_a_run_where_no_model_answers_is_partial_says_why_and_still_delivers_briefs(tmp_path, web, monkeypatch):
    from conftest import PROVIDERS

    from pbs.llm.base import LLMError
    from pbs.llm.fake import FakeProvider

    monkeypatch.setenv("GEMINI_API_KEY", "x")
    retired = LLMError("unreadable response body (HTTP 200, text/html, 900 bytes)", status=200, code="bad_body",
                       fatal_for_provider=True)
    dead = {n: FakeProvider(n, fail_with=retired) for n in PROVIDERS}
    out = tick.run(tmp_path / "data", transport=web.transport(), llm_providers=dead, sleep=lambda s: None,
                   send_notifications=False, trigger="schedule")
    assert out["status"] == "partial" and out["llm_calls"] == 0 and out["llm_failures"] == len(PROVIDERS)
    assert out["delivery"]["counts"] == {"linkedin": 3, "x": 6}  # the full set, as briefs
    assert sum(len(p.calls) for p in dead.values()) == len(PROVIDERS)  # each tried once, then switched off
    desk = json.loads((tmp_path / "data" / "desk" / "desk.json").read_text())
    DeskState.model_validate(desk)
    run = desk["runs"][0]
    assert run["degraded"] == "brief_cards"
    assert any(n.startswith("No model call succeeded in this run: gemini: unreadable response (HTTP 200)")
               for n in run["notes"])
    assert "llm_failing" in {w["code"] for w in desk["warnings"]}
    external = [c for c in desk["cards"] if c.get("delivery_id") == out["delivery"]["id"] and c["mode"] == "external"]
    assert external and all(c["draft_state"] == "brief" for c in external)
    assert "model providers returned errors" in " ".join(external[0]["flags"]["notes"])


def test_doctor_only_checks_and_never_delivers(tmp_path, monkeypatch, capsys):
    from pbs import cli
    from pbs.store import Store

    monkeypatch.setenv("PBS_PUBLIC_LOGS", "1")
    assert cli.main(["doctor", "--offline", "--data", str(tmp_path / "diag")]) == 0
    out = capsys.readouterr().out
    assert "doctor: ok   Model: gemini (fake-1)" in out and "doctor: warn Secret: PBS_BLOCKLIST" in out
    store = Store.open(tmp_path / "diag")
    assert store.count("doctor_reports") == 1 and store.count("deliveries") == 0 and store.count("cards") == 0


def test_a_public_data_repo_shows_as_an_alert_and_a_failed_doctor_check(tmp_path, web, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("PBS_DATA_PUBLIC", "1")
    out = _run(tmp_path, web, trigger="dispatch", hints={"doctor"})
    desk = json.loads((tmp_path / "data" / "desk" / "desk.json").read_text())
    assert "data_public" in {w["code"] for w in desk["warnings"]} and out["status"] in ("ok", "partial")
    check = next(c for c in desk["doctor"]["checks"] if c["name"] == "Data repo private")
    assert check["status"] == "fail"
