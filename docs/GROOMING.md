# CareerEngine — Grooming Tracker

> Turns roadmap items ([REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)) into sonnet-launchable
> build specs, and tracks how far each is groomed so we can resume mid-stream.
> A workstream is Ready when it has: scope (files), acceptance criteria (named tests), and points at
> the Shared preamble + Definition of Done in [AGENT_EXECUTION_PROMPT.md](AGENT_EXECUTION_PROMPT.md)
> and the spec in [ARCHITECTURE.md](ARCHITECTURE.md). Builders run on Sonnet with worktree isolation;
> Opus reviews + merges (no self-declared done). master stays green per merge.
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

1. ✅ Phase 1.7 (integration closure of deferred Phase-1 work) — merged.
2. ✅ Phase 2 (web/infra/async) — built, deployed live on Cloud Run (dev).
3. **▶ Phase 4 — Portfolio Workbench** (see below) — groomed & ready; **next up**. Order 4A→4B→4C→4D
   (4E deferred). Each slice is an independent PR via the standard branch→check→review→PR→merge→deploy
   loop in [HANDOFF.md](HANDOFF.md).
4. Phase 3 (hardening/eval) — not groomed here.

---

## Phase 1.5 status (archived)

Phase 1.5 is complete (contract v2.0.0; 317 tests). This file now grooms what remains:
Phase 1.7 + Phase 2.

---

## Phase 1.7 — grooming status (deferred Phase-1 integration closure)

| WS | Scope | Depends on | Grooming |
|----|-------|-----------|----------|
| 1.7-A | Resume-file upload wired into CLI grill start path | 1.5 INGEST complete | ✅✅ BUILT (review in progress) |
| 1.7-B | True session resume semantics for return-loop flows | 1.5 DISCOVERY complete | ✅✅ BUILT (review in progress) |
| 1.7-C | discovery_turn_node wired into main graph/CLI path (contract v2.1.0) | 1.5 GRILL + DISCOVERY complete | ✅✅ BUILT (review in progress) |
| 1.7-D | Move FakeFirestore test doubles out of production module | none | ✅✅ BUILT (review in progress) |

> **Status:** all four 1.7 workstreams built by Opus this session (B→A→D→C), 338 tests green,
> Sonnet pre-review + Copilot gate pending before tagging `contract-v2.1.0`. 1.7-C took the approved
> additive minor bump (`coverage_confirmed`) rather than the original "no contract bump" note.

### Sequencing for 1.7

Recommended order to keep master green and minimize merge conflict:
1. 1.7-B first (session load/resume semantics).
2. 1.7-A second (resume-file CLI wiring consumes stable session semantics).
3. 1.7-C third (graph/CLI discovery-turn wiring).
4. 1.7-D can run in parallel with 1.7-C (low coupling), then merge before Phase 2 fan-out.

### ✅ 1.7-B — session resume semantics (build first)
Read first: [ARCHITECTURE.md §2](ARCHITECTURE.md) + [ARCHITECTURE.md §4](ARCHITECTURE.md) + Shared preamble.

```text
You are WS 1.7-B for CareerEngine. Implement true resumed-session behavior for the discovery return
loop so we stop relying on last-write-wins create_session behavior.

Stay in: cli/session.py, cli/app.py (session open path only), database/firestore_session.py (only if
needed for explicit get/load semantics), and tests.

Scope:
- Add/standardize a helper path that loads an existing session state by session_id and reuses it when
  present instead of blind create/overwrite.
- Preserve current behavior for brand-new sessions.
- Ensure return-loop prompts and grill_frontier continuity use loaded persisted state.
- Keep ADK runner turn semantics unchanged (one node per run_async invocation).

Acceptance criteria (named tests required):
- Existing session_id with persisted state is loaded (not clobbered), and grilling resumes from prior
  frontier/question context.
- New session_id still starts clean with INGESTING/GRILLING flow as expected.
- Missing/invalid session_id returns a typed, user-safe error path (no stack leak).
- No regression to normal answer/checkpoint/tailor paths.

DoD:
- make check green.
- Report READY FOR REVIEW with file list + criterion->test mapping.
- No contract changes.
```

