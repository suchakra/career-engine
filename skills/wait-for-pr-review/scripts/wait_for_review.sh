#!/usr/bin/env bash
# Wait (block) until a matching PR review appears — e.g. GitHub Copilot's code
# review — polling gh internally so the caller makes ONE call instead of burning
# tokens on repeated polls.
#
# Exit codes: 0 = matching review found (printed as JSON) · 2 = timeout ·
# 64 = bad args · 69 = gh not authenticated.
set -euo pipefail

PR=""
PATTERN="copilot"      # case-insensitive substring matched against review author login
TIMEOUT=540            # seconds (keep < the 600s Bash-tool cap; re-invoke if it times out)
INTERVAL=30            # seconds between polls
REPO=""                # optional owner/name (defaults to the cwd repo)
SINCE=""               # optional ISO8601; only count reviews submitted at/after this

usage() {
  echo "usage: wait_for_review.sh --pr N [--author-pattern copilot] [--timeout 540] [--interval 30] [--repo owner/name] [--since ISO8601]" >&2
}

# Require that a flag was given a value; otherwise fail with the documented code
# (64) + usage instead of a bare `shift 2` failure under `set -e`.
require_val() {
  # $1 = flag name, $2 = number of args still available (including the flag)
  if [[ "$2" -lt 2 ]]; then
    echo "missing value for $1" >&2
    usage
    exit 64
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr) require_val "$1" "$#"; PR="$2"; shift 2 ;;
    --author-pattern) require_val "$1" "$#"; PATTERN="$2"; shift 2 ;;
    --timeout) require_val "$1" "$#"; TIMEOUT="$2"; shift 2 ;;
    --interval) require_val "$1" "$#"; INTERVAL="$2"; shift 2 ;;
    --repo) require_val "$1" "$#"; REPO="$2"; shift 2 ;;
    --since) require_val "$1" "$#"; SINCE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 64 ;;
  esac
done

[[ -n "$PR" ]] || { echo "--pr is required" >&2; usage; exit 64; }
[[ "$TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { echo "--timeout must be a positive integer" >&2; exit 64; }
[[ "$INTERVAL" =~ ^[1-9][0-9]*$ ]] || { echo "--interval must be a positive integer" >&2; exit 64; }

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is not authenticated. Run 'gh auth login' or set GH_TOKEN, then retry." >&2
  exit 69
fi

repo_args=()
[[ -n "$REPO" ]] && repo_args=(--repo "$REPO")

pat_lc="$(printf '%s' "$PATTERN" | tr '[:upper:]' '[:lower:]')"

# jq program passed values via --arg (never string-interpolated), so a pattern
# or timestamp containing quotes/backslashes/newlines can't corrupt the filter.
# Nulls in author.login / submittedAt are guarded with // "".
jq_prog='[ .reviews[]
  | select(((.author.login // "") | ascii_downcase) | contains($pat))
  | select(($since == "") or ((.submittedAt // "") >= $since)) ]
  | last // empty'

deadline=$(( $(date +%s) + TIMEOUT ))
echo "Waiting for a review by author ~ '$PATTERN' on PR #$PR (timeout ${TIMEOUT}s, poll ${INTERVAL}s)..." >&2

while :; do
  reviews_json="$(gh pr view "$PR" "${repo_args[@]}" --json reviews 2>/dev/null || true)"
  if [[ -n "$reviews_json" ]]; then
    match="$(printf '%s' "$reviews_json" | jq -c --arg pat "$pat_lc" --arg since "$SINCE" "$jq_prog" 2>/dev/null || true)"
    if [[ -n "$match" ]]; then
      echo "REVIEW_FOUND" >&2
      echo "$match"
      exit 0
    fi
  fi
  now="$(date +%s)"
  if (( now >= deadline )); then
    echo "TIMEOUT: no matching review within ${TIMEOUT}s (re-invoke to keep waiting)." >&2
    exit 2
  fi
  sleep "$INTERVAL"
done
