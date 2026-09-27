#!/usr/bin/env bash
# Check out PBS state into $PBS_DATA_DIR.
#   Recommended: a separate PRIVATE repo (set repo variable PBS_DATA_REPO=owner/name and secret PBS_DATA_TOKEN).
#   Alternative: the 'data' branch of this repo, allowed only when this repo is private.
set -euo pipefail

DIR="${PBS_DATA_DIR:-.pbs-data}"

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
  URL="https://x-access-token:${PBS_DATA_TOKEN}@github.com/${PBS_DATA_REPO}.git"
  echo "::add-mask::${PBS_DATA_TOKEN}"
else
  if [ "${REPO_PRIVATE:-false}" != "true" ]; then
    echo "::error::This code repo is public, so PBS will not store personal data in it. Create a private repo (for example pbs-data), set the repo variable PBS_DATA_REPO and the secret PBS_DATA_TOKEN. See docs/SETUP.md."
    exit 1
  fi
  BRANCH="${PBS_DATA_BRANCH:-data}"
  URL="https://x-access-token:${GITHUB_TOKEN}@github.com/${GH_REPO}.git"
fi

rm -rf "$DIR"
if git ls-remote --exit-code --heads "$URL" "$BRANCH" >/dev/null 2>&1; then
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
