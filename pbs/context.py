"""Run context: store, settings, LLM router, run recorder. Passed to every pipeline step."""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__, ids, log, timeutil
from .guardrails import load_blocklist
from .settings import Settings
from .settings import load as load_settings
from .store import Store


def settings_from_store(store: Store) -> tuple[Settings, list[str]]:
    overrides = dict(store.get_setting("overrides", {}) or {})
    profile = store.get_setting("profile")
    if profile:
        overrides["profile"] = profile
    return load_settings(overrides)


# Errors that belong to one news source: tracked in source health, not worth flagging the whole run for.
SOURCE_LEVEL = ("parse:", "search:")


class RunRecorder:
    def __init__(self, store: Store, task: str, trigger: str):
        self.store = store
        self.id = ids.new_id("run")
        self.task = task
        self.trigger = trigger
        self.started_at = timeutil.now_iso()
        self.steps: list[dict[str, Any]] = []
        self.notes: list[str] = []
        self.degraded: str | None = None
        self.failed_steps = 0
        self.journal = log.reset_journal()

    @contextmanager
    def step(self, name: str) -> Iterator[dict[str, Any]]:
        """Run a step in isolation: an exception marks it failed and the tick moves on."""
        record: dict[str, Any] = {"name": name, "status": "ok"}
        started = time.monotonic()
        try:
            yield record
        except Exception as exc:  # noqa: BLE001 - isolation is the point
            record["status"] = "failed"
            record["error"] = type(exc).__name__
            self.failed_steps += 1
            log.error(name, exc)
        finally:
            record["secs"] = round(time.monotonic() - started, 2)
            self.steps.append(record)

    def note(self, message: str) -> None:
        if message not in self.notes:
            self.notes.append(message)

    def degrade(self, level: str) -> None:
        order = [None, "fewer_cards", "brief_cards"]
        if order.index(level) > order.index(self.degraded):
            self.degraded = level

    def finish(self, llm_usage: dict[str, Any] | None = None) -> dict[str, Any]:
        ok_steps = sum(1 for s in self.steps if s["status"] == "ok")
        status = "ok" if self.failed_steps == 0 else ("partial" if ok_steps else "failed")
        usage = llm_usage or {}
        if usage.get("failures") and not usage.get("calls"):
            # Nothing a model was asked for came back: the run "worked", but not the way it should have.
            errors = usage.get("provider_errors") or {}
            self.note("No model call succeeded in this run" + (
                ": " + "; ".join(f"{p}: {e}" for p, e in sorted(errors.items())) if errors else "") + ".")
            if status == "ok":
                status = "partial"
        elif status == "ok" and any(not e["where"].startswith(SOURCE_LEVEL) for e in self.journal.errors):
            status = "partial"  # a card, request or event failed even though its step carried on
        row = {
            "id": self.id,
            "task": self.task,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "ended_at": timeutil.now_iso(),
            "status": status,
            "steps": self.steps,
            "llm": llm_usage or {},
            "errors": [{k: e[k] for k in ("where", "type", "message", "at")} for e in self.journal.errors],
            "degraded": self.degraded,
            "notes": self.notes,
            "journal": {"lines": self.journal.lines[-200:], "traces": [e["trace"] for e in self.journal.errors][-5:]},
            "versions": {"app": __version__},
        }
        self.store.upsert("runs", row)
        return row


@dataclass
class Ctx:
    store: Store
    settings: Settings
    run: RunRecorder
    data_root: Path
    trigger: str = "manual"
    hints: set[str] = field(default_factory=set)
    force: bool = False
    blocklist: list[str] = field(default_factory=list)
    settings_warnings: list[str] = field(default_factory=list)
    transport: Any = None
    llm_providers: dict[str, Any] | None = None
    sleep: Any = None
    _router: Any = None
    # Inbox files ingested by this run: deleted once the store that includes them is saved (inbox.cleanup).
    inbox_consumed: list[Path] = field(default_factory=list)
    # "Get fresh posts" options from the desk: {"platforms": [...] | None, "per_platform": n | None,
    # "find_sources": bool}. None: the morning set as configured.
    fresh: dict[str, Any] | None = None

    @classmethod
    def create(cls, data_root: str | Path, task: str = "tick", trigger: str = "manual", hints: set[str] | None = None,
               force: bool = False, transport: Any = None, llm_providers: dict[str, Any] | None = None,
               sleep: Any = None) -> Ctx:
        store = Store.open(data_root)
        settings, warnings = settings_from_store(store)
        ctx = cls(
            store=store,
            settings=settings,
            run=RunRecorder(store, task, trigger),
            data_root=Path(data_root),
            trigger=trigger,
            hints=set(hints or ()),
            force=force,
            blocklist=load_blocklist(),
            settings_warnings=warnings,
            transport=transport,
            llm_providers=llm_providers,
            sleep=sleep,
        )
        for w in warnings:
            log.warn(w)
        return ctx

    @property
    def llm(self) -> Any:
        if self._router is None:
            from .llm.router import Router

            kwargs: dict[str, Any] = {"providers": self.llm_providers} if self.llm_providers else {}
            if self.sleep is not None:
                kwargs["sleep"] = self.sleep
            self._router = Router(self.settings, self.store, self.blocklist, **kwargs)
        return self._router

    def reload_settings(self) -> None:
        self.settings, self.settings_warnings = settings_from_store(self.store)
        if self._router is not None:
            self._router.settings = self.settings

    @property
    def tz(self) -> str:
        return self.settings.timezone

    def local_now(self) -> dt.datetime:
        return timeutil.local(timeutil.now(), self.tz)

    def local_date(self) -> dt.date:
        return self.local_now().date()

    def local_date_str(self) -> str:
        return self.local_date().isoformat()