### ✅ 1.7-A — resume-file upload CLI wiring
Read first: [ARCHITECTURE.md §12.2](ARCHITECTURE.md) + [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md).

```text
You are WS 1.7-A for CareerEngine. Wire resume-file upload into the grill command so users can start
from a real resume file without manual seeding.

Stay in: main.py, cli/app.py, cli/session.py (only call-site glue), and tests. Do NOT alter schema.

Scope:
- Add a grill CLI option (e.g. --resume-file PATH).
- Detect mime type, read bytes, call tools.resume_parser.parse_resume(bytes, mime).
- Seed start(work_timeline=...) when parse succeeds.
- Surface parse failures as clear user-facing messages with recovery guidance.
- Keep text-only startup path unchanged when no file is provided.

Acceptance criteria (named tests required):
- Valid PDF path calls parse_resume and seeds non-empty work_timeline.
- Valid image path (png/jpg/webp) routes through same parse flow.
- Unsupported mime and parse failures print deterministic user-safe error and continue with normal
  interactive options (no crash).
- Existing no-file behavior remains unchanged.

DoD:
- make check green.
- No raw file bytes persist in CareerEngineState or logs.
- Report READY FOR REVIEW with criterion->test map.
```

### ✅ 1.7-C — discovery_turn graph wiring
Read first: [ARCHITECTURE.md §12.3-§12.4](ARCHITECTURE.md) + [HANDOFF.md](HANDOFF.md).

```text
You are WS 1.7-C for CareerEngine. Wire discovery_turn_node into the main graph/CLI flow so the
"what have you done since?" turn is reachable in normal operation.

Stay in: workflows/discovery_graph.py, workflows/nodes.py (only minimal integration hooks),
cli/app.py (only routing/surface glue), tests/test_workflow.py, tests/test_integration.py.

Scope:
- Add an explicit router branch that can route to discovery_turn_node when coverage confirmation is
  needed.
- Keep one-node-per-run semantics and checkpoint brake behavior intact.
- Ensure discovered entries append to work_timeline and are picked up by grill frontier rules.

Acceptance criteria (named tests required):
- Router chooses discovery_turn branch under expected incomplete-coverage condition.
- A user discovery reply appends a discovered Entry and subsequent turn targets that entry when
  appropriate.
- No loop/spin regression (single run_async invocation still advances one node and stops).
- Existing finalize/tailor paths remain reachable and never gated.

DoD:
- make check green.
- Contract bumped v2.0.0 → v2.1.0 (additive: `coverage_confirmed`; user-approved — the one-shot
  discovery turn needs a state marker to record it has run; see status table note above).
- READY FOR REVIEW with explicit regression-test list.
```

### ✅ 1.7-D — persistence module hygiene (test fakes out of prod)
Read first: [PROGRESS.md](PROGRESS.md) Phase 1.3 deferred note.

```text
You are WS 1.7-D for CareerEngine. Move FakeFirestore test doubles out of the production persistence
module to reduce runtime coupling.

Stay in: database/firestore_session.py, tests/ (new helper module allowed), and imports referencing
those fakes.

Scope:
- Move FakeFirestoreClient and supporting _Fake* classes into tests/fixtures or tests/helpers.
- Keep production module behavior unchanged.
- Update tests to import from test helper location.

Acceptance criteria (named tests required):
- No FakeFirestore test-double classes remain in database/firestore_session.py.
- Firestore adapter tests still pass with moved fakes.
- Import graph for production runtime does not include test-only classes.

DoD:
- make check green.
- READY FOR REVIEW with before/after import evidence.
```

### Phase 1.7 exit gate

Phase 1.7 is complete only when all four items above are merged and this end-to-end demo is green:
1. Start grill with resume file.
2. Parse + seed timeline.
3. Run discovery turn in graph.
4. Pause and resume same session id.
5. Continue grilling backward and tailor without gating.

---

## Phase 2 — grooming status (web / infra / async, capstone-ready)

