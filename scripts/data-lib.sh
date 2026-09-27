# Shared by the data scripts: git without the workspace's credentials, and errors that say what to fix.
# Reads PBS_TOKEN_NAME (the secret that holds the token) and PBS_TARGET_REPO (owner/name), when known.
# shellcheck shell=bash

# actions/checkout leaves the workflow's own token in the workspace's git config
# (http.https://github.com/.extraheader). Git run from the workspace sends that header instead of the data
# token in the URL, so a private data repo answers 404 "Repository not found". The empty value clears it.
data_git() {
  git -c "http.https://github.com/.extraheader=" "$@"
}

is_access_failure() {
  case "$1" in
    *"error: 401"*|*"error: 403"*|*"error: 404"*|*"not granted"*|*"Permission to"*|*"Authentication failed"*|\
    *"could not read Username"*|*"Invalid username or password"*|*"Repository not found"*|*"hook declined"*|\
    *"protected branch"*) return 0 ;;
  esac
  return 1
}

# GitHub's own one-line reason (its "remote:" lines carry no secrets or personal content). Never fails,
# since the callers run under `set -e` and most failures have no such line.
github_said() {
  printf '%s\n' "$1" | sed -n 's/^remote: *\([^[:space:]].*\)$/\1/p' | sed -n '1p'
}

explain_git_failure() {
  local op="$1" msg="$2" token="${PBS_TOKEN_NAME:-the token}" repo="${PBS_TARGET_REPO:-the data repo}" fix said why
  said="$(github_said "$msg")"
  why="${said:+ GitHub said: ${said%.}.}"
  if [ "$token" = "GITHUB_TOKEN" ]; then
    fix="The workflow's GITHUB_TOKEN needs 'contents: write' (see permissions in .github/workflows/pbs.yml)."
  else
    fix="Fix the token at github.com/settings/personal-access-tokens: Resource owner ${repo%%/*}, Repository access including ${repo##*/}, and Repository permissions → Contents set to \"Read and write\" (a classic token needs the repo scope instead). If you create a new token, paste it into the ${token} secret."
  fi
  case "$msg" in
    *"hook declined"*|*"protected branch"*)
      echo "::error::${repo} refused the push (a branch protection rule or hook).${why} Let ${token} push to the data branch." ;;
    *"error: 403"*|*"not granted"*|*"Permission to"*)
      if [ "$op" = read ]; then
        echo "::error::${token} can't read ${repo} (HTTP 403).${why} ${fix}"
      else
        echo "::error::${token} can read ${repo} but can't push to it (HTTP 403).${why} ${fix}"
      fi ;;
    *"error: 404"*|*"Repository not found"*|*"not found"*)
      if [ "$op" = read ]; then
        echo "::error::${token} can't see ${repo} (HTTP 404).${why} Either no repo has that name (check the PBS_DATA_REPO variable and github.com/${repo}), or the token isn't allowed to see it. ${fix}"
      else
        echo "::error::${token} can read ${repo} but GitHub hid the push endpoint from it (HTTP 404). ${fix}"
      fi ;;
    *"error: 401"*|*"Authentication failed"*|*"could not read Username"*|*"Invalid username or password"*)
      echo "::error::GitHub rejected ${token} (HTTP 401): it has expired, been revoked or was pasted incompletely.${why} Create a new token and update the ${token} secret." ;;
    *)
      echo "::error::Couldn't ${op} ${repo}: $(printf '%s\n' "$msg" | grep -v '^[[:space:]]*$' | tail -n 2 | tr '\n' ' ')" ;;
  esac
}
