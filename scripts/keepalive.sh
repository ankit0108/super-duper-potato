#!/usr/bin/env bash
# GitHub disables schedules in repos without activity for 60 days. Re-enabling the workflow through the
# API keeps it alive without dummy commits. The desk also warns if runs go stale.
set -euo pipefail
if [ -z "${GH_TOKEN:-}" ] || [ -z "${GITHUB_REPOSITORY:-}" ]; then exit 0; fi
curl -fsS -X PUT \
  -H "Authorization: Bearer ${GH_TOKEN}" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_REPOSITORY}/actions/workflows/pbs.yml/enable" >/dev/null \
  && echo "Schedule kept alive." || echo "Keepalive skipped."
