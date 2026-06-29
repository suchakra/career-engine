# CareerEngine — GitHub Copilot instructions

> The same rules live in [`CLAUDE.md`](../CLAUDE.md) (Claude Code) and
> [`AGENTS.md`](../AGENTS.md) (Antigravity / generic agents).

## Start every fresh session here
**Before doing anything else, read `docs/HANDOFF.md`** to orient yourself — it's the resume point.
Then skim the other `docs/` files as needed (see Project orientation below).

## Docs-first rule (most important)
**Durable state lives in `docs/`, not in any assistant's chat memory.** Whenever you make a
decision, finish a chunk of work, change direction, or learn something worth keeping:
- Write it into the relevant file under `docs/` — don't leave it only in conversation.
- Keep `docs/HANDOFF.md` current; it is the **resume point** read at the start of every session
  and when switching between AI tools. Update its "👉 YOU ARE HERE" banner before you stop.
- This repo is worked on across **multiple AI tools** (Claude Code, GitHub Copilot, Antigravity).
  Treat `docs/` as the shared, tool-agnostic source of truth so any tool can pick up cleanly.

## Docs governance
- Every core doc has one job only.
  `docs/HANDOFF.md` is the session resume point and current next-action banner.
  `docs/PROGRESS.md` is the delivery ledger and only canonical milestone/workstream status.
  `docs/ARCHITECTURE.md` is the design truth and accepted architectural decisions.
  `docs/REFINED_PROJECT_PLAN.md` is the roadmap and sequencing truth.
  `docs/GROOMING.md` is the build-launch spec for upcoming work only.
- Status is canonical in `docs/PROGRESS.md` only. Other docs may summarize status, but must not
  become the authoritative source for complete/in-progress/blocked/not-started state.
- "You are here" state is canonical in `docs/HANDOFF.md` only. Current branch cleanliness, work
  in flight, and immediate next action belong there.
- Planning docs describe intended behavior, not shipped reality. If a planning doc mentions build
  status, it must point back to `docs/PROGRESS.md`.
- Any design-heavy doc must declare freshness explicitly at the top using: status (`draft`,
  `active`, `frozen`, or `superseded`), last reviewed date, and a pointer to the replacement if
  superseded.
- If code changes affect behavior, workflow topology, contract shape, build sequencing, or
  milestone completion, reconcile the relevant docs in the same session before stopping.
- If you notice contradiction between docs, do not leave it implicit. Fix it, mark one source as
  stale, or record the follow-up in `docs/HANDOFF.md` before ending the session.
- `docs/GROOMING.md` is for executable build prompts, not unresolved design debate. Update
  architecture/plan first, then regenerate grooming.
- If text is no longer current but still useful, mark it `superseded` or `historical` rather than
  leaving ambiguous stale guidance in place.
- Avoid copying the same fact into multiple docs unless each copy serves a different purpose.
  Milestone completion belongs in `docs/PROGRESS.md`; next action belongs in `docs/HANDOFF.md`;
  rationale belongs in `docs/ARCHITECTURE.md`.
- Start of session: read `docs/HANDOFF.md` first, then `docs/PROGRESS.md` if delivery state may
  be affected.
- End of session: if you changed implementation state, plan, architecture, or resolved a docs
  contradiction, update the owning doc before stopping.
- Work is not complete until code state and docs state agree.

## Before switching tools or ending a session
1. Commit or stash so the git working tree is **clean** — the next tool/session starts from a
   known state. Uncommitted half-edits are the main thing that breaks a hand-off.
2. Make sure `docs/HANDOFF.md` reflects what's in flight and what's next.

## Project orientation
- Read `docs/HANDOFF.md` first, then `docs/PROGRESS.md` (live status), `docs/ARCHITECTURE.md`,
  and `docs/REFINED_PROJECT_PLAN.md`.
- Don't mutate a spec that's mid-build — version-gate instead.
- Validate changes with `make check` (ruff, mypy --strict, pytest).
