# CareerEngine — AI agent instructions

> Generic agent instructions (read by Antigravity and other agents that support `AGENTS.md`).
> The same rules live in [`CLAUDE.md`](CLAUDE.md) (Claude Code) and
> [`.github/copilot-instructions.md`](.github/copilot-instructions.md) (GitHub Copilot).

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

## Before switching tools or ending a session
1. Commit or stash so the git working tree is **clean** — the next tool/session starts from a
   known state. Uncommitted half-edits are the main thing that breaks a hand-off.
2. Make sure `docs/HANDOFF.md` reflects what's in flight and what's next.

## Project orientation
- Read `docs/HANDOFF.md` **first**, then `docs/PROGRESS.md` (live status),
  `docs/ARCHITECTURE.md`, and `docs/REFINED_PROJECT_PLAN.md`.
- Don't mutate a spec that's mid-build — **version-gate** instead.
- Validate changes with `make check` (ruff, mypy --strict, pytest).
