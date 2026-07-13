---
name: resume-careerengine
description: Resume autonomous CareerEngine work after a session reset or a fresh session. Use when told to "resume", "continue where you left off", "pick up the work", or when a scheduled wake-up fires. Reads docs/HANDOFF.md, picks the next ticket, and builds it end-to-end under the repo's merge rules.
---

# Resume CareerEngine work (cold-start safe)

You are picking up autonomous work on CareerEngine, possibly after a session reset, with
**no memory of the previous session**. Everything you need is on disk. Do not ask the
operator what to do next — the answer is in the docs. Just start.

## 0. ONE TICKET = ONE FRESH SESSION (Sumanta, 2026-07-13 — do not drift from this)

**Start a new session for every ticket.** When a ticket is merged, deployed, and its docs are
reconciled, **stop and end the session** — do not roll straight into the next ticket in the same
thread.

This is the whole point of `docs/HANDOFF.md`, and it had stopped being used as designed: tickets
were being chained in one enormous thread, so by ticket #3 the context was mostly the archaeology
of tickets #1 and #2. **A cold session that reads HANDOFF costs a fraction of turn #400 in a
1M-token thread, and it reasons better** — it sees the ticket, not the debris.

The obligation this creates: **HANDOFF must be true before you stop** (§4). If the banner is
wrong, the next cold session starts wrong. The handoff *is* the deliverable, not a chore after it.

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
- **Merging + deploying qa is authorized** without asking, *provided the PR got its reviews*
  (§3 step 0 plan review + §3 step 5 diff review). The reviews are the CONDITION of the merge
  authority, not a nicety.
- **The review budget — ONE diff review, not two (Sumanta, 2026-07-13).** The waste was never the
  reviewer, it was the *redundancy*, plus letting a reviewer re-audit the whole repo from scratch.
  - **Plan review stays exactly as it is (§3 step 0) — do not touch it.** It is the cheapest,
    highest-leverage step we have: short input, high value. It killed the `_covers` deletion (would
    have double-listed every existing user's résumé), the CQ-5b re-open bug, and the CQ-6b undo
    design — all *before any code existed*.
  - **Diff review: exactly one, `model: opus`, with a TIGHT BRIEF.** Hand it (a) the diff, (b) the
    **3–5 specific risks you are actually worried about**, and (c) an explicit instruction: *do not
    re-derive repo context, do not audit unrelated code, answer the named risks and anything that
    would break a user*. An unbriefed reviewer spends its budget rediscovering the codebase.
  - **Escalate to a SECOND reviewer only when the PR touches persisted state, auth, or money** —
    the places where a miss is *unrecoverable*. A rendering bug can be fixed next deploy; a
    migration that mangles a real portfolio cannot.
  - Copilot is no longer part of the loop (premium quota exhausted). Do not wait on it.
  - Still true regardless of count: **never self-review**, treat every finding as real until you
    disprove it, and tell the reviewer the author is an overconfident AI.
  (`{N}` = the PR number; `{owner}`/`{repo}` = the repo you are in — substitute, don't run literally.)
- **`dev` is BLOCKADED.** Never deploy there without an explicit go-ahead
  (`-f confirm_dev_cutover=true`). It is Kaggle-visible and holds real user data.
- **Any deploy that migrates persisted state** requires the backup + read-only dry-run in
  `docs/QA_DEPLOY_RUNBOOK.md` first. Non-negotiable — real users' portfolios are in there.
- **Never put secrets in code.** If a new GitHub secret is needed, stop and ask.
- Gate everything: **`make check`** (ruff + mypy --strict + pytest) **and** **`make frontend-check`**
  (npm ci → lint → typecheck → vitest → build → bundle budget). Use the make targets, not ad-hoc
  `npx` calls — the make lane is what CI runs, and it checks more (the bundle budget in particular).
  Docs-only changes skip the local gate but still go through PR + an adversarial review (§2).

## 3. Build loop (repeat until the ticket list is done)

For each ticket, in GROOMING order:

0. **PLAN REVIEW FIRST — before you write a line of code.** Write the plan (what you will change,
   in which files, what each gate/invariant must hold, what could go wrong) and hand it to a
   **different model** for an adversarial pre-execution review:
   `Agent(subagent_type="general-purpose", model="fable", run_in_background=false)`.
   Tell it: the plan's author is an overconfident AI; find the assumption that is false, the code
   path the plan forgets, and the existing data the plan will break. Demand concrete failure
   sequences, not opinions.
   **Why (Sumanta, 2026-07-13 — "it will save rework"):** on CQ-5b the plan was reviewed only
   AFTER it was built, and the review found the feature was **completely inert** (I wired coverage
   into the grill node but not into the ROUTER, which still abandoned the entry) and that it would
   have **re-opened every returning user's finished portfolio**. Both were plan-level errors —
   visible in the design, not just the diff — and cost a full rebuild. Ask *before* building.
1. `git checkout master && git pull && git checkout -b feat/<slug>`
2. Build it. Backend seam → API route → frontend → tests, each with a test that would have
   caught the bug the ticket describes.
3. Gate (both lanes). Fix everything.
4. Commit with a message that explains **why**, not just what. Push, open a PR whose body
   states the failure being fixed.
5. **ONE adversarial diff review — `model: opus`, tight brief** (§2). Give it the diff + the 3–5
   risks you are actually worried about + "do not re-derive repo context". Address every finding,
   reply on each thread, resolve them. **Never merge with an open thread, and never self-review.**
   A second reviewer only if the PR touches **persisted state, auth, or money**.
6. Merge when CI is green *and* zero threads are unresolved.
7. Deploy qa: `gh workflow run deploy.yml --ref master -f environment=qa`, wait, verify
   `/api/health` and the new routes in the served `/openapi.json`.
8. **Update `docs/HANDOFF.md` + `docs/PROGRESS.md`, then STOP — end the session** (§0). Do not
   start the next ticket in this thread. The banner you leave behind is what the next cold session
   runs on.

## 4. Before you stop — and you STOP at the end of every ticket (§0)

Leave the tree **clean** and the docs **true**:
- Commit or push everything; no half-edits.
- `docs/HANDOFF.md`'s banner must name the next action precisely enough that a session with
  zero memory can continue from it.
- If a PR is open and mid-review, say so in the banner with its number.
- Then **end the session**. The next ticket starts cold, from HANDOFF. That is the design.

## 5. Deployment / qa facts

- qa URL: `https://career-engine-qa-app-ontyg6kaja-uc.a.run.app`
- Redeploy: `gh workflow run deploy.yml --ref master -f environment=qa`
- Live session state is under the Firestore document's **`session_state`** key.
  `career_engine_state` is empty in practice and **will mislead you**.
