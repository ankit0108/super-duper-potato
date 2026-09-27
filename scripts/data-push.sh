#!/usr/bin/env bash
# Commit and push PBS state. The desk only ever adds new files under inbox/, and the pipeline only
# deletes processed inbox files and rewrites db/ and desk/, so a rebase on top of desk writes never conflicts.
set -euo pipefail

DIR="${PBS_DATA_DIR:-.pbs-data}"
MSG="${1:-pbs: tick}"
[ -d "$DIR/.git" ] || { echo "No data checkout; nothing to save."; exit 0; }
cd "$DIR"
git add -A
if git diff --cached --quiet; then
  echo "No data changes."
  exit 0
fi
git commit -q -m "$MSG"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
for attempt in 1 2 3 4 5; do
  if git push -q origin "HEAD:${BRANCH}" 2>/dev/null; then
    echo "Data saved."
    exit 0
  fi
  echo "Push rejected (the desk wrote meanwhile); rebasing, attempt ${attempt}."
  if ! git pull -q --rebase origin "$BRANCH"; then
    git rebase --abort 2>/dev/null || true
  fi
  sleep $((attempt * 2))
done
echo "::error::Could not save data after 5 attempts."
exit 1
