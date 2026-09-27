"""The data checkout/push scripts against local bare repos: first run, desk writes during a run, rebase."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def sh(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    out = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


def git(*args: str, cwd: Path) -> str:
    return sh(["git", *args], cwd)


@pytest.fixture
def env(tmp_path):
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    e = dict(os.environ)
    e.update(PBS_DATA_URL=str(remote), PBS_DATA_DIR=str(tmp_path / "work"), PBS_DATA_BRANCH="main",
             PATH=f"{Path(sys.executable).parent}:{e.get('PATH', '')}", GIT_AUTHOR_NAME="t",
             GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return e, remote


def tick(e, tmp_path):
    sh([str(ROOT / "scripts/data-checkout.sh")], tmp_path, e)
    sh(["pbs", "tick", "--data", e["PBS_DATA_DIR"], "--offline", "--no-notify"], tmp_path, e)


def test_first_run_creates_state_and_desk_writes_rebase_cleanly(env, tmp_path):
    e, remote = env
    tick(e, tmp_path)
    sh([str(ROOT / "scripts/data-push.sh"), "pbs: first"], tmp_path, e)
    log = git("--git-dir", str(remote), "log", "--oneline", "main", cwd=tmp_path)
    assert "pbs: first" in log

    # Start a second run (checkout), then the desk writes an inbox file before the run pushes.
    sh([str(ROOT / "scripts/data-checkout.sh")], tmp_path, e)
    desk = tmp_path / "desk"
    git("clone", "-q", str(remote), str(desk), cwd=tmp_path)
    (desk / "inbox").mkdir(exist_ok=True)
    (desk / "inbox" / "evb_desk.json").write_text(json.dumps({
        "v": 1, "id": "evb_desk", "created_at": "2026-09-28T01:00:00Z",
        "events": [{"id": "ev_acct", "at": "2026-09-28T01:00:00Z", "type": "account.stats", "date": "2026-09-28",
                    "platform": "x", "followers": 15}]}))
    git("add", "-A", cwd=desk)
    git("-c", "user.name=desk", "-c", "user.email=d@e", "commit", "-q", "-m", "desk: event", cwd=desk)
    git("push", "-q", "origin", "HEAD:main", cwd=desk)

    sh(["pbs", "tick", "--data", e["PBS_DATA_DIR"], "--offline", "--no-notify"], tmp_path, e)
    out = sh([str(ROOT / "scripts/data-push.sh"), "pbs: second"], tmp_path, e)
    assert "rebasing" in out and "Data saved" in out

    # The desk's event survives and is processed by the next run.
    tick(e, tmp_path)
    sh([str(ROOT / "scripts/data-push.sh"), "pbs: third"], tmp_path, e)
    fresh = tmp_path / "check"
    git("clone", "-q", str(remote), str(fresh), cwd=tmp_path)
    stats = (fresh / "db" / "account_stats.jsonl").read_text()
    assert '"followers":15' in stats
    assert not (fresh / "inbox" / "evb_desk.json").exists()


def test_public_repo_without_data_repo_is_refused(tmp_path):
    e = dict(os.environ)
    for k in ("PBS_DATA_URL", "PBS_DATA_REPO"):
        e.pop(k, None)
    e.update(REPO_PRIVATE="false", PBS_DATA_DIR=str(tmp_path / "work"))
    out = subprocess.run([str(ROOT / "scripts/data-checkout.sh")], cwd=tmp_path, env=e, capture_output=True, text=True)
    assert out.returncode == 1 and "public" in out.stdout
