# CareerEngine — Grooming Tracker

> Turns roadmap items ([REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)) into sonnet-launchable
> build specs, and tracks how far each is groomed so we can resume mid-stream.
> A workstream is Ready when it has: scope (files), acceptance criteria (named tests), and points at
> the durable builder invariants in [skills/build-slice](../skills/build-slice/SKILL.md) and the one
> relevant [ARCHITECTURE.md](ARCHITECTURE.md) section. Builders run on Sonnet with worktree isolation;
> Opus reviews + merges (no self-declared done). master stays green per merge. A builder gets a
> self-contained ticket + the skill — not the big docs (see [CONTEXT_STRATEGY.md](CONTEXT_STRATEGY.md)).
>
> Grooming legend: ✅ Ready (launchable) · ◐ Draft (outline, needs detail) · ⬜ To groom.

## Delivery lens (architecture + business)

Every groomed item below is constrained by the four standing goals:
1. Quality without compromise (quantified outcomes, no fake confidence).
2. Extreme cost efficiency (capability-first model routing, no hardcoded model IDs).
3. Privacy-first BYOK architecture (secrets in Secret Manager only).
4. Capstone demoability (Google X Kaggle 5-day intensive): reproducible end-to-end story, fast setup,
   and clear evidence artifacts for judges.

## Current launch order

Live grooming is **current phase only**. Completed phases (1.5, 1.7, 2, 4, 7, 8, 9) are retired to
[history/GROOMING_ARCHIVE.md](history/GROOMING_ARCHIVE.md) — grep it for provenance, don't load it whole.
Canonical status for every phase is in [PROGRESS.md](PROGRESS.md).

1. ✅ Phases 1.5 → 9 — SHIPPED (see [history/GROOMING_ARCHIVE.md](history/GROOMING_ARCHIVE.md)).
2. ▶ **Phase 10 — Replace Streamlit with Next.js + FastAPI** — groomed below; building API-first, one
   slice per PR (10.1 → 10.7).

> **Retire ritual:** when a phase's tickets are all ✅ and merged, move them to
> `history/GROOMING_ARCHIVE.md` in the same session (see
> [CONTEXT_STRATEGY.md](CONTEXT_STRATEGY.md)). GROOMING.md stays small so it never bloats what an
> agent loads.

---

## Phase 10 — Replace Streamlit with Next.js + FastAPI (build tickets)

> **Status: 10.0 done + 10.1–10.6b SHIPPED (PR #63–#70); only 10.7 (cutover) remains, ⏸ deferred to Phase 11.** The accepted
> decision, rationale, auth model, streaming choice, deploy
> topology, and API contract sketch are **canonical in [ARCHITECTURE.md §16](ARCHITECTURE.md)** — do
> not restate them here. Sequencing is in [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md) Phase 10;
> status is canonical in [PROGRESS.md](PROGRESS.md). Build **API-first, one slice per PR**, in order —
> each slice must be green (`make check` + any new frontend checks) before the next starts.

### Decision anchor (one line)
Retire the Streamlit surface for a **Next.js (App Router) frontend over a FastAPI JSON API**; the
Python domain is unchanged; `schema.py` stays the wire contract; auth + streaming move to the API
boundary. Full rationale + design decisions (AD-16.1..7): [ARCHITECTURE.md §16](ARCHITECTURE.md).

### Standing build rules for every 10.x ticket

- **Do not change domain behaviour.** FastAPI handlers `await` the existing async stores / graph /
  tailor / renderers directly. No business logic moves into the transport layer.
- **`schema.py` is the wire contract.** Response/request models are the existing Pydantic types (or
  thin DTOs over them); frontend types are generated from the OpenAPI schema, never hand-kept.
  Anything requiring a new field is a separate additive-MINOR `CONTRACT_VERSION` bump, not folded in.
- **Sub-agent instruction:** if a ticket's assumptions don't match the actual code (store signatures,
  auth interfaces, session shape), **PAUSE and ask — do not assume.** Confirm the auth shape (10.1)
  before wiring any protected route.
- Each ticket ships with tests; do not report `DONE`, report `READY FOR REVIEW`.

### ✅ 10.0–10.6b — SHIPPED (retired to the archive)
Completed slices **10.0** (ADR) · **10.1** (FastAPI skeleton + auth, PR #63) · **10.2** (read APIs,
#64) · **10.3** (write APIs, #65) · **10.4** (grill SSE API, #66) · **10.5** (Next.js app shell, #67) ·
**10.6a** (grill streaming UI, #68) · **10.6b** (tailor + résumé-export API #69 + Tailor UI #70). Full
build specs retired to [history/GROOMING_ARCHIVE.md §Phase 10](history/GROOMING_ARCHIVE.md); status
canonical in [PROGRESS.md](PROGRESS.md). **Only 10.7 (cutover) remains, deferred to Phase 11.**

### ⏸ 10.7 — Cutover  *(DEFERRED to Phase 11 · M · Backend + Infra + Docs)*
**Gated:** deletes the Streamlit `web/` app + reconfigures the deployed service, but the current dev
deployment is **frozen for the Kaggle presentation** (still runs Streamlit). Per the re-scoped roadmap
([REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md) Phase 11), the cutover pairs with **11.A (new
prod-like environment)** — do it there, not against the frozen env. Spec retained below for when it runs.
Make Next.js + FastAPI the deployed product and remove Streamlit.
- **Acceptance:** delete `web/` Streamlit app + `web/async_runner.py`; update Dockerfile / Cloud Run
  service(s) / `allowedOrigins` / redirect URIs; reconcile [ARCHITECTURE.md](ARCHITECTURE.md) (mark
  Streamlit sections `superseded`, update the frontends diagram), [PROGRESS.md](PROGRESS.md),
  [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md), [SECURITY.md](SECURITY.md), and
  [HANDOFF.md](HANDOFF.md). `CONTRACT_VERSION` unchanged by the migration itself.
- **Tests:** the API test suite is green with no import of `web/`; deploy config lints.

---

