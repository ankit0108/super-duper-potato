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


GITHUB_403 = ("remote: Write access to repository not granted.\n"
              "fatal: unable to access 'https://github.com/ankit/pbs-data.git/': The requested URL returned error: 403")


def fake_tools(tmp_path: Path, git_fail: dict[str, str] | None = None, http_code: str = "200",
               api_code: str = "404") -> dict[str, str]:
    """Put stand-ins for git (failing the given subcommands with GitHub's messages) and curl on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    real_git = shutil.which("git")
    cases = "".join(f'  {sub}) printf "%s\\n" {json.dumps(msg)} >&2; exit 128 ;;\n'
                    for sub, msg in (git_fail or {}).items())
    log = tmp_path / "git-calls.log"
    (bin_dir / "git").write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> {log}\nfor a in "$@"; do case "$a" in\n{cases}'
                                 f'  ls-remote) exit 0 ;;\nesac; done\nexec {real_git} "$@"\n')
    # The push check answers `http_code`; the anonymous visibility check (api.github.com) answers `api_code`.
    (bin_dir / "curl").write_text(f'#!/usr/bin/env bash\ncase "$*" in *api.github.com*) printf "{api_code}"; exit 0 ;; esac\n'
                                  f'cat >/dev/null\nprintf "{http_code}"\n')
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    e = dict(os.environ)
    e.pop("PBS_DATA_URL", None)
    e.update(PATH=f"{bin_dir}:{Path(sys.executable).parent}:{e.get('PATH', '')}", PBS_DATA_REPO="ankit/pbs-data",
             PBS_DATA_TOKEN="tok", PBS_DATA_DIR=str(tmp_path / "work"))
    return e


def run_script(name: str, e: dict[str, str], cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(ROOT / "scripts" / name), *args], cwd=cwd, env=e, capture_output=True, text=True,
                          timeout=60)


def test_a_token_that_cannot_read_the_data_repo_stops_before_the_run(tmp_path):
    e = fake_tools(tmp_path, git_fail={"ls-remote": GITHUB_403})
    out = run_script("data-checkout.sh", e, tmp_path)
    assert out.returncode == 1
    assert "PBS_DATA_TOKEN can't read ankit/pbs-data (HTTP 403)" in out.stdout
    assert "GitHub said: Write access to repository not granted." in out.stdout
    assert 'Contents set to "Read and write"' in out.stdout
    assert "starting fresh" not in out.stdout and not (tmp_path / "work").exists()


def test_a_read_only_token_stops_before_the_run(tmp_path):
    e = fake_tools(tmp_path, http_code="403")
    out = run_script("data-checkout.sh", e, tmp_path)
    assert out.returncode == 1
    assert "PBS_DATA_TOKEN can read ankit/pbs-data but can't push to it (HTTP 403)" in out.stdout


def test_a_missing_data_repo_says_so(tmp_path):
    e = fake_tools(tmp_path, git_fail={"ls-remote": "remote: Repository not found.\nfatal: repository "
                                                    "'https://github.com/ankit/pbs-data.git/' not found"})
    out = run_script("data-checkout.sh", e, tmp_path)
    assert out.returncode == 1 and "PBS_DATA_TOKEN can't see ankit/pbs-data (HTTP 404)" in out.stdout
    assert "GitHub said: Repository not found." in out.stdout and "Resource owner ankit," in out.stdout


def test_an_unreadable_local_remote_is_not_mistaken_for_a_new_one(tmp_path):
    e = dict(os.environ)
    e.update(PBS_DATA_URL=str(tmp_path / "missing.git"), PBS_DATA_DIR=str(tmp_path / "work"))
    out = run_script("data-checkout.sh", e, tmp_path)
    assert out.returncode == 1 and "Couldn't read the data repo" in out.stdout
    assert not (tmp_path / "work").exists()


def test_push_refused_for_access_fails_at_once_with_the_fix(tmp_path):
    work = tmp_path / "work"
    git("init", "-q", "-b", "main", str(work), cwd=tmp_path)
    git("remote", "add", "origin", "https://github.com/ankit/pbs-data.git", cwd=work)
    (work / "state.txt").write_text("x")
    e = fake_tools(tmp_path, git_fail={"push": GITHUB_403})
    e.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
    out = run_script("data-push.sh", e, tmp_path, "pbs: test")
    assert out.returncode == 1
    assert "PBS_DATA_TOKEN can read ankit/pbs-data but can't push to it (HTTP 403)" in out.stdout
    assert "rebasing" not in out.stdout and "attempt" not in out.stdout


def test_git_checks_clear_the_workspace_credentials(tmp_path):
    # actions/checkout leaves the workflow's token in the workspace's git config; git would send it instead of
    # PBS_DATA_TOKEN, and a private data repo answers 404 (the first live runs). Every data git call clears it.
    e = fake_tools(tmp_path, http_code="200")
    out = run_script("data-checkout.sh", e, tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr
    calls = (tmp_path / "git-calls.log").read_text().splitlines()
    ls_remote = [c for c in calls if " ls-remote " in f" {c} "]
    assert ls_remote and all(c.startswith("-c http.https://github.com/.extraheader= ") for c in ls_remote)


def test_a_public_data_repo_is_flagged_for_the_run_and_the_desk(tmp_path):
    e = fake_tools(tmp_path, api_code="200")
    e["GITHUB_ENV"] = str(tmp_path / "github.env")
    out = run_script("data-checkout.sh", e, tmp_path)
    assert out.returncode == 0 and "::warning::ankit/pbs-data is public" in out.stdout
    assert (tmp_path / "github.env").read_text() == "PBS_DATA_PUBLIC=1\n"
