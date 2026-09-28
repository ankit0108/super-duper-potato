"""Command line: `pbs tick`, `pbs doctor`, `pbs init`, `pbs export`, `pbs schema`, `pbs demo`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__, log


def _data_dir(arg: str | None) -> Path:
    return Path(arg or os.environ.get("PBS_DATA_DIR") or ".pbs-data").resolve()


def _offline_kwargs(offline: bool) -> dict[str, Any]:
    if not offline:
        return {}
    from .demo.web import MockWeb
    from .llm.fake import FakeProvider
    from .settings import load

    settings, _ = load()
    os.environ.setdefault("GEMINI_API_KEY", "offline")
    return {"transport": MockWeb().transport(),
            "llm_providers": {name: FakeProvider(name) for name in settings.llm.providers},
            "sleep": lambda s: None}


def cmd_tick(args: argparse.Namespace) -> int:
    from . import tick

    hints = {h.strip() for h in (args.hint or "").split(",") if h.strip()}
    unknown = hints - tick.TASKS
    if unknown:
        print(f"unknown hint(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    summary = tick.run(_data_dir(args.data), trigger=args.trigger, hints=hints, force=args.force,
                       send_notifications=not args.no_notify, **_offline_kwargs(args.offline))
    print(json.dumps(summary, indent=1))
    return 0 if summary.get("status") != "failed" else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    """Only the checks (secrets, every model provider, every source): no delivery, so it's safe to run anytime,
    even against an empty data directory when the real data can't be reached."""
    from . import doctor, export
    from .context import Ctx
    from .scout.sources import sync_seeds

    ctx = Ctx.create(_data_dir(args.data), task="doctor", trigger="manual", **_offline_kwargs(args.offline))
    sync_seeds(ctx.store)
    with ctx.run.step("doctor") as step:
        step["summary"] = doctor.run_doctor(ctx)["summary"]
    ctx.run.finish(ctx.llm.usage.as_dict() if ctx._router else {})
    export.write(ctx)
    ctx.store.save()
    summary = step.get("summary") or {}
    print(json.dumps(summary))
    return 1 if summary.get("fail") or "summary" not in step else 0


def cmd_init(args: argparse.Namespace) -> int:
    from . import export, playbook, stances
    from .context import Ctx
    from .scout.sources import sync_seeds

    root = _data_dir(args.data)
    ctx = Ctx.create(root, task="init", trigger="manual")
    added = sync_seeds(ctx.store)
    seeded = stances.ensure_seeded(ctx)
    playbook.ensure_seed(ctx)
    (root / "inbox" / "blobs").mkdir(parents=True, exist_ok=True)
    (root / "inbox" / "blobs" / ".gitkeep").touch()
    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(DATA_README, encoding="utf-8")
    ctx.run.finish()
    export.write(ctx)
    changed = ctx.store.save()
    print(f"Initialised {root}: {added} sources, {seeded} stances, {len(changed)} files written.")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from . import export
    from .context import Ctx

    ctx = Ctx.create(_data_dir(args.data), task="export")
    path = export.write(ctx)
    print(path)
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    from .contracts import json_schema

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(json_schema(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(out)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .demo.build import build_demo

    path = build_demo(Path(args.out), data_dir=Path(args.data) if args.data else None)
    print(path)
    return 0


DATA_README = """# PBS data (private)

This repository is written by the Personal Brand System. Keep it **private**.

- `db/` — state as JSON Lines, one table per file (written by the pipeline only)
- `desk/desk.json` — what the desk renders (written by the pipeline only)
- `inbox/` — events from the desk (written by the desk only; the pipeline ingests and deletes them)
- `media/` — processed analytics screenshots (kept 60 days)
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pbs", description="Personal Brand System")
    parser.add_argument("--version", action="version", version=f"pbs {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("tick", help="run everything that is due")
    p.add_argument("--data", help="data directory (default: $PBS_DATA_DIR or .pbs-data)")
    p.add_argument("--trigger", default="manual", help="schedule | dispatch | manual")
    p.add_argument("--hint", default="", help="comma-separated tasks: morning,weekly_batch,reflection,doctor,scout,platform_research")
    p.add_argument("--force", action="store_true", help="force hinted tasks (e.g. another morning set)")
    p.add_argument("--offline", action="store_true", help="fake model + mock web (no network, no keys)")
    p.add_argument("--no-notify", action="store_true")
    p.set_defaults(fn=cmd_tick)

    p = sub.add_parser("doctor", help="check providers, secrets and sources")
    p.add_argument("--data")
    p.add_argument("--offline", action="store_true")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("init", help="create and seed a data directory")
    p.add_argument("--data")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("export", help="rewrite desk/desk.json")
    p.add_argument("--data")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("schema", help="write the desk contract JSON Schema")
    p.add_argument("--out", default="web/src/types/contracts.schema.json")
    p.set_defaults(fn=cmd_schema)

    p = sub.add_parser("demo", help="build demo data for the desk (offline)")
    p.add_argument("--out", default="web/public/demo")
    p.add_argument("--data", help="keep the demo data directory here")
    p.set_defaults(fn=cmd_demo)

    args = parser.parse_args(argv)
    try:
        return int(args.fn(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        log.error(f"cli:{args.cmd}", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
