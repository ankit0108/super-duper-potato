#!/usr/bin/env bash
# Check out PBS state into $PBS_DATA_DIR.
#   Recommended: a separate PRIVATE repo (set repo variable PBS_DATA_REPO=owner/name and secret PBS_DATA_TOKEN).
#   Alternative: the 'data' branch of this repo, allowed only when this repo is private.
# Before the run starts it checks that the token can read AND push, so a token problem fails in seconds with
# the fix spelled out, instead of after a whole run whose results can't be saved.
set -euo pipefail

DIR="${PBS_DATA_DIR:-.pbs-data}"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/git-errors.sh
. "$SCRIPTS/git-errors.sh"

GITHUB_REPO=""
if [ -n "${PBS_DATA_URL:-}" ]; then
  # Explicit remote (tests, self-hosted git).
  BRANCH="${PBS_DATA_BRANCH:-main}"
  URL="$PBS_DATA_URL"
elif [ -n "${PBS_DATA_REPO:-}" ]; then
  if [ -z "${PBS_DATA_TOKEN:-}" ]; then
    echo "::error::PBS_DATA_REPO is set but the PBS_DATA_TOKEN secret is missing (fine-grained token, Contents: read and write on ${PBS_DATA_REPO})."
    exit 1
  fi
  BRANCH="${PBS_DATA_BRANCH:-main}"
  echo "::add-mask::${PBS_DATA_TOKEN}"
  URL="https://x-access-token:${PBS_DATA_TOKEN}@github.com/${PBS_DATA_REPO}.git"
  TOKEN="$PBS_DATA_TOKEN"
  GITHUB_REPO="$PBS_DATA_REPO"
  export PBS_TOKEN_NAME="PBS_DATA_TOKEN"
else
  if [ "${REPO_PRIVATE:-false}" != "true" ]; then
    echo "::error::This code repo is public, so PBS will not store personal data in it. Create a private repo (for example pbs-data), set the repo variable PBS_DATA_REPO and the secret PBS_DATA_TOKEN. See docs/SETUP.md."
    exit 1
  fi
  BRANCH="${PBS_DATA_BRANCH:-data}"
  URL="https://x-access-token:${GITHUB_TOKEN}@github.com/${GH_REPO}.git"
  TOKEN="$GITHUB_TOKEN"
  GITHUB_REPO="$GH_REPO"
  export PBS_TOKEN_NAME="GITHUB_TOKEN"
fi
export PBS_TARGET_REPO="${GITHUB_REPO:-the data repo}"

rm -rf "$DIR"
ERR="$(mktemp)"
trap 'rm -f "$ERR"' EXIT
# Without --exit-code, ls-remote succeeds with no output when the repo is readable but the branch is new;
# any failure means the repo couldn't be read at all, which must not be mistaken for "no data yet".
if ! REFS="$(git ls-remote --heads "$URL" "$BRANCH" 2>"$ERR")"; then
  explain_git_failure read "$(cat "$ERR")"
  exit 1
fi

if [ -n "$GITHUB_REPO" ]; then
  # GitHub answers the push handshake with 403 when the token may read but not write.
  B64="$(printf 'x-access-token:%s' "$TOKEN" | base64 | tr -d '\n')"
  CODE="$(printf 'header = "Authorization: Basic %s"\n' "$B64" | curl -sS -o /dev/null -w '%{http_code}' \
    --max-time 20 -K - "https://github.com/${GITHUB_REPO}.git/info/refs?service=git-receive-pack" 2>/dev/null || true)"
  case "$CODE" in
    200) ;;
    401|403|404) explain_git_failure write "The requested URL returned error: ${CODE}"; exit 1 ;;
    *) echo "::warning::Couldn't confirm push access to ${GITHUB_REPO} (HTTP ${CODE:-none}); carrying on." ;;
  esac
fi

if [ -n "$REFS" ]; then
  git clone -q --depth 1 --branch "$BRANCH" "$URL" "$DIR"
  echo "Data checked out (${BRANCH})."
else
  echo "No '${BRANCH}' branch yet: starting fresh state."
  mkdir -p "$DIR"
  git -C "$DIR" init -q -b "$BRANCH"
  git -C "$DIR" remote add origin "$URL"
  pbs init --data "$DIR"
fi
git -C "$DIR" config user.name "pbs-bot"
git -C "$DIR" config user.email "pbs-bot@users.noreply.github.com"
