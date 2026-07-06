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
3. ✅ **Phase 4 — Portfolio Workbench** (4A–4D) — SHIPPED & deployed (PRs #15/#16/#17). 4E deferred.
4. ✅ **Phase 7 — Job Discovery web surface** (PRs #38–42, contract v2.8.0) — COMPLETE. ⚠️ Needs redeploy (Phase 8A).
5. **Phase 8 — Operational hardening** — groomed below; not started.
6. **Phase 9 — Replace Streamlit; proper product UI** — not yet groomed; groom after Phase 8 ships.
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
| 4A | Sidebar navigation shell (repurpose empty left panel) | live web app | none | ✅✅ SHIPPED (PR #15) |
| 4B | Portfolio view — experience tree + per-entry recorded stories | 4A shell | none | ✅✅ SHIPPED (PR #16) |
| 4C | Steerable grill — "grill me about this" pins `grill_frontier` | 4B (tree UI) | none | ✅✅ SHIPPED (PR #17) |
| 4D | Add an experience/project manually (portfolio-mutation seam) | 4B | none | ✅✅ SHIPPED (PR #17) |
| 4E | Highlight/pin an experience for tailoring priority (DEFERRED) | 4B/4D | **+minor** | ◐ Draft (deferred) |

> **Status:** 4A–4D built, Copilot-reviewed, merged, and deployed to dev (467 tests, no contract
> change). 4C+4D shipped together (they share `web/portfolio_store.py`). 4E remains deferred.

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

## Phase 7 — Job Discovery web surface (bring discovery from CLI into the product UI)

> **Status: ✅ COMPLETE 2026-07-06** (7A PR #38 · 7B PR #39 · 7C). Turned the Phase 6 two-agent discovery
> loop (was CLI-only, `career-engine discover`) into a **product feature**: the "Jobs" view in the web app.
> Spec: [ARCHITECTURE.md §15.6](ARCHITECTURE.md). Reused the discovery engine wholesale (`discovery/`); this
> phase was the **web surface + preference persistence** around it — no change to the agents/loop.

### The flow (user journey)
1. Signed-in user clicks **"Jobs"** in the sidebar (new nav entry).
2. **Preferences** (persisted, editable): target roles · nice-to-haves · dealbreakers. Pre-filled from the
   saved profile; first-time users get the operator defaults as a starting point. Saved to the workspace.
3. **"Find jobs"** → runs the live loop (Scout ⇄ MCP ⇄ Primary) on the user's **BYOK key** (Pro-tier
   `ModelEvaluator`), gated behind a button + spinner (like Tailor). Bridged into Streamlit's sync model via
   the existing `web.async_runner.run_async` (the Scout is async).
4. Results render: **✅ Strong matches** and **🟡 For review**, each with company · title · location · a
   live URL · the **AI rationale**. Accepted jobs persist to the `LedgerStore` (Firestore) → idempotent
   re-runs (already-seen jobs hard-reject), and prior results show on entry.
5. Each job has **"Tailor résumé to this"** → feeds the discovered JD into the existing Tailor flow (closes
   discover → tailor in the UI, mirroring the CLI's `--tailor-session`).

### Contract
- Add `discovery_preferences: SessionPreferences` to `UserWorkspace` (additive → **minor bump v2.8.0**;
  backward-compatible default via `default_factory`). `SessionPreferences` already exists (v2.5.0).

### Sequencing (reviewable increments, one PR each)
- **7A — persist discovery preferences (build first; contract v2.8.0).** `UserWorkspace.discovery_preferences`
  + a `web/preferences_store.py` seam (`load_discovery_preferences` / `save_discovery_preferences`, copy-on-write,
  mirrors `profile_store`). Tests: roundtrip, preserve-others, backward-compat, pins→2.8.0.
- **7B — the Jobs view (the meat).** `web/jobs.py` (pure `build_jobs_view` + injectable `render_jobs`, like
  `web/portfolio.py`); a web discovery runner (`web/jobs_runner.py`: builds Scout + `PrimaryAgent`(BYOK
  `ModelEvaluator`) + Firestore `LedgerStore`, runs `discover()` via `run_async`, records accepted, returns a
  `DiscoveryResult`); the preferences form; nav entry `("jobs", "Jobs")` in `web/navigation.py` + routing in
  `web/streamlit_app.py`; load persisted jobs on entry. Tests: view-model mapping, render callbacks (fake `st`),
  runner wiring with a fake Scout + in-memory store (offline, no key).
- **7C — "Tailor to this job".** A per-job button that stashes the discovered `raw_description` as the Tailor
  JD (`session_state`) and routes to the Tailor view (which pre-fills it). Tests: the handler sets the JD +
  view; Tailor consumes a pre-filled JD.

### Design rules (keep)
- **Reuse the engine**: no changes to `discovery/scout.py` / `primary.py` / `job_source.py` / `mcp_server.py` —
  Phase 7 only adds the web surface + preference persistence.
- **Two-layer UI** (pure view-model + injectable renderer) so it's tested without a Streamlit runtime, exactly
  like `dashboard.py` / `portfolio.py`.
- **BYOK-gated** (uses `_resolve_byok_key`); render gated behind a button (WeasyPrint-style cost discipline);
  best-effort persistence never blocks the UI; no secrets stored.

### Phase 7 exit gate
On the web app, a signed-in user can set + save job preferences, click "Find jobs", see ranked live matches
with AI rationale, and tailor a résumé to a chosen job — all in the UI, `make check` green, contract bumped
additively to v2.8.0. Docs reconciled so discovery is a **product feature**, not a CLI-only demo.

---

## Not groomed here

Phase 3 hardening/eval and post-v1 backlog remain intentionally out of launch scope for this pass.

---

## Phase 8 — Operational hardening (post-Phase-7 productionisation)

> **Status: ⬜ Not started.** All Phase 7 code (PRs #38–42) is on master and `make check` green.
> [PROGRESS.md §Phase 8](PROGRESS.md) is the canonical status tracker.
> Spec context: [ARCHITECTURE.md §15.5–15.6](ARCHITECTURE.md); security context: [SECURITY.md](SECURITY.md).

### How to launch these tickets

Each ticket below contains a complete, self-contained build prompt. Paste the code-block content
verbatim into a Sonnet subagent (worktree-isolated). The prompt includes all the context the
subagent needs. **Subagents are instructed to PAUSE and report back rather than assume** — if
something doesn't match what the prompt describes, the agent stops and explains the discrepancy.
Review the report, clarify, then re-launch.

PR workflow (updated — Claude subscription ended; Gemini 2.5 Pro is the pre-push review gate):
```
new branch → subagent builds → make check green →
Gemini 2.5 Pro review subagent (PASS or CHANGES REQUESTED → fix → re-review) →
push → gh pr create → Copilot review → address → squash-merge → update PROGRESS.md
```
The Gemini review subagent prompt template (use for every ticket):
```
You are a code reviewer for CareerEngine. Review the diff on branch <branch>.
Read the ticket spec in GROOMING.md §<ticket> for the intended scope and acceptance criteria.
1. Re-run `make check` (and `make tf-check` if Terraform changed). Report exit codes.
2. For each changed file, verify: scope boundary respected, acceptance criteria met, no new
   security issues (OWASP Top 10 lens), no contract change without a VERSION bump.
3. Return exactly: PASS (with any non-blocking nits) or CHANGES REQUESTED (with a numbered
   must-fix list). Do not approve if any must-fix remains.
```

### The goal in plain language

The Jobs Discovery feature is **fully wired in code** but invisible in the live app because the Cloud Run
deployment hasn't been refreshed. Once redeployed (8A), the Jobs button will appear in the sidebar. Two
other gaps keep the product from being operationally sound at any scale:

1. **Sweep never fires** — Cloud Scheduler PUTs a 14-day pending-action reminder job, but the endpoint it
   targets 404s because `jobs/sweep_endpoint.py` (the framework-agnostic handler) was never mounted behind
   an HTTP route. Fix: promote the sweep to a **Cloud Run Job** triggered by Scheduler, removing the need
   for an HTTP server entirely.

2. **BYOK keys bleed across users** — `_client_factory` in `workflows/nodes.py` is a module-level mutable
   global. When user A's grill call sets the factory to their key, a concurrent user B's request can
   inherit that client. Under Cloud Run's default concurrency (no longer `concurrency=1` since PR #14
   reverted it), this is a real concurrency hazard. Fix: `contextvars.ContextVar` for per-async-context
   factory override, captured at submission time via `contextvars.copy_context()`.

The remaining items (8B dashboard CTA, 8E deployer-SA, 8F HITL dashboard) are improvements or
security hygiene that don't block the core product.

### Launch order

| Ticket | Scope | Size | Depends on | Grooming |
|--------|-------|------|-----------|----------|
| 8A | Redeploy to dev | Ops (no code) | none | ✅ Ready |
| 8B | Dashboard "Find jobs" CTA | Tiny (1 file) | 8A ideally first | ✅ Ready |
| 8C | Wire sweep endpoint (Cloud Run Job) | Medium | 8A (deploy validates) | ✅ Ready |
| 8D | Multi-user model-client isolation | Significant (design-first) | none (but read the design section) | ◐ Draft — needs user sign-off on the design before implementation |
| 8E | Deployer-SA least-privilege | Terraform-only | none | ◐ Draft (see SECURITY.md for the role list) |
| 8F | HITL TTL/override dashboard | Medium-new feature | none | ⬜ To groom |
| 8G | Custom domain via Cloudflare + Cloud Run | Terraform (2 new modules) | 8A (deploy must be live) | ✅ Ready |

---

### ⬜ 8A — Redeploy to dev (operational, no code change)

**What:** Dispatch the existing manual deploy workflow so the Cloud Run dev image reflects master
(PRs #38–42). No files to change.

**Command:**
```bash
gh workflow run deploy.yml --ref master -f environment=dev
```

**Verification:** Visit https://career-engine-dev-app-ontyg6kaja-uc.a.run.app, sign in with Google,
confirm the sidebar shows **Dashboard / Portfolio / Grill / Jobs / Tailor**. Click Jobs and confirm the
preferences form + "Find jobs" button appear (no Gemini key → the info message is expected).

**No PR needed.** Record the outcome in [HANDOFF.md](HANDOFF.md).

---

### ⬜ 8B — Dashboard "Find jobs" CTA

> Read first: `web/dashboard.py`, `web/streamlit_app.py` (render_dashboard call + the existing
> Grill/Tailor buttons pattern).

**What:** The dashboard (`render_dashboard` in `web/dashboard.py`) already has "Start / continue
grilling" (primary) and "Tailor a resume" buttons but no Jobs entry point. Users have to discover the
sidebar themselves. Add a third button so all three core flows are reachable from the landing page.

**Scope:** `web/dashboard.py` only (view-model flag + renderer button). Tests already cover the
dashboard renderer via a fake `st`; add one more assertion.

```text
You are WS 8B for CareerEngine. Add a "Find jobs" button to the dashboard so Job Discovery is
reachable from the landing page.

Stay in: web/dashboard.py (add DashboardView.can_find_jobs: bool = True field; add button in
render_dashboard), and the existing dashboard tests in tests/test_nodes.py (or wherever the
render_dashboard / build_dashboard_view tests live — check with grep).

Scope:
- Add a `can_find_jobs: bool = True` field to DashboardView (mirrors the existing can_tailor
  invariant; always True; never gates).
- In render_dashboard, after the "Tailor a resume" button, add:
    st.button("Find jobs", on_click=lambda: st.session_state.__setitem__("view", "jobs"))
  The on_click pattern is identical to the existing Grill and Tailor buttons.
- Add a test asserting: render_dashboard emits a "Find jobs" button; clicking it sets view=jobs.

Acceptance criteria (named tests required):
- test_dashboard_find_jobs_button_present: a rendered DashboardView has a "Find jobs" button.
- test_dashboard_find_jobs_routes_to_jobs_view: the button's on_click sets session_state["view"] = "jobs".
- Existing dashboard tests remain green (no regression).

DoD:
- make check green.
- No contract change.
- Gemini 2.5 Pro review PASS (use the review prompt template in GROOMING.md §Phase 8 header;
  address any CHANGES REQUESTED before pushing the branch).
- Report READY FOR REVIEW with criterion→test mapping.
```

---

### ⬜ 8C — Wire the pending-action sweep (Cloud Run Job approach)

> Read first: `jobs/pending_action_sweep.py`, `jobs/sweep_endpoint.py`, `main.py` (existing CLI
> commands pattern), `infrastructure/modules/` (Cloud Run + Scheduler modules),
> `infrastructure/envs/dev/main.tf`, [ARCHITECTURE.md §8](ARCHITECTURE.md).

**What / Why:** `jobs/pending_action_sweep.py` (`run_sweep`) exists and is tested. `jobs/sweep_endpoint.py`
is a framework-agnostic OIDC-verified HTTP handler built to be mounted behind a route — but nothing mounts
it, so Cloud Scheduler gets 404s. Rather than add an HTTP framework alongside Streamlit, the cleaner
approach is a **Cloud Run Job** (a one-shot container run, not a persistent service). Cloud Scheduler can
trigger a Cloud Run Job via the Jobs Execute API with standard service-account IAM auth — no OIDC token
exchange, no HTTP server required. The existing `jobs/sweep_endpoint.py` is retained (not deleted) as a
secondary HTTP-triggered path, but it is no longer the primary wiring.

**Design:**
- Add `career-engine sweep` CLI command in `main.py` → `jobs/sweep_cli.py` (thin, mirrors `discovery/cli.py`).
  Calls `run_sweep(store=FirestoreWorkspaceStore(), today=date.today().isoformat())` and exits 0/1.
- Add a `jobs/sweep_cli.py` module (the testable core — resolves store, calls `run_sweep`, logs counts).
- In Terraform: add a Cloud Run Job resource (`google_cloud_run_v2_job`) in the scheduler module (or a
  new `sweep_job` module) that runs the same Docker image with `command: ["career-engine", "sweep"]`.
  Update the Scheduler job from a `pubsub` / HTTP push target to a Cloud Run Jobs execute target
  (`google_cloud_scheduler_job` with `http_target` pointing to the Jobs Execute API endpoint, SA-authed).
- No new container image needed — the existing `Dockerfile` already installs the package.

```text
You are WS 8C for CareerEngine. Wire the pending-action sweep so Cloud Scheduler actually triggers it.

Approach: Cloud Run Job (not HTTP endpoint). Add a `career-engine sweep` CLI command, then update
Terraform to run it as a Cloud Run Job on schedule.

Stay in: main.py (add sweep command), jobs/sweep_cli.py (new — the testable core), tests/ (new
test for the CLI + store integration), infrastructure/modules/scheduler/ or a new sweep_job module,
infrastructure/envs/dev/main.tf (add the job + scheduler wiring).

Do NOT delete jobs/sweep_endpoint.py — keep it as an alternative HTTP-triggered path with its doc comment.
Do NOT modify jobs/pending_action_sweep.py (the pure logic is already correct).

Scope:
  CLI:
  - Add `career-engine sweep` in main.py (parallel to `career-engine discover`).
  - jobs/sweep_cli.py: resolve_sweep_store() (Firestore, with loud in-memory fallback), run_sweep_command()
    (calls run_sweep, logs "Swept N workspaces, M actions triggered", returns counts). Pure + testable.
  Terraform:
  - Add a Cloud Run Job resource that runs the same image with ["career-engine", "sweep"] as the command.
  - Update the Cloud Scheduler job to target the Cloud Run Jobs Execute API endpoint (POST
    https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run) with the
    deployer/scheduler SA having roles/run.invoker on the job.
  - make tf-check green in envs/dev.

Acceptance criteria (named tests required):
  - test_sweep_cli_calls_run_sweep: resolve_sweep_store() returns a store; run_sweep_command() calls
    run_sweep with it and returns (workspaces_processed, actions_triggered) counts.
  - test_sweep_cli_store_fallback: if Firestore construction raises, logs a warning and uses in-memory
    store (does not crash).
  - Existing sweep tests (test_pending_action_sweep.py, test_jobs_handlers.py) remain green.
  - make tf-check green.

DoD:
  - make check green (including new sweep CLI tests).
  - make tf-check green.
  - No contract change.
  - jobs/sweep_endpoint.py retained; doc comment updated to note the Cloud Run Job is the primary path.
  - Gemini 2.5 Pro review PASS (use the review prompt template in GROOMING.md §Phase 8 header;
    address any CHANGES REQUESTED before pushing the branch).
  - Report READY FOR REVIEW with criterion→test mapping.
```

---

### ⬜ 8D — Multi-user model-client isolation (design-first)

> Read first: `workflows/nodes.py` (the `_client_factory` global, `set_model_client_factory`,
> `_get_model_client`), `web/async_runner.py` (the `run_async` loop), `web/grill_ui.py`
> (how the web grill injects a BYOK key today).

**The problem:** `_client_factory` in `workflows/nodes.py` is a module-level `Callable[[], ModelClient]`
that `set_model_client_factory()` mutates globally. Any caller that sets it races with every other
concurrent request. Cloud Run's default concurrency (multiple simultaneous requests per instance) means
user A's BYOK key can be used to generate user B's résumé content — a privacy and billing violation.

**Proposed design (for user review before coding):**

```
ContextVar approach:

1. Add to workflows/nodes.py:
     _factory_ctx: contextvars.ContextVar[Callable[[], ModelClient] | None] = \
         contextvars.ContextVar("_model_client_factory", default=None)

2. set_model_client_factory_for_context(factory) sets _factory_ctx.set(factory).
   The existing set_model_client_factory(factory) becomes a module-level-only setter
   (used by tests + CLI where there is no concurrency) — kept for backward compat.

3. _get_model_client() checks _factory_ctx.get() first; falls back to _client_factory().

4. In web/async_runner.run_async (or wherever the coroutine is submitted to the
   background loop): capture ctx = contextvars.copy_context() at submission time, then
   run the coroutine inside ctx.run(...). This propagates the caller's ContextVar state
   into the background task.
   Concretely: replace loop.run_until_complete(coro) with a Future + ctx.run approach,
   or use asyncio.Task with copy_context() explicitly.

5. web/grill_ui.py calls set_model_client_factory_for_context(byok_factory) before
   calling run_async.

No contract change. The test helpers that call set_model_client_factory remain unchanged
(they run serially with no concurrency).
```

⚠️ **This ticket requires the user to review and sign off on the design above before any code is
written.** The risk is subtle: if `run_async`'s context propagation is wrong, the BYOK key silently
fails to propagate and every grill falls back to the default (Free) client — a regression harder to
notice than a crash. Do NOT proceed with implementation until the design is confirmed.

```text
You are WS 8D for CareerEngine. Fix the process-global model-client factory so concurrent web users
cannot bleed BYOK keys across requests.

⚠️ READ THE DESIGN NOTE in GROOMING.md §8D IN FULL before writing any code. Implement exactly the
ContextVar approach described there — do not improvise.

Stay in: workflows/nodes.py (add ContextVar, add set_model_client_factory_for_context, update
_get_model_client), web/async_runner.py (propagate context into background task), web/grill_ui.py
(call the new context setter), tests/test_nodes.py (new isolation tests).

Scope (strict — do NOT touch grill nodes, graph edges, or any other web/* files):
- Add _factory_ctx ContextVar to workflows/nodes.py.
- Add set_model_client_factory_for_context(factory) (context-local override).
- _get_model_client(): check _factory_ctx.get() first, fall back to _client_factory().
- web/async_runner.run_async: capture ctx = contextvars.copy_context() before submitting;
  ensure the coroutine runs within that captured context.
- web/grill_ui.py: replace any set_model_client_factory call with set_model_client_factory_for_context.
- Keep the module-level set_model_client_factory for CLI/test backward compat.

Acceptance criteria (named tests required):
- test_context_factory_isolation: two concurrent tasks each setting different factories via
  set_model_client_factory_for_context get different clients (no bleed).
- test_context_factory_fallback: a context with no override falls back to the module-level factory.
- test_run_async_propagates_context: a factory set before run_async() is visible inside the
  submitted coroutine.
- Existing tests that use set_model_client_factory() remain green (no regression).

DoD:
- make check green.
- No contract change.
- No changes to graph nodes, routing logic, or existing API surfaces beyond the new context setter.
- Gemini 2.5 Pro review PASS (use the review prompt template in GROOMING.md §Phase 8 header;
  address any CHANGES REQUESTED before pushing the branch).
- Report READY FOR REVIEW with criterion→test mapping and a written explanation of how copy_context
  propagation was verified.
```

---

### ◐ 8E — Deployer-SA least-privilege curation (Terraform-only)

> Read first: [SECURITY.md](SECURITY.md) "Required next review" section; `infrastructure/modules/`.

**What:** The `career-engine-deployer` service account was granted broad project-level roles to get the
initial deploy working. Narrow them to only what each Terraform resource actually needs (Cloud Run deploy,
Artifact Registry push, Firestore rules, Secret Manager reads for the runtime SA, etc.).

**This is Terraform-only** (`infrastructure/` files). No application code changes.

Acceptance criteria:
- `make tf-check` green in both envs.
- The deployer SA's bound roles are listed in [SECURITY.md](SECURITY.md) "Post-8E role inventory" section.
- A `terraform plan` on a fresh environment shows no diff from the stated desired state.

DoD:
- `make tf-check` green.
- [SECURITY.md](SECURITY.md) updated with the role inventory.
- No application code changes.

---

### ⬜ 8F — HITL TTL/override dashboard (lower priority; not yet groomed)

**What:** A dedicated view for managing discovery HITL decisions: list dismissed companies (from
`InteractionLedger.rejected_companies`), allow un-dismissing a company (reverse a "Not interested"),
optionally show when a dismissal was added. A full TTL (auto-expiry) mechanism on the `rejected_companies`
list is also roadmap but deferred to a separate sub-ticket once the base view ships.

**Dependencies:** none on the code side; the `LedgerStore` already has `add_rejected_company` + the
`rejected_companies` set on the ledger. Needs a `remove_rejected_company` method on `LedgerStore`.

**Status:** ⬜ To groom — the user flow and Firestore path need to be specified before a build spec is written.

---

### ✅ 8G — Custom domain `career-engine.bitcrafty.cloud` via Cloudflare + Cloud Run

> Read first: `infrastructure/modules/cloud_run/main.tf`, `infrastructure/envs/dev/main.tf`,
> `infrastructure/envs/dev/variables.tf`, `docker-entrypoint.sh` (how `CE_AUTH_REDIRECT_URI`
> becomes `redirect_uri` in `secrets.toml`).

**Goal:** Serve the deployed web app at `https://career-engine.bitcrafty.cloud` instead of (or in
addition to) the raw `*.run.app` URL. Everything infrastructure must be Terraform — no manual
Cloudflare dashboard clicks, no manual `gcloud` commands for the ongoing state.

**Approach: Cloudflare DNS-only (grey cloud) + Cloud Run domain mapping (GCP-managed SSL)**

- Cloudflare acts as the DNS resolver only (`proxied = false`). GCP provisions and renews the
  SSL certificate for the custom domain via `google_cloud_run_domain_mapping`.
- Why DNS-only (not Cloudflare proxy): Cloud Run domain mapping SSL provisioning works by
  validating that the DNS A/AAAA records resolve directly to GCP's load-balancer IPs. With
  Cloudflare proxy (orange cloud) enabled, the resolved IP is Cloudflare's, not GCP's, and SSL
  provisioning never completes. DNS-only (grey cloud) keeps the resolution path direct.
- Cloudflare proxy can be enabled AFTER SSL provisioning is confirmed, but the recommended steady
  state is DNS-only — it avoids Cloudflare WebSocket quirks with Streamlit and keeps the
  architecture simpler.

**What changes in Terraform (all IaC, zero manual resource creation):**

```
New modules:
  infrastructure/modules/cloud_run_domain_mapping/
    main.tf   — google_cloud_run_domain_mapping resource + outputs
    variables.tf

  infrastructure/modules/cloudflare_dns/
    main.tf   — cloudflare provider + cloudflare_dns_record resources
                (verification TXT + A/AAAA records from domain mapping)
    variables.tf

Changes to existing files:
  infrastructure/envs/dev/main.tf
    — add cloudflare provider block (api_token from TF_VAR_cloudflare_api_token)
    — add module "domain_mapping" call
    — add module "cloudflare_dns" call (depends_on domain_mapping)
    — update CE_AUTH_REDIRECT_URI env to "https://${var.custom_domain}/_stcore/oauth2callback"

  infrastructure/envs/dev/variables.tf
    — custom_domain (string, default "career-engine.bitcrafty.cloud")
    — cloudflare_zone_id (string, bitcrafty.cloud zone id from Cloudflare dashboard)
    — cloudflare_api_token (string, sensitive — set via TF_VAR_cloudflare_api_token, never in state)
    — google_domain_verification_txt (string — TXT record value from Google domain verification)
```

**Detailed resource design:**

`infrastructure/modules/cloud_run_domain_mapping/main.tf`:
```hcl
resource "google_cloud_run_domain_mapping" "custom" {
  project  = var.project_id
  location = var.region
  name     = var.domain    # e.g. "career-engine.bitcrafty.cloud"

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = var.service_name  # the Cloud Run service name (not the URL)
  }

  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}

output "resource_records" {
  description = "DNS records to add to Cloudflare (populated after GCP provisions the mapping)."
  value       = google_cloud_run_domain_mapping.custom.status[0].resource_records
}
```

`infrastructure/modules/cloudflare_dns/main.tf`:
```hcl
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 4.0, < 5.0"
    }
  }
}

# Step 1: TXT record for Google domain ownership verification.
# Value comes from Google Webmaster Central / Cloud Console domain verification.
# Apply this first (targeted apply), complete verification, then apply the rest.
resource "cloudflare_dns_record" "verification" {
  zone_id = var.zone_id
  name    = var.subdomain                  # e.g. "career-engine"
  type    = "TXT"
  content = var.google_verification_txt    # e.g. "google-site-verification=..."
  ttl     = 300
  proxied = false
  comment = "Google domain ownership verification for Cloud Run domain mapping"
}

# Step 2: A/AAAA records from Cloud Run domain mapping.
# resource_records is a list of { name, type, rrdata } objects.
resource "cloudflare_dns_record" "cloud_run" {
  for_each = { for r in var.resource_records : r.type => r }

  zone_id = var.zone_id
  name    = var.subdomain
  type    = each.value.type    # "A" or "AAAA"
  content = each.value.rrdata
  ttl     = 300
  proxied = false              # DNS-only: GCP manages SSL; keep grey cloud
  comment = "Cloud Run custom domain mapping — managed by Terraform"

  depends_on = [cloudflare_dns_record.verification]
}
```

**Apply order (two-phase, both Terraform):**

```
Phase 1 — DNS verification (one-time bootstrap):
  1. Obtain the Google domain verification TXT value:
       gcloud domains verify career-engine.bitcrafty.cloud
     (copy the TXT string it prints)
  2. Set TF_VAR_google_domain_verification_txt="<value>"
  3. terraform apply -target=module.cloudflare_dns.cloudflare_dns_record.verification
     (adds only the TXT record to Cloudflare)
  4. Wait ~30 s for DNS propagation, then complete verification:
       gcloud domains verify career-engine.bitcrafty.cloud --verify
     (or visit the Cloud Run Console > Domain Mappings > Verify)

Phase 2 — Full apply (steady state after bootstrap):
  5. terraform apply   (creates domain_mapping, A/AAAA records, updates CE_AUTH_REDIRECT_URI)
  6. SSL provisioning takes 5–30 min; check status:
       gcloud run domain-mappings describe --domain career-engine.bitcrafty.cloud --region us-central1
  7. Update the Google OAuth 2.0 client's authorized redirect URIs in the Cloud Console
     (MANUAL — one-time; add https://career-engine.bitcrafty.cloud/_stcore/oauth2callback
      alongside the existing *.run.app URI; both can coexist):
       Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs → edit the web client
```

**Ongoing (after first apply):** normal `terraform apply` workflow; domain mapping and DNS records are
idempotent. The `CE_AUTH_REDIRECT_URI` change in the Cloud Run env causes a new Cloud Run revision to
deploy automatically (no manual step).

**CI/CD secrets required (add to repo `vars`/`secrets` in GitHub):**
- `TF_VAR_cloudflare_api_token` — a Cloudflare API token scoped to `bitcrafty.cloud` DNS Edit.
  Create at Cloudflare Dashboard → My Profile → API Tokens → Create Token → "Edit zone DNS".
  Never commit; pass only via `TF_VAR_cloudflare_api_token` in the deploy workflow env.
- `TF_VAR_cloudflare_zone_id` — the zone ID for `bitcrafty.cloud` (not sensitive; in tfvars is fine).
- `TF_VAR_google_domain_verification_txt` — only needed for the one-time bootstrap apply.

```text
You are WS 8G for CareerEngine. Add Terraform resources to serve the web app at
https://career-engine.bitcrafty.cloud via Cloudflare DNS + Cloud Run domain mapping.

Read GROOMING.md §8G IN FULL before writing any code. Implement exactly the
two-module approach described there — cloud_run_domain_mapping + cloudflare_dns.

Stay in:
  infrastructure/modules/cloud_run_domain_mapping/  (new)
  infrastructure/modules/cloudflare_dns/             (new)
  infrastructure/envs/dev/main.tf                    (add modules + update CE_AUTH_REDIRECT_URI)
  infrastructure/envs/dev/variables.tf               (add custom_domain, cloudflare_zone_id,
                                                       cloudflare_api_token, google_domain_verification_txt)

Do NOT modify application code (web/, workflows/, etc.).
Do NOT change infrastructure/modules/cloud_run/main.tf — the domain mapping is a separate resource.

Acceptance criteria:
  - make tf-check green (fmt + validate) in infrastructure/envs/dev/.
  - A terraform plan (with dummy var values and no GCP credentials) shows the expected resource
    additions: google_cloud_run_domain_mapping + cloudflare_dns_record × N.
  - CE_AUTH_REDIRECT_URI env in the Cloud Run module call is
    "https://${var.custom_domain}/_stcore/oauth2callback".
  - The cloudflare provider block uses api_token = var.cloudflare_api_token (sensitive);
    the value never appears in .tf files or state.
  - cloudflare_dns_record resources all have proxied = false.
  - The verification TXT record and A/AAAA records are separate resources with correct depends_on.
  - infrastructure/README.md updated with: (a) the two-phase apply order, (b) the new TF_VAR_*
    secrets required, (c) the one-time manual OAuth client step.

DoD:
  - make tf-check green.
  - No application code changes.
  - README.md updated as above.
  - Gemini 2.5 Pro review PASS (use the review prompt template in GROOMING.md §Phase 8 header;
    address any CHANGES REQUESTED before pushing the branch).
  - Report READY FOR REVIEW with the full list of new/modified files.
```

---

### Phase 8 exit gate

Phase 8 is complete when:
- The deployed dev app shows the Jobs nav, preferences form, and "Find jobs" button; and the dashboard
  has a "Find jobs" action button (8A + 8B).
- Cloud Scheduler successfully triggers a sweep run (verified in Cloud Logging) with no 404 (8C).
- A written concurrency test proves two simultaneous grill contexts use different model clients (8D).
- `https://career-engine.bitcrafty.cloud` serves the app with a valid TLS certificate (8G).
- `make check` green and `make tf-check` green at every merged PR.
- [SECURITY.md](SECURITY.md) has a "Post-8E role inventory" section (8E).
- Every PR passed both Gemini 2.5 Pro review (pre-push) and Copilot review (on the PR).

---

## Phase 9 — Replace Streamlit; proper product UI *(⬜ not groomed — groom after Phase 8 ships)*

> **Status: ⬜ Not started. Not groomed.** Do not build anything in Phase 9 scope until Phase 8
> is complete and a proper architecture design session has been held. This section is a placeholder
> to ensure the decision is not lost.

### Why this phase exists

The current UI is scaffolding — Streamlit was the right tool to prove the product concept fast, but
it is not the right tool for a multi-user SaaS:

1. **`max_instances=1` is not a business choice — it is forced by Streamlit's architecture.**
   `session_state` is per-connection but the process is global; the model-client factory race (8D)
   is a direct symptom. Even with the ContextVar fix, Streamlit cannot safely serve concurrent users
   without significant workarounds.

2. **Streamlit WebSocket model creates friction** with CDN/proxy layers (Cloudflare, the custom
   domain work in 8G), and makes standard web patterns (SSR, SEO, mobile, deep-linking) impossible.

3. **Every UI feature is harder than it needs to be.** The two-layer view-model pattern (pure
   view-model + injectable `st`) was invented to work around Streamlit's untestability. With a
   proper frontend this scaffolding disappears.

4. **BYOK acquisition friction.** New users must create a Google AI Studio account, enable billing,
   and paste an API key before they see any value. A platform-owned free tier (3 grill sessions/month
   on Flash, paid tier unlocks Pro) would remove the top-of-funnel drop. The `AccessMode` enum
   (`FREE` / `BYOK`) already exists in the contract; Phase 9 adds `FREE_PLATFORM` routing.

### Intended scope (to be fully groomed)

- **Backend:** FastAPI service (replaces/wraps the existing workflow + discovery engine; no contract
  change needed — the engine is already well-separated from the UI layer).
- **Frontend:** Next.js (or equivalent) — SSR, proper auth, mobile, SEO, deep-linking.
- **Auth:** migrate from Streamlit native OIDC to a standard OAuth2/OIDC flow (the Firebase/Google
  OIDC backend is already correct; only the Streamlit-specific `st.login` surface changes).
- **Free tier:** platform-owned Gemini Flash quota (rate-limited per user_id); BYOK users bypass
  the quota. A `PlatformQuotaStore` (Firestore-backed counter, daily reset) gates the free tier.
- **Streamlit retained** for internal tooling / demos during transition; removed from the public
  Cloud Run service only after the new frontend is verified end-to-end.

### Pre-grooming design questions (resolve before writing any build specs)

1. Next.js + FastAPI vs. a full Next.js fullstack (with API routes)? What does the deployment
   topology look like on Cloud Run?
2. How does the grill loop (streaming, multi-turn, long-running) map to a REST or WebSocket API?
   The current ADK Runner pattern needs an HTTP-friendly wrapper.
3. Free tier quota: per-day or per-month? What's the unit economics ceiling at $0?
4. Streamlit transition: run both in parallel (A/B) or hard cutover?
5. What does the design system look like? (Color, typography, component library.)

**Do not groom further until Phase 8 ships.** Record any design decisions made before then in
[ARCHITECTURE.md](ARCHITECTURE.md) under a new §16.

