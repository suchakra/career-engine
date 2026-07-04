---
name: ship-change
description: Ship one code change end-to-end the CareerEngine way — branch, gate, dual review (Sonnet + Copilot), squash-merge, then trigger the GitHub Actions deploy and verify the live app. Use for every code change so the branch→check→PR→review→merge→deploy→verify loop is one consistent procedure instead of hand-rolled commands each time. Requires an authenticated gh CLI + gcloud.
---

# ship-change

The standard per-change delivery loop for CareerEngine. It encodes the process in
[docs/HANDOFF.md](../../docs/HANDOFF.md) "Process (how we work)" so it runs the same
way every time. The build, the commit message, the PR body, and addressing review
comments still need judgment — this skill sequences the mechanical steps and
provides a script for the repetitive tail (dispatch deploy → wait → verify 200).

## Prerequisites
- `gh` authenticated (`gh auth status`), `jq`, and `gcloud` authenticated.
- Working tree clean or intentionally staged; you are on / branching from `master`.

## The loop

1. **Branch.** `git checkout -b <fix|feat|docs>/<slug>` off up-to-date `master`.
2. **Build** the change (Opus, in-context). Match surrounding code style.
3. **Gate green.** `make check` (ruff + mypy --strict + pytest); `make tf-check` if infra changed.
   A contract change (`schema.py`/`config.py`/public interface) needs a `CONTRACT_VERSION` bump.
4. **Sonnet review** the diff as an independent gate for anything non-trivial or
   state-machine/contract-touching (spawn a review subagent; address CHANGES REQUESTED,
   re-gate). Small surgical diffs may be Opus self-review.
5. **Commit + push.** Conventional message; trailer
   `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
6. **Open the PR.** `gh pr create` with a body that states the symptom, root cause, fix,
   and test/guard. No schema change unless a bump is called out.
7. **Request Copilot review**, then **wait** for it:
   ```bash
   PR=<n>
   gh api --method POST "repos/{owner}/{repo}/pulls/$PR/requested_reviewers" \
     -f 'reviewers[]=copilot-pull-request-reviewer[bot]'   # surfaces as login 'Copilot'
   ../wait-for-pr-review/scripts/wait_for_review.sh --pr "$PR"   # blocks until the review lands
   ```
   (Use the sibling `wait-for-pr-review` skill — don't hand-roll a poll loop.)
8. **Address Copilot comments** (`gh api repos/{owner}/{repo}/pulls/$PR/comments`): fix, push,
   reply on the PR. If Copilot is silent for a few minutes on an urgent fix, merging on CI-green +
   self-review is acceptable — say so explicitly.
9. **Merge + deploy + verify** with the script:
   ```bash
   scripts/deploy_and_verify.sh --pr "$PR"
   ```
   It squash-merges (`--delete-branch`), updates `master`, dispatches the Actions `deploy.yml`
   workflow, waits for that run to finish, and curls the Cloud Run URL until it returns 200.
   (Deploy is done by **GitHub Actions** — the script only triggers `deploy.yml` and verifies;
   nothing is built or applied locally. `deploy.yml` is `workflow_dispatch` today, so it must be
   triggered per merge unless/until a push-to-master trigger is added.)
10. **Reconcile docs** in the same session (PROGRESS / HANDOFF / owning doc). Tree clean.

## deploy_and_verify.sh

```
scripts/deploy_and_verify.sh --pr <N> [--no-merge] [--env dev] \
    [--service career-engine-dev-app] [--region us-central1] [--url <override>] [--timeout 600]
```
- With `--pr`: squash-merges the PR + deletes the branch, then deploys + verifies.
- With `--no-merge` (or no `--pr`): just dispatches the deploy for the current `master` and verifies.
- Exit codes: `0` live (HTTP 200) · `2` deploy run failed/timed out · `3` service not 200 ·
  `64` bad args · `69` missing/unauthenticated `gh`/`gcloud`.

## Notes
- Don't batch-deploy while a user is mid-session in the app — back-to-back redeploys restart the
  Cloud Run container and can wedge an in-flight session. Batch fixes, then one deploy.
- The two review gates are independent (Sonnet reads the diff; Copilot reviews the PR); CI is the
  third. Only a review PASS ticks `docs/PROGRESS.md`.
