#!/usr/bin/env bash
# Commit and push PBS state. The desk only ever adds new files under inbox/, and the pipeline only
# deletes processed inbox files and rewrites db/ and desk/, so a rebase on top of desk writes never conflicts.
# Access problems (expired token, read-only token) stop at once with the fix; only races and network
# errors are retried.
set -euo pipefail

DIR="${PBS_DATA_DIR:-.pbs-data}"
MSG="${1:-pbs: tick}"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/data-lib.sh
. "$SCRIPTS/data-lib.sh"
if [ -z "${PBS_TOKEN_NAME:-}" ]; then
  if [ -n "${PBS_DATA_REPO:-}" ]; then export PBS_TOKEN_NAME="PBS_DATA_TOKEN" PBS_TARGET_REPO="$PBS_DATA_REPO"; fi
fi

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
  if OUT="$(data_git push -q origin "HEAD:${BRANCH}" 2>&1)"; then
    echo "Data saved."
    exit 0
  fi
  if is_access_failure "$OUT"; then
    explain_git_failure push "$OUT"
    exit 1
  fi
  case "$OUT" in
    *"rejected"*|*"non-fast-forward"*|*"fetch first"*)
      echo "Push rejected (the desk wrote meanwhile); rebasing, attempt ${attempt}." ;;
    *)
      echo "Push failed ($(printf '%s\n' "$OUT" | grep -v '^[[:space:]]*$' | tail -n 1)); retrying, attempt ${attempt}." ;;
  esac
  if ! data_git pull -q --rebase origin "$BRANCH" 2>/dev/null; then
    git rebase --abort 2>/dev/null || true
  fi
  sleep $((attempt * 2))
done
echo "::error::Could not save data after 5 attempts."
exit 1
