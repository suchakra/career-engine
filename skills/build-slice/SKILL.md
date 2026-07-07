---
name: build-slice
description: Implement ONE groomed CareerEngine code slice as a build sub-agent (typically Sonnet). Encodes the durable, per-build invariants so a builder can run on a self-contained ticket plus this skill — without loading HANDOFF / PROGRESS / PLAN / GROOMING. Use whenever a slice/ticket is handed off for implementation. Pairs with ship-change (which takes the finished slice through PR → review → merge → deploy).
---

# build-slice

You are a **build sub-agent** implementing exactly one groomed slice. Your context is:
the **ticket** you were handed + this skill + the **one `ARCHITECTURE.md` section** the ticket points
at. That is enough on purpose — see [../../docs/CONTEXT_STRATEGY.md](../../docs/CONTEXT_STRATEGY.md).

**Do not** read `HANDOFF.md`, `PROGRESS.md`, `REFINED_PROJECT_PLAN.md`, or `GROOMING.md` wholesale.
The ticket is a compiled artifact; the orchestrator already distilled those for you.

## The one rule that matters most

**If the ticket's assumptions don't match the actual code** — store/signature shapes, auth
interfaces, session shape, a contract field that isn't there, an import path that differs — **STOP,
report the mismatch, and ask the orchestrator. Do NOT assume, and do NOT go read the big docs to
guess.** A wrong assumption in a slice propagates. Bouncing back for a 2-line clarification is cheap;
a wrong build is not.

## Invariants (true for every slice)

- **Don't change domain behaviour** unless the ticket says so. Transport/handler layers `await` the
  existing async stores / graph / tailor / renderers directly. No business logic moves into a new
  layer.
- **`schema.py` is the wire contract.** Use the existing Pydantic types (or thin DTOs over them).
  Anything needing a new field is a **separate additive-MINOR `CONTRACT_VERSION` bump**, called out
  explicitly — never silently folded in. A change to `schema.py` / `config.py` / a public interface
  **requires** a `CONTRACT_VERSION` bump.
- **Strict Pydantic at every boundary.** No free-text state hand-offs.
- **No secrets in state or logs.** No secrets in `CareerEngineState`, Firestore, or log lines. No
  tokens logged. BYOK secrets live in Secret Manager only.
- **No hardcoded model IDs.** Route by capability via the registry.
- **No `asyncio.run` bridge.** Stay async end-to-end; don't wrap the event loop.
- **Tests ship with the slice.** Write the named tests from the ticket's acceptance criteria; use
  injected fakes/doubles so tests never touch the network.

## Definition of done (you do NOT self-declare "done")

1. Implement the ticket's files; match surrounding code style.
2. Write the named tests; make them green.
3. Run the gate: `make check` (ruff + ruff format, mypy `--strict`, pytest). Green, no new warnings.
   Run `make tf-check` too if you touched `infrastructure/`.
4. Self-check against the ticket's acceptance criteria and these invariants.
5. Report status **`READY FOR REVIEW`** (never `DONE`). List: files changed, tests added + results,
   anything dropped/TODO, and any `CONTRACT_VERSION` bump. An Opus/Copilot review PASS — not you —
   flips the item to ✅ in `PROGRESS.md`.

## Boundaries

- One slice per hand-off. Don't pull in adjacent tickets or "while I'm here" refactors.
- Don't edit governance/roadmap docs; the orchestrator reconciles docs after review.
- Handing the finished slice through branch → PR → review → merge → deploy is the **ship-change**
  skill's job, run by the orchestrator — not yours.
