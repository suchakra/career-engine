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

## Phase 10 — Replace Streamlit with Next.js + FastAPI  *(✅ COMPLETE — retired to archive)*

**All slices shipped: 10.0–10.7b (PR #63–#72 + Streamlit-removal PR).** The Streamlit surface is gone; the
product runs on a **Next.js (App Router) frontend over a FastAPI JSON API**, deployed as **one container**
(Next.js static export served by FastAPI, AD-16.10). Design is canonical in
[ARCHITECTURE.md §16](ARCHITECTURE.md); status in [PROGRESS.md](PROGRESS.md); full build specs + the
standing 10.x build rules are retired to
[history/GROOMING_ARCHIVE.md §Phase 10](history/GROOMING_ARCHIVE.md).

**Next phase (11 — stabilization) is NOT yet groomed into build tickets.** Groom it (WARM docs → tickets)
before building; scope is in [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md) Phase 11. The immediate
first slice is **11.A — stand up a new-GCP-project `qa` env** and deploy the 10.7 image to it.

---

