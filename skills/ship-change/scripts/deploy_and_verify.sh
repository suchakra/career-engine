#!/usr/bin/env bash
# Merge a PR (optional), trigger the GitHub Actions deploy workflow, wait for that
# run to finish, and verify the Cloud Run service is live (HTTP 200). One blocking
# call instead of hand-rolled dispatch + poll + curl each time.
#
# Deploy is done by GitHub Actions (deploy.yml); this script only TRIGGERS it and
# verifies — nothing is built or `terraform apply`-ed locally.
#
# Exit codes: 0 = live (HTTP 200) · 2 = deploy run failed/timed out ·
# 3 = service reachable but not 200 · 64 = bad args · 69 = missing prerequisite.
set -euo pipefail

PR=""
NO_MERGE=0
ENVIRONMENT="dev"
WORKFLOW="deploy.yml"
SERVICE="career-engine-dev-app"
REGION="us-central1"
URL=""
TIMEOUT=600            # seconds to wait for the deploy run to complete
INTERVAL=20

usage() {
  echo "usage: deploy_and_verify.sh [--pr N] [--no-merge] [--env dev] [--service NAME] [--region R] [--url URL] [--timeout 600]" >&2
}
require_val() { if [[ "$2" -lt 2 ]]; then echo "missing value for $1" >&2; usage; exit 64; fi; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr) require_val "$1" "$#"; PR="$2"; shift 2 ;;
    --no-merge) NO_MERGE=1; shift ;;
    --env) require_val "$1" "$#"; ENVIRONMENT="$2"; shift 2 ;;
    --service) require_val "$1" "$#"; SERVICE="$2"; shift 2 ;;
    --region) require_val "$1" "$#"; REGION="$2"; shift 2 ;;
    --url) require_val "$1" "$#"; URL="$2"; shift 2 ;;
    --timeout) require_val "$1" "$#"; TIMEOUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 64 ;;
  esac
done

[[ "$TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { echo "--timeout must be a positive integer" >&2; exit 64; }
command -v gh >/dev/null 2>&1 || { echo "prerequisite missing: gh" >&2; exit 69; }
gh auth status >/dev/null 2>&1 || { echo "gh not authenticated (gh auth login / GH_TOKEN)" >&2; exit 69; }
command -v gcloud >/dev/null 2>&1 || { echo "prerequisite missing: gcloud" >&2; exit 69; }

# 1. Merge the PR (squash + delete branch) unless suppressed.
if [[ -n "$PR" && "$NO_MERGE" -eq 0 ]]; then
  echo "Squash-merging PR #$PR ..." >&2
  gh pr merge "$PR" --squash --delete-branch
fi
git checkout master >/dev/null 2>&1 || true
git pull --ff-only >/dev/null 2>&1 || true

# 2. Trigger the Actions deploy workflow and capture the new run id.
echo "Dispatching $WORKFLOW (environment=$ENVIRONMENT) ..." >&2
gh workflow run "$WORKFLOW" --ref master -f environment="$ENVIRONMENT"
sleep 8
RID="$(gh run list --workflow="$WORKFLOW" --limit 1 --json databaseId --jq '.[0].databaseId')"
[[ -n "$RID" ]] || { echo "could not resolve deploy run id" >&2; exit 2; }
echo "Deploy run: $RID  (https://github.com/$(gh repo view --json nameWithOwner --jq .nameWithOwner)/actions/runs/$RID)" >&2

# 3. Wait for the run to finish.
deadline=$(( $(date +%s) + TIMEOUT ))
while :; do
  status="$(gh run view "$RID" --json status,conclusion --jq '.status+"/"+(.conclusion // "")' 2>/dev/null || echo "unknown/")"
  echo "  deploy: $status" >&2
  case "$status" in
    completed/success) break ;;
    completed/*) echo "DEPLOY FAILED: $status" >&2; exit 2 ;;
  esac
  (( $(date +%s) >= deadline )) && { echo "TIMEOUT waiting for deploy run" >&2; exit 2; }
  sleep "$INTERVAL"
done

# 4. Verify the live service returns 200.
if [[ -z "$URL" ]]; then
  URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)' 2>/dev/null || true)"
fi
[[ -n "$URL" ]] || { echo "could not resolve service URL (pass --url)" >&2; exit 3; }
code="$(curl -s -o /dev/null -w '%{http_code}' "$URL" --max-time 25 || echo 000)"
echo "LIVE CHECK: HTTP $code  $URL" >&2
[[ "$code" == "200" ]] || { echo "service did not return 200" >&2; exit 3; }
echo "$URL"
exit 0
