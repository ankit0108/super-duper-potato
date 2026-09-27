# Turn git/GitHub failures into an error that says exactly what to fix. Sourced by the data scripts.
# Reads PBS_TOKEN_NAME (the secret that holds the token) and PBS_TARGET_REPO (owner/name), when known.
# shellcheck shell=bash

is_access_failure() {
  case "$1" in
    *"error: 401"*|*"error: 403"*|*"error: 404"*|*"not granted"*|*"Permission to"*|*"Authentication failed"*|\
    *"could not read Username"*|*"Invalid username or password"*|*"Repository not found"*|*"hook declined"*|\
    *"protected branch"*) return 0 ;;
  esac
  return 1
}

explain_git_failure() {
  local op="$1" msg="$2" token="${PBS_TOKEN_NAME:-the token}" repo="${PBS_TARGET_REPO:-the data repo}" fix
  if [ "$token" = "GITHUB_TOKEN" ]; then
    fix="The workflow's GITHUB_TOKEN needs 'contents: write' (see permissions in .github/workflows/pbs.yml)."
  else
    fix="Edit the token (GitHub → Settings → Developer settings → Fine-grained tokens): Repository access must include ${repo##*/}, and Repository permissions → Contents must be \"Read and write\". If you create a new token instead, update the ${token} secret."
  fi
  case "$msg" in
    *"hook declined"*|*"protected branch"*)
      echo "::error::${repo} refused the push (a branch protection rule or hook). Let ${token} push to the data branch." ;;
    *"error: 403"*|*"not granted"*|*"Permission to"*)
      if [ "$op" = read ]; then
        echo "::error::${token} can't read ${repo} (HTTP 403). ${fix}"
      else
        echo "::error::${token} can read ${repo} but can't push to it (HTTP 403). ${fix}"
      fi ;;
    *"error: 404"*|*"Repository not found"*)
      echo "::error::${repo} wasn't found with ${token} (HTTP 404). Check that the PBS_DATA_REPO variable is owner/name, that the repo exists, and that the token's Repository access includes it." ;;
    *"error: 401"*|*"Authentication failed"*|*"could not read Username"*|*"Invalid username or password"*)
      echo "::error::GitHub rejected ${token} (HTTP 401): it has expired, been revoked or was pasted incompletely. Create a new token and update the ${token} secret." ;;
    *)
      echo "::error::Couldn't ${op} ${repo}: $(printf '%s\n' "$msg" | grep -v '^[[:space:]]*$' | tail -n 2 | tr '\n' ' ')" ;;
  esac
}
