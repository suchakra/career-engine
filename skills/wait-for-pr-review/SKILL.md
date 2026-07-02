---
name: wait-for-pr-review
description: Block until a PR review (e.g. GitHub Copilot's automated code review) lands, by polling gh internally. Use after opening a PR and requesting a Copilot/bot review, so you make ONE call instead of burning tokens re-polling. Requires an authenticated gh CLI.
---

# wait-for-pr-review

Waits for a matching PR review to appear, then prints it. Polling happens
**inside the script**, so the agent makes a single blocking call rather than
looping poll-tool-calls (which burns tokens).

## When to use

After you `gh pr create` and request a review (e.g. from GitHub Copilot), invoke
this to wait for the review to be submitted, then read its comments and address them.

## Prerequisites

- `gh` authenticated (`gh auth login` or `GH_TOKEN`).
- `jq` installed (used to filter `gh pr view --json reviews`).

The script exits **69** if either prerequisite is missing (gh unauthenticated or jq absent).

## Request a Copilot review first (separate step)

The script only *waits*; request the review yourself before calling it:

```bash
# Preferred: request Copilot as a reviewer (the exact login can vary by account;
# copilot-pull-request-reviewer[bot] is the common one):
gh api --method POST "repos/{owner}/{repo}/pulls/<PR>/requested_reviewers" \
  -f 'reviewers[]=copilot-pull-request-reviewer[bot]'   # or use the GitHub UI: "Reviewers → Copilot"
```

## Wait for it

```bash
skills/wait-for-pr-review/scripts/wait_for_review.sh --pr <PR> [options]
```

Options: `--author-pattern copilot` (default; case-insensitive substring of the
review author's login), `--timeout 540` (seconds — keep under the 600s Bash-tool
cap; re-invoke to keep waiting), `--interval 30`, `--repo owner/name`,
`--since <ISO8601>` (only count reviews submitted at/after a timestamp — pass the
time you requested the review to ignore earlier ones).

## Exit codes

- `0` — a matching review was found; its JSON (author, state, body, submittedAt)
  is printed to stdout.
- `2` — timeout (no matching review yet); re-invoke to keep waiting.
- `64` — bad arguments (missing/invalid flag values) · `69` — prerequisite
  missing (`gh` not authenticated, or `jq` not installed).

## After it returns

Fetch the full review + inline comments and address them:

```bash
gh pr view <PR> --json reviews,comments
gh api "repos/{owner}/{repo}/pulls/<PR>/comments"   # inline review comments
```
Apply the appropriate suggestions, commit, and push; the review re-runs on new commits.

> Note: this is a generic utility. It matches any review author by substring, so
> it also works for human reviewers (`--author-pattern <login>`).
