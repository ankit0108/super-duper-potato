from __future__ import annotations

import json
from pathlib import Path

import pytest

from pbs import ids, timeutil
from pbs.context import Ctx
from pbs.demo.web import MockWeb
from pbs.llm.fake import FakeProvider
from pbs.settings import load
from pbs.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
PROVIDERS = ["gemini", "gemini_lite", "github", "github_strong", "groq", "openrouter"]


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    # Monday 28 Sep 2026, 05:45 Melbourne (AEST, UTC+10)
    timeutil.freeze("2026-09-27T19:45:00Z")
    ids.seed(7)
    for var in ("PBS_BLOCKLIST", "GEMINI_API_KEY", "GITHUB_TOKEN", "PBS_NTFY_TOPIC", "PBS_TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    yield
    timeutil.freeze(None)


@pytest.fixture
def store(tmp_path) -> Store:
    return Store.open(tmp_path / "data")


@pytest.fixture
def settings():
    s, warnings = load()
    assert not warnings
    return s


def fake_providers(**handlers):
    return {n: FakeProvider(n, handlers=handlers or None) for n in PROVIDERS}


@pytest.fixture
def web():
    return MockWeb()


@pytest.fixture
def make_ctx(tmp_path, web, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")

    def _make(root=None, providers=None, **kw):
        return Ctx.create(root or (tmp_path / "data"), transport=web.transport(),
                          llm_providers=providers or fake_providers(), sleep=lambda s: None, **kw)

    return _make


def write_inbox(root, events, name="batch"):
    folder = root / "inbox"
    folder.mkdir(parents=True, exist_ok=True)
    body = {"v": 1, "id": f"evb_{name}", "device": "test", "created_at": "2026-09-27T20:00:00Z",
            "events": [{"at": "2026-09-27T20:00:00Z", **e} for e in events]}
    (folder / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")
