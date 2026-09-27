"""Logging that is safe for public Actions logs.

When PBS_PUBLIC_LOGS=1 (set in the workflows of a public code repo), console output carries only
counts, IDs and error classes. Anything that may contain personal content goes through
`private()` and is kept in the run record inside the private data repo.
"""

from __future__ import annotations

import os
import sys
import traceback
from dataclasses import dataclass, field

from . import timeutil


def public_mode() -> bool:
    return os.environ.get("PBS_PUBLIC_LOGS", "0") == "1"


@dataclass
class RunJournal:
    """Collects private detail for the run record (stored in the private data repo)."""

    lines: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def add(self, line: str) -> None:
        self.lines.append(f"{timeutil.now_iso()} {line}")
        if len(self.lines) > 400:
            self.lines = self.lines[-400:]


_journal = RunJournal()


def journal() -> RunJournal:
    return _journal


def reset_journal() -> RunJournal:
    global _journal
    _journal = RunJournal()
    return _journal


def info(msg: str) -> None:
    """Public-safe message: counts, IDs, stage names. Never content."""
    print(f"[pbs] {msg}", file=sys.stdout, flush=True)
    _journal.add(msg)


def warn(msg: str) -> None:
    print(f"[pbs] WARN {msg}", file=sys.stdout, flush=True)
    _journal.add(f"WARN {msg}")


def private(msg: str) -> None:
    """Detail that may include personal content. Printed only outside public mode."""
    _journal.add(msg)
    if not public_mode():
        print(f"[pbs] {msg}", file=sys.stdout, flush=True)


def error(where: str, exc: BaseException) -> dict:
    """Record an exception. Public logs get the class and location only."""
    record = {
        "at": timeutil.now_iso(),
        "where": where,
        "type": type(exc).__name__,
        "message": str(exc)[:2000],
        "trace": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-6000:],
    }
    _journal.errors.append(record)
    if public_mode():
        print(f"[pbs] ERROR in {where}: {type(exc).__name__}", file=sys.stdout, flush=True)
    else:
        print(f"[pbs] ERROR in {where}: {type(exc).__name__}: {exc}", file=sys.stdout, flush=True)
    return record
