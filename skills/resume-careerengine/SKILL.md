---
name: resume-careerengine
description: Resume autonomous CareerEngine work after a session reset or a fresh session. Use when told to "resume", "continue where you left off", "pick up the work", or when a scheduled wake-up fires. Reads docs/HANDOFF.md, picks the next ticket, and builds it end-to-end under the repo's merge rules.
---

# Resume CareerEngine work (cold-start safe)

You are picking up autonomous work on CareerEngine, possibly after a session reset, with
**no memory of the previous session**. Everything you need is on disk. Do not ask the
operator what to do next — the answer is in the docs. Just start.

## 1. Orient (in this order, always)

1. `docs/HANDOFF.md` — the **"👉 YOU ARE HERE"** banner is the resume point. It names the
   next ticket and any active warnings.
2. `docs/PROGRESS.md` — canonical delivery status ("qa hardening" + "Copy quality" rows).
3. `docs/GROOMING.md` — the build tickets themselves (**CQ-1…CQ-6**, **CLEAN-1**). Each has
   scope + acceptance criteria. Build them **in order**; later ones depend on earlier ones.
4. `docs/ARCHITECTURE.md` §18 — the design decisions behind the copy-quality work (AD-18.1…18.5).

Then check reality: `git status`, `git log --oneline -5`, `gh pr list`. **An already-open PR may be
mid-review — finish that (address the comments, resolve the threads, merge) before starting
anything new.**

## 2. The non-negotiable rules (these were learned the hard way)

- **NEVER push to `master`.** Branch → PR → review → merge. Not even for docs.
- **NEVER merge with an unresolved review thread.** Every Copilot comment gets a fix **or**
  a written reply on the thread. Requesting a re-review means *waiting for the new review* —
  a second review can land after the first looks clean. (`master` has a Conversation
  Resolution blocker; a PR sits at `BLOCKED` until threads are resolved.)
  - Reply: `gh api repos/{owner}/{repo}/pulls/{N}/comments/{comment_id}/replies -f body="..."`
  - Find unresolved threads (GraphQL, substituting the repo you are in):
    `gh api graphql -f query='{ repository(owner:"{owner}", name:"{repo}") { pullRequest(number:{N}) { reviewThreads(first:30) { nodes { id isResolved path } } } } }'`
  - Resolve: `gh api graphql -f query='mutation { resolveReviewThread(input:{threadId:"{thread_id}"}) { thread { isResolved } } }'`
- **Merging + deploying qa is authorized** without asking, *provided* Copilot reviewed first.
  `gh pr edit {N} --add-reviewer copilot-pull-request-reviewer`, then wait. (`{N}` = the PR number;
  `{owner}`/`{repo}` = the repo you are in — substitute them, don't run them literally.)
- **`dev` is BLOCKADED.** Never deploy there without an explicit go-ahead
  (`-f confirm_dev_cutover=true`). It is Kaggle-visible and holds real user data.
- **Any deploy that migrates persisted state** requires the backup + read-only dry-run in
  `docs/QA_DEPLOY_RUNBOOK.md` first. Non-negotiable — real users' portfolios are in there.
- **Never put secrets in code.** If a new GitHub secret is needed, stop and ask.
- Gate everything: `make check` (ruff + mypy --strict + pytest) **and** the frontend lane
  (`npx tsc --noEmit`, `npx vitest run`, `npx next lint`, `npm run build`). Docs-only changes
  skip the local gate but still go through PR + Copilot.

## 3. Build loop (repeat until the ticket list is done)

For each ticket, in GROOMING order:

1. `git checkout master && git pull && git checkout -b feat/<slug>`
2. Build it. Backend seam → API route → frontend → tests, each with a test that would have
   caught the bug the ticket describes.
3. Gate (both lanes). Fix everything.
4. Commit with a message that explains **why**, not just what. Push, open a PR whose body
   states the failure being fixed.
5. Request Copilot. **Wait.** Address every comment. Reply. Resolve.
6. Merge when CI is green *and* zero threads are unresolved.
7. Deploy qa: `gh workflow run deploy.yml --ref master -f environment=qa`, wait, verify
   `/api/health` and the new routes in the served `/openapi.json`.
8. **Update `docs/HANDOFF.md` + `docs/PROGRESS.md` before moving on** — that is what makes
   the *next* cold start work. Docs go through a PR too.

## 4. Before you stop (or run out of budget)

Leave the tree **clean** and the docs **true**:
- Commit or push everything; no half-edits.
- `docs/HANDOFF.md`'s banner must name the next action precisely enough that a session with
  zero memory can continue from it.
- If a PR is open and mid-review, say so in the banner with its number.

## 5. Deployment / qa facts

- qa URL: `https://career-engine-qa-app-ontyg6kaja-uc.a.run.app`
- Redeploy: `gh workflow run deploy.yml --ref master -f environment=qa`
- Live session state is under the Firestore document's **`session_state`** key.
  `career_engine_state` is empty in practice and **will mislead you**.