| WS | Scope | Depends on | Grooming |
|----|-------|-----------|----------|
| 2A | Streamlit workspace + dashboard + pending-action + discovery nudge UI | Phase 1.7 complete | ✅ Ready |
| 2B | Web auth path (Identity Platform/Firebase) and session bootstrap | 2A shell | ✅ Ready |
| 2C | Terraform infra (Cloud Run, Firestore, Artifact Registry, Secret Manager, Scheduler) | none | ✅ Ready |
| 2D | Async pending-action sweep job + scheduler contract | 2C | ✅ Ready |
| 2E | Capstone packaging: reproducible demo runbook + evaluation evidence | 2A-2D | ✅ Ready |

### Phase 2 fan-out and merge strategy

1. Launch 2C first (infra baseline).
2. Launch 2A and 2B in parallel once 2C interface assumptions are frozen.
3. Launch 2D after 2C resources/naming are stable.
4. Launch 2E after 2A-2D are merged to produce a capstone-ready submission artifact set.

### ✅ 2C — infrastructure baseline (build first)
Read first: [ARCHITECTURE.md §5](ARCHITECTURE.md) + [ARCHITECTURE.md §8](ARCHITECTURE.md).

```text
You are WS 2C for CareerEngine. Build the deployable GCP baseline for dev/prod.

Stay in: infrastructure/modules/*, infrastructure/envs/dev/*, infrastructure/envs/prod/*,
infrastructure/README.md, Makefile (deploy/destroy targets only).

Scope:
- Terraform modules/resources for Cloud Run, Firestore Native, Artifact Registry, Secret Manager,
  Cloud Scheduler.
- Service account least privilege with secretmanager.secretAccessor for runtime identity.
- Parameterize project/region/resource names; no hardcoded secrets.
- Ensure env/dev and env/prod both validate and plan.

Acceptance criteria (named checks/tests required):
- terraform fmt -check, terraform validate, terraform plan succeed in dev and prod roots.
- Plan output includes expected IAM binding for Secret Manager accessor.
- make deploy/make destroy target dev root deterministically.
- README documents prerequisites, variables, and rollback path.

DoD:
- Infra checks green and captured in review handoff.
- READY FOR REVIEW.
```

### ✅ 2A — Streamlit workspace and UX surface
Read first: [ARCHITECTURE.md §2](ARCHITECTURE.md) + [ARCHITECTURE.md §8](ARCHITECTURE.md).

```text
You are WS 2A for CareerEngine. Build the Streamlit workspace as a thin presentation layer over the
existing runner/session core.

Stay in: main.py (web path), new/updated web UI modules, minimal cli-independent helpers, tests.
Do NOT embed workflow logic in UI.

Scope:
- Dashboard showing current progress, recent activity, pending actions, and resume/tailor entry points.
- Surface consent-respecting discovery nudge in web UX (never blocks tailoring).
- Show pending-action items generated by async sweep.
- Keep CLI and web sharing same state backend contract.

Acceptance criteria (named tests required):
- Web path boots and renders dashboard with fixture state.
- Incomplete recent window shows nudge; complete window hides nudge.
- Tailor action proceeds even when nudge is shown.
- Pending-action item renders when present in workspace state.

DoD:
- make check green.
- No workflow/business logic moved into UI layer.
- READY FOR REVIEW.
```

### ✅ 2B — web auth/session bootstrap
Read first: [ARCHITECTURE.md §5](ARCHITECTURE.md).

```text
You are WS 2B for CareerEngine. Wire web identity and session bootstrap for the Streamlit path.

Stay in: auth/firebase_auth.py, web auth glue, main.py web bootstrap, tests.

Scope:
- Implement/finish Identity Platform web auth integration for stable user_id.
- Ensure authenticated user maps to correct session namespace.
- Keep BYOK key retrieval through KeyVault/Secret Manager, never Firestore.

Acceptance criteria (named tests required):
- Same identity resolves to stable user_id across logins.
- Unauthenticated access is rejected with safe UX path.
- Authenticated flow can open/create workspace session and read existing state.
- No secret material appears in session payloads.

DoD:
- make check green.
- READY FOR REVIEW with auth failure-path tests listed.
```

