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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr) PR="$2"; shift 2 ;;
    --author-pattern) PATTERN="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --since) SINCE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 64 ;;
  esac
done

[[ -n "$PR" ]] || { echo "--pr is required" >&2; usage; exit 64; }

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is not authenticated. Run 'gh auth login' or set GH_TOKEN, then retry." >&2
  exit 69
fi

repo_args=()
[[ -n "$REPO" ]] && repo_args=(--repo "$REPO")

# jq filter: pick reviews whose author login contains the pattern (lowercased),
# optionally submitted at/after --since; return the most recent one (or empty).
pat_lc="$(printf '%s' "$PATTERN" | tr '[:upper:]' '[:lower:]')"
jq_filter="[.reviews[]
  | select(.author.login | ascii_downcase | contains(\"$pat_lc\"))"
if [[ -n "$SINCE" ]]; then
  jq_filter+=" | select(.submittedAt >= \"$SINCE\")"
fi
jq_filter+="] | last // empty"

deadline=$(( $(date +%s) + TIMEOUT ))
echo "Waiting for a review by author ~ '$PATTERN' on PR #$PR (timeout ${TIMEOUT}s, poll ${INTERVAL}s)..." >&2

while :; do
  match="$(gh pr view "$PR" "${repo_args[@]}" --json reviews --jq "$jq_filter" 2>/dev/null || true)"
  if [[ -n "$match" ]]; then
    echo "REVIEW_FOUND" >&2
    echo "$match"
    exit 0
  fi
  now="$(date +%s)"
  if (( now >= deadline )); then
    echo "TIMEOUT: no matching review within ${TIMEOUT}s (re-invoke to keep waiting)." >&2
    exit 2
  fi
  sleep "$INTERVAL"
done