### ✅ 2D — async pending-action sweep
Read first: [ARCHITECTURE.md §8](ARCHITECTURE.md).

```text
You are WS 2D for CareerEngine. Implement async pending-action sweep and scheduler integration.

Stay in: jobs/pending_action_sweep.py, scheduler wiring references, tests.

Scope:
- Query applied records older than 14 days and write pending_action markers to workspace state.
- Keep operation idempotent (repeat runs do not duplicate pending items).
- Optional follow-up suggestion path must use per-user key resolution safely.

Acceptance criteria (named tests required):
- Records older than threshold are flagged exactly once.
- Records newer than threshold are untouched.
- Re-running job preserves idempotency.
- Failure in one user record does not crash entire sweep; errors are logged with user-safe context.

DoD:
- make check green.
- READY FOR REVIEW with idempotency evidence.
```

### ✅ 2E — capstone packaging and evidence set
Read first: [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md) decision D9.

```text
You are WS 2E for CareerEngine. Produce capstone submission artifacts for the Google X Kaggle 5-day
intensive without changing core architecture.

Stay in: docs/ (capstone runbook/evidence), evaluation/ (minimal deterministic script updates),
optionally Makefile docs targets.

Scope:
- Create a short, reproducible demo runbook: setup -> run -> expected outputs/screens.
- Map features to judging-facing proof points: quality, cost efficiency, privacy, agent workflow.
- Add deterministic evidence capture checklist (commands, screenshots/logs, test outputs).

Acceptance criteria:
- A fresh reviewer can execute the runbook end-to-end in bounded time and reproduce expected outputs.
- Evidence checklist references concrete commands and file outputs, not prose claims.
- Submission narrative clearly states tradeoffs and deferred scope.

DoD:
- make check remains green.
- READY FOR REVIEW with runbook dry-run notes.
```

### Phase 2 exit gate

Phase 2 is complete when:
1. Dev deploy is reproducible.
2. Web + CLI share state consistently.
3. Pending-action sweep runs on schedule contract.
4. Capstone runbook and evidence bundle are reviewer-friendly and reproducible.

---

## Phase 4 — grooming status (Portfolio Workbench: visible, navigable, steerable data)

Spec: [ARCHITECTURE.md §14](ARCHITECTURE.md). Roadmap: [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)
Phase 4 / decision D10. These are **UI-forward** slices over already-persisted state — most need no
contract change. Builds run as normal PRs (Opus in-context or a Sonnet builder), each green on
`make check`, reviewed, merged, then deployed via `deploy.yml`.

| WS | Scope | Depends on | Contract | Grooming |
|----|-------|-----------|----------|----------|
| 4A | Sidebar navigation shell (repurpose empty left panel) | live web app | none | ✅ Ready |
| 4B | Portfolio view — experience tree + per-entry recorded stories | 4A shell | none | ✅ Ready |
| 4C | Steerable grill — "grill me about this" pins `grill_frontier` | 4B (tree UI) | none | ✅ Ready |
| 4D | Add an experience/project manually (portfolio-mutation seam) | 4B | none | ✅ Ready |
| 4E | Highlight/pin an experience for tailoring priority (DEFERRED) | 4B/4D | **+minor** | ◐ Draft (deferred) |

### Sequencing for Phase 4
1. **4A first** — it introduces the sidebar/router shell the other slices hang off of.
2. **4B** next — the read-only experience tree + per-entry story view (also the surface 4C/4D act on).
3. **4C and 4D** can follow 4B (4C is a frontier write; 4D adds the mutation seam). Low coupling; either order.
4. **4E deferred** — build only on explicit request (it's the one contract bump).

Shared read-first for every 4x builder: [ARCHITECTURE.md §14](ARCHITECTURE.md) + §2 (layering: no
workflow logic in UI) + the current `web/` modules (`streamlit_app.py`, `dashboard.py`, `grill_ui.py`,
`session_loader.py`) + the Shared preamble & Definition of Done in
[AGENT_EXECUTION_PROMPT.md](AGENT_EXECUTION_PROMPT.md).

### ✅ 4A — sidebar navigation shell (build first)

```text
You are WS 4A for CareerEngine. Repurpose the near-empty Streamlit left panel into a persistent
navigation sidebar for the web app. This is a pure presentation/routing refactor — NO schema, NO
contract, NO workflow-logic changes.

Stay in: web/streamlit_app.py, web/dashboard.py, and tests. Do NOT touch schema.py/config.py, the graph,
or the persistence layer.

Scope:
- Build a persistent st.sidebar with: the signed-in identity + "Sign out" (already present), and a nav
  control (radio or buttons) that sets st.session_state["view"] among: Dashboard, Portfolio, Grill,
  Tailor. Keep the existing view-routing keys ("dashboard"/"grill"/"tailor"); add "portfolio" (its view
  is built in 4B — for 4A a placeholder that says "coming next" is fine).
- Show a compact tracked-applications list in the sidebar (company — title — status) read from the
  already-loaded UserWorkspace; empty-state text when none.
- The nav must not lose in-progress grill state on rerun (only switch the view key; do not clear
  grill session_state). Selecting the current view is a no-op.
- Keep the main column uncluttered — move only navigation/identity/app-list into the sidebar.

Acceptance criteria (named tests required — the dashboard/view builders are already tested without a
real Streamlit; follow that injectable pattern):
- A nav view-model builder (pure function) returns the correct nav items + active view given
  session_state; unit-tested without Streamlit.
- The applications-list view-model renders company/title/status from a fixture UserWorkspace, and shows
  the empty-state string when there are no applications.
- Switching nav updates the view key and does not mutate grill/tailor session_state.

DoD:
- make check green. No workflow logic in the UI. No contract change.
- Report READY FOR REVIEW with criterion->test map.
```

### ✅ 4B — portfolio view (peruse recorded details per experience)

```text
You are WS 4B for CareerEngine. Add a read-only "Portfolio" view that shows the user what has been
recorded about them, per experience. Reads the persisted discovery state only — NO contract change.

Stay in: web/streamlit_app.py (route the "portfolio" view), a new web/portfolio.py (view-model +
injectable renderer, mirroring web/dashboard.py), a small pure helper (e.g. stories_by_entry in
schema.py's helper region OR web/portfolio.py), web/session_loader.py (reuse; extend only if needed),
and tests.

Scope:
- Load the user's latest CareerEngineState via web.session_loader.try_load_latest_discovery_state.
- Render work_timeline as an experience tree/list (newest first), each Entry showing title, org, dates,
  type, and status (documented / needs_quantifying / grilled / summarized / skipped).
- Selecting an Entry shows: its recorded StarStory items (grouped by StarStory.entry_id == Entry.entry_id),
  each story's situation/task/action/result + a "metric validated" indicator; and the Entry's existing
  bullets. Entries with no stories yet show a clear "not grilled yet" state.
- Pure view-model built and unit-tested WITHOUT Streamlit (follow build_dashboard_view). The Streamlit
  renderer is a thin pass-through.
- Best-effort/non-fatal: a load failure shows an empty portfolio, never crashes (session_loader already
  swallows backend errors).

Acceptance criteria (named tests required):
- stories_by_entry groups stories correctly by entry_id and ignores/creates-empty for entries with none.
- The portfolio view-model lists entries with their status and attaches the right stories to each entry
  from a fixture CareerEngineState.
- An entry with zero linked stories yields the "not grilled yet" marker in the view-model.
- Empty/failed state yields an empty-but-valid view-model (no exception).

DoD:
- make check green. No contract change. No workflow logic in UI.
- Report READY FOR REVIEW with criterion->test map.
```

### ✅ 4C — steerable grill (jump the grill to a chosen experience)

```text
You are WS 4C for CareerEngine. Let the user steer the grill onto a specific experience instead of the
reverse-chronological default. grill_frontier is already documented jumpable and honored by the router —
this slice sets it before the next grill turn. NO contract change, NO new graph edges.

Stay in: web/portfolio.py (or web/grill_ui.py) for the "Grill me about this" action, web/streamlit_app.py
routing, and a small tested write path to set grill_frontier on the persisted session (extend the
portfolio-mutation seam from 4D if it lands first, else add a minimal set_grill_frontier(session_id,
entry_id) helper using FirestoreSessionService with the same asyncio.run sync bridge as session_loader),
and tests.

Scope:
- In the Portfolio experience tree (4B), each entry gets a "Grill me about this" action.
- The action sets grill_frontier = that entry's entry_id on the user's latest session state (persisted),
  then routes to the grill view so the next turn targets that entry.
- If no session exists yet, fall back to starting a fresh grill seeded so that entry is the frontier.
- Do not change one-node-per-run semantics or the checkpoint brake.

Acceptance criteria (named tests required):
- Setting the frontier writes grill_frontier = entry_id to the loaded state and it survives a reload
  (use the fakes in tests/fakes.py — no live Firestore).
- After a frontier jump, the next grill turn targets the chosen entry (assert via the existing
  graph/router tests or a focused unit test of the frontier-selection logic).
- No-session case starts a clean grill without raising.

DoD:
- make check green. No contract change.
- Report READY FOR REVIEW with criterion->test map.
```

### ✅ 4D — add an experience/project manually (portfolio-mutation seam)

```text
You are WS 4D for CareerEngine. Let a user add a remembered project/experience (the long-tenure breadth
fix) so it appears in the tree and is immediately grillable. The model already supports this
(Entry.source == "manual"); introduce the reusable, tested portfolio-mutation seam (ARCHITECTURE
AD-14.2). NO contract change.

Stay in: a new database/portfolio_mutations.py (or web/portfolio_store.py) for the read-modify-write
seam, web/portfolio.py for the "Add experience" form + wiring, web/streamlit_app.py routing, and tests.
Do NOT write session state ad hoc from the UI — go through the seam.

Scope:
- Seam: a sync façade (asyncio.run bridge, like session_loader/workspace_store) that loads the user's
  latest session state, appends/edits an Entry, stamps CONTRACT_VERSION, and saves via
  FirestoreSessionService. If no session exists, create one seeded with the new Entry.
- UI: an "Add experience" form capturing title, org, type (ExperienceType), start/end date, optional
  bullets. New entries are source="manual", status=NEEDS_QUANTIFYING.
- After add, the entry shows in the 4B tree and can be grilled (pairs naturally with 4C's jump action).
- Guard: reject empty title; dates optional; no secrets ever enter the Entry.

Acceptance criteria (named tests required — use tests/fakes.py, no live Firestore):
- add_manual_entry appends an Entry with source="manual" and the given fields to work_timeline and it
  survives a reload.
- Adding when no prior session exists creates a session containing exactly that entry.
- The saved document is stamped with CONTRACT_VERSION and carries no secret fields.
- Concurrent-write posture is documented (last-write-wins on the single-user demo — see AD-14.4);
  no correctness test required beyond single-writer.

DoD:
- make check green. No contract change.
- Report READY FOR REVIEW with criterion->test map.
```

### ◐ 4E — highlight/pin an experience (DEFERRED — needs a contract bump)

Not launchable yet. When requested: add `Entry.highlighted: bool` (additive → minor `CONTRACT_VERSION`
bump + tag), surface a pin toggle in the 4B tree, and have the tailor node prefer highlighted stories.
Groom fully (files + named tests + the version-bump note) at build time, per the version-gate rule.

### Phase 4 exit gate

Phase 4 (4A–4D) is complete when, on the deployed dev app, a user can: navigate via the sidebar; open
Portfolio and read the STAR stories recorded per experience; add a remembered project under a long
tenure; and launch a grill targeted at a chosen experience — all with `make check` green and **no
contract break**.

---

## Not groomed here

Phase 3 hardening/eval and post-v1 backlog remain intentionally out of launch scope for this pass.
