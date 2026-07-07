# CareerEngine — Grooming Archive (historical)

> **Status:** `historical` · retired build specs, read-only.
> **Purpose:** cold storage for **completed** grooming tickets (Phases 1.5–9). These are DONE and
> shipped; they are kept for provenance and semantic recall (grep / semantic search), **not** for
> active work. Do **not** load this file wholesale into an agent — retrieve the one section you need.
> Live/current build specs are in [../GROOMING.md](../GROOMING.md); status is canonical in
> [../PROGRESS.md](../PROGRESS.md); design rationale in [../ARCHITECTURE.md](../ARCHITECTURE.md).
>
> _Retired from GROOMING.md on 2026-07-07 as part of the context-management strategy
> ([../CONTEXT_STRATEGY.md](../CONTEXT_STRATEGY.md))._

---

## Phase 1.5 status (archived)

Phase 1.5 is complete (contract v2.0.0; 317 tests). _(Historical: at the time this was written, the
live grooming file tracked what remained — Phase 1.7 + Phase 2.)_

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
Read first: [ARCHITECTURE.md §2](../ARCHITECTURE.md) + [ARCHITECTURE.md §4](../ARCHITECTURE.md) + Shared preamble.

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
Read first: [ARCHITECTURE.md §12.2](../ARCHITECTURE.md) + [REFINED_PROJECT_PLAN.md](../REFINED_PROJECT_PLAN.md).

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
Read first: [ARCHITECTURE.md §12.3-§12.4](../ARCHITECTURE.md) + [HANDOFF.md](../HANDOFF.md).

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
Read first: [PROGRESS.md](../PROGRESS.md) Phase 1.3 deferred note.

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
Read first: [ARCHITECTURE.md §5](../ARCHITECTURE.md) + [ARCHITECTURE.md §8](../ARCHITECTURE.md).

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
Read first: [ARCHITECTURE.md §2](../ARCHITECTURE.md) + [ARCHITECTURE.md §8](../ARCHITECTURE.md).

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
Read first: [ARCHITECTURE.md §5](../ARCHITECTURE.md).

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
Read first: [ARCHITECTURE.md §8](../ARCHITECTURE.md).

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
Read first: [REFINED_PROJECT_PLAN.md](../REFINED_PROJECT_PLAN.md) decision D9.

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

Spec: [ARCHITECTURE.md §14](../ARCHITECTURE.md). Roadmap: [REFINED_PROJECT_PLAN.md](../REFINED_PROJECT_PLAN.md)
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

Shared read-first for every 4x builder: [ARCHITECTURE.md §14](../ARCHITECTURE.md) + §2 (layering: no
workflow logic in UI) + the current `web/` modules (`streamlit_app.py`, `dashboard.py`, `grill_ui.py`,
`session_loader.py`) + the Shared preamble & Definition of Done in
[AGENT_EXECUTION_PROMPT.md](../AGENT_EXECUTION_PROMPT.md).

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
> Spec: [ARCHITECTURE.md §15.6](../ARCHITECTURE.md). Reused the discovery engine wholesale (`discovery/`); this
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
> [PROGRESS.md §Phase 8](../PROGRESS.md) is the canonical status tracker.
> Spec context: [ARCHITECTURE.md §15.5–15.6](../ARCHITECTURE.md); security context: [SECURITY.md](../SECURITY.md).

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
| 8D | Multi-user model-client isolation | Significant | none | ✅ Ready — DI via closure injection (approved 2026-07-06) |
| 8E | Deployer-SA least-privilege | Terraform-only | none | ◐ Draft (see SECURITY.md for the role list) |
| 8F | HITL TTL/override dashboard | Medium-new feature | none | ⬜ To groom |
| 8G | Custom domain via Cloudflare + Cloud Run | Terraform (2 new modules) | 8A (deploy must be live) | ✅ SHIPPED (PR #46) |

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

**No PR needed.** Record the outcome in [HANDOFF.md](../HANDOFF.md).

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
> `infrastructure/envs/dev/main.tf`, [ARCHITECTURE.md §8](../ARCHITECTURE.md).

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

### ✅ 8D — Multi-user model-client isolation (DI via closure injection)

> Read first: `workflows/nodes.py` (the `_client_factory` global, `set_model_client_factory`,
> `_get_model_client`, and the 6 node functions that call it), `workflows/discovery_graph.py`
> (shim functions + `build_discovery_workflow` + `build_runner`), `web/grill_ui.py`
> (`_install_model_client` call site + how the session/runner is built), `web/streamlit_app.py`
> (tailor path `_install_model_client` call), `cli/app.py` (`_install_model_client` call sites).

**The problem:** `_client_factory` in `workflows/nodes.py` is a module-level `Callable[[], ModelClient]`
that `set_model_client_factory()` mutates globally. Any caller that sets it races with every other
concurrent request. Cloud Run's default concurrency (multiple simultaneous requests per instance) means
user A's BYOK key can be used to generate user B's résumé content — a privacy and billing violation.

**Approved design (2026-07-06): Explicit DI via closure injection at `build_discovery_workflow()`**

The industry-standard explicit DI approach was chosen over ContextVar. Correctness is enforced
structurally rather than relying on async context propagation — impossible to regress silently.

```
Design:

1. workflows/nodes.py: Add `_client: ModelClient | None = None` keyword-only parameter to each of
   the 6 node functions that call `_get_model_client()`. Inside each node:
     client = _client if _client is not None else _get_model_client()
   The module-level `_get_model_client()` and `set_model_client_factory()` remain unchanged
   (used by CLI/tests where there is no concurrency — backward compat).

2. workflows/discovery_graph.py: Add `model_factory: Callable[[], ModelClient] | None = None`
   parameter to `build_discovery_workflow()`. Make ALL shim functions closures inside
   `build_discovery_workflow()` (move them from module level into the function body) — each closure
   captures `model_factory` and passes `_client=model_factory() if model_factory else None` to the
   wrapped node call. Only shims for nodes that use _get_model_client need to pass _client; others
   are unchanged in behaviour but also become closures for consistency.
   Thread `model_factory` through `build_runner(model_factory=None)` → `build_discovery_workflow()`.

3. Call sites — replace _install_model_client with factory-at-build:
   - web/grill_ui.py: find where the runner is constructed (likely inside _setup_grill_session or
     similar); pass model_factory=lambda: ss["grill_client"] to build_runner(). Remove the
     _install_model_client(ss["grill_client"]) per-render call.
   - web/streamlit_app.py (tailor path ~line 684): pass model_factory to build_runner() instead of
     calling _install_model_client(client) after the fact.
   - cli/app.py: pass model_factory=lambda: client to build_runner() instead of calling
     _install_model_client(). Remove the _install_model_client helper function if no callers remain.

4. No contract change. Node pure function signatures gain one keyword-only parameter with a default
   of None — fully backward compatible with all existing call sites and tests.
```

```text
You are WS 8D for CareerEngine. Fix the process-global model-client factory so concurrent web users
cannot bleed BYOK keys across requests.

READ THE DESIGN NOTE in GROOMING.md §8D IN FULL before writing any code. Implement exactly the
explicit DI via closure injection approach described there — do NOT use ContextVar or any other
ambient state mechanism.

Files to read BEFORE writing any code (in this order):
1. workflows/nodes.py — identify the 6 node functions that call _get_model_client() (grep for
   "_get_model_client()" to find them); read their current signatures.
2. workflows/discovery_graph.py — read ALL shim functions and build_discovery_workflow() in full;
   understand how shims call node functions; read build_runner().
3. web/grill_ui.py — find _install_model_client call site(s) and how the runner/session is built.
4. web/streamlit_app.py — find the tailor path _install_model_client call (~line 684) and context.
5. cli/app.py — find both _install_model_client call sites (~lines 257 and 969) and the helper def.

PAUSE CONDITIONS — stop and report back without proceeding if:
- Any node function has a non-`(state)` positional signature that would require more than adding
  a `_client=None` keyword arg (e.g. if ADK already passes additional positional args).
- The shim functions are NOT simple thin wrappers over the pure node functions (e.g. if they
  already do multi-step logic that would be broken by making them closures).
- _install_model_client is called in more files than the three listed above.

Scope:
  workflows/nodes.py:
  - Add `*, _client: ModelClient | None = None` to each of the 6 node functions that call
    _get_model_client(). Replace `client = _get_model_client()` with
    `client = _client if _client is not None else _get_model_client()`.
  - Keep _get_model_client(), set_model_client_factory(), and _client_factory unchanged.

  workflows/discovery_graph.py:
  - Add `model_factory: Callable[[], ModelClient] | None = None` to build_discovery_workflow().
  - Move shim functions from module level into build_discovery_workflow() as closures.
    Each shim that wraps a node using _client passes `_client=model_factory() if model_factory else None`.
  - Add `model_factory: Callable[[], ModelClient] | None = None` to build_runner(); thread to
    build_discovery_workflow(model_factory=model_factory).

  web/grill_ui.py:
  - Find where build_runner() is called for the grill session. Pass
    model_factory=lambda: ss.get("grill_client") (where ss = st.session_state) to build_runner().
  - Remove the per-render _install_model_client(ss["grill_client"]) call.

  web/streamlit_app.py:
  - Find the tailor path that calls _install_model_client(client). Change it to pass
    model_factory=lambda: client to build_runner() instead.

  cli/app.py:
  - In both call sites, replace _install_model_client(model_client) with passing
    model_factory=lambda: model_client to build_runner().
  - If _install_model_client has no remaining callers, remove it.

  tests/test_nodes.py (or tests/test_model_client_di.py — new file if test_nodes.py is large):
  - Add named tests (see acceptance criteria).

Acceptance criteria (named tests required — exact names):
- test_di_node_uses_explicit_client: call a node function that uses the client (e.g. ingest_node or
  grill_turn_node equivalent) with an explicit _client=FakeClient(); assert the fake client was called,
  not _get_model_client(). Use the existing set_model_client_factory() approach to put a sentinel
  default in, then pass a different _client, and verify the explicit one wins.
- test_di_node_fallback_to_module_factory: call the same node function WITHOUT _client; assert that
  the module-level factory is used (set via set_model_client_factory with a sentinel).
- test_di_two_workflows_isolated: build two workflows via build_discovery_workflow() with different
  model_factory callables (factory_a, factory_b); invoke the ingest or grill shim from each workflow
  (by running a full turn or by calling the shim directly); assert factory_a's client is used in
  workflow A's turn and factory_b's client in workflow B's turn — no bleed.
- test_build_runner_threads_factory: call build_runner(model_factory=fake_factory); invoke a node
  turn via the runner; assert fake_factory was called to create the client.
- Existing tests that use set_model_client_factory() must remain green (no regression).

DoD:
- make check green.
- No contract change.
- No changes to graph topology, routing logic, ADK edges, or session/persistence layer.
- _install_model_client removed from cli/app.py if no callers remain (keep if still used).
- Gemini 2.5 Pro review PASS (use the review prompt template in GROOMING.md §Phase 8 header;
  address any CHANGES REQUESTED before pushing the branch).
- Report READY FOR REVIEW with criterion→test mapping and a table showing: for each of the 3 original
  _install_model_client call sites, what replaced it.
```

---

### ◐ 8E — Deployer-SA least-privilege curation (Terraform-only)

> Read first: [SECURITY.md](../SECURITY.md) "Required next review" section; `infrastructure/modules/`.

**What:** The `career-engine-deployer` service account was granted broad project-level roles to get the
initial deploy working. Narrow them to only what each Terraform resource actually needs (Cloud Run deploy,
Artifact Registry push, Firestore rules, Secret Manager reads for the runtime SA, etc.).

**This is Terraform-only** (`infrastructure/` files). No application code changes.

Acceptance criteria:
- `make tf-check` green in both envs.
- The deployer SA's bound roles are listed in [SECURITY.md](../SECURITY.md) "Post-8E role inventory" section.
- A `terraform plan` on a fresh environment shows no diff from the stated desired state.

DoD:
- `make tf-check` green.
- [SECURITY.md](../SECURITY.md) updated with the role inventory.
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
                Note: cloudflare_dns_record is a v5 provider API; constraint ">= 5.0, < 6.0" is correct.
                (v4 used cloudflare_record; the spec originally said >= 4.0 which was an error)
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
      version = ">= 5.0, < 6.0"  # v5+ required: cloudflare_dns_record is a v5 API
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
- [SECURITY.md](../SECURITY.md) has a "Post-8E role inventory" section (8E).
- Every PR passed both Gemini 2.5 Pro review (pre-push) and Copilot review (on the PR).

---

## Phase 9 — Replace Streamlit; proper product UI *(◐ Draft — Phase 8 core shipped; backlog captured)*

> **Status: ◐ Draft.** Phase 8 core (8A–8D + 8G) shipped. 8E (deployer-SA) and 8F (HITL TTL
> dashboard) are lower-priority and can run in parallel with early Phase 9 Streamlit-compatible
> improvements. Full frontend rewrite still requires a design session (open questions below).
> Items marked **Streamlit-compatible** can ship as incremental PRs now.

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

> **Resolved (2026-07-07):** the frontend/backend architecture decision is recorded in
> [ARCHITECTURE.md §16](../ARCHITECTURE.md) (Next.js App Router + FastAPI JSON API; auth at the API
> boundary; grill over SSE; Cloud Run deploy) and broken into executable build tickets in **Phase 10**
> below. Questions 1 and 2 are answered there; 3–5 are finalised inside the relevant Phase 10 slice.

1. Next.js + FastAPI vs. a full Next.js fullstack (with API routes)? What does the deployment
   topology look like on Cloud Run?
2. How does the grill loop (streaming, multi-turn, long-running) map to a REST or WebSocket API?
   The current ADK Runner pattern needs an HTTP-friendly wrapper.
3. Free tier quota: per-day or per-month? What's the unit economics ceiling at $0?
4. Streamlit transition: run both in parallel (A/B) or hard cutover?
5. What does the design system look like? (Color, typography, component library.)

---

### Phase 9 product backlog

| ID | Summary | Size | Compat | Priority | Grooming |
|----|---------|------|--------|----------|----------|
| 9J | Grill checkpoint: copy reminding user they can leave and come back | XS | Streamlit | High | ✅ Ready |
| 9I | Tailor: "specific instructions" textarea per application | S | Streamlit | High | ✅ Ready |
| 9B | Portfolio: make "Add experience" CTA prominent at top of entry list | S | Streamlit | High | ✅ Ready |
| 9C | Profile: dedicated editable section for name/email/contact | S | Streamlit | High | ✅ Ready |
| 9K | Portfolio: per-experience progress indicator (stories recorded) | S | Streamlit | Medium | ✅ Ready |
| 9G | Jobs: "Track application" auto-harvests title + company from JD | S | Streamlit | Medium | ✅ Ready |
| 9E | Jobs: sort for-review list by relevance; scrollable container | S | Streamlit | Medium | ✅ Ready |
| 9D | Resume: better template — Inter/system-ui, multi-section layout | M | Streamlit | High | ✅ Ready |
| 9A | Portfolio: delete/edit recorded bullets + STAR stories | M | Streamlit | High | ✅ Ready |
| 9F | Jobs: tighten discovery parameters + smarter preference defaults | M | Streamlit | Medium | ✅ Ready |
| 9H | Resume download: inline chat for résumé-specific edits | L | Frontend | Medium | ◐ Draft (build on Phase 10) |
| 9L | (Stretch) Monthly achievements email reminder | L | Streamlit | Low | ◐ Draft (email provider decision first) |
| 9M | (Stretch) Visual drag-and-drop résumé section editor | XL | Frontend | Low | ◐ Draft (build on Phase 10) |

### Launch order

Run 9J + 9I + 9B in parallel (zero dependencies, tiny/small). Then 9C + 9K + 9G in parallel.
Then 9E + 9D + 9F + 9A — 9A may depend on a `story_id` contract decision; see PAUSE condition.

PR workflow for every ticket: same as Phase 8:
```
new branch → subagent builds → make check green →
Gemini 2.5 Pro review (PASS or CHANGES REQUESTED → fix → re-review) →
push → gh pr create → request Copilot review →
wait with skills/wait-for-pr-review/scripts/wait_for_review.sh --pr <N> →
address comments → squash-merge → update PROGRESS.md + HANDOFF.md
```

---

### ✅ 9J — Grill checkpoint: "you can come back later"

> Read first: `web/grill_ui.py` — the block that renders when `ss.get("grill_checkpoint")` is
> truthy (line ~667) and `_confirm_checkpoint` (line ~469).

**What:** Pure copy change. When the grill pauses at a checkpoint, show a short informational
message that the user can leave and return — their progress is saved. No logic change.

```text
You are WS 9J for CareerEngine. Add a short info message at the grill checkpoint
telling the user they can leave and come back later.

Files to read BEFORE writing any code:
1. web/grill_ui.py — find the block that renders when ss.get("grill_checkpoint") is truthy
   (grep for grill_checkpoint). Read the full render block and _confirm_checkpoint(). Note
   exactly what is rendered above and below the confirm button.

PAUSE CONDITIONS:
- If the checkpoint is rendered in a different file than web/grill_ui.py.
- If there is already any copy about returning later or saving progress.

Scope:
  web/grill_ui.py:
  - In the block guarded by `if ss.get("grill_checkpoint"):`, add this ABOVE the checkpoint
    summary and confirm button:
      st.info(
          "💾 Your progress is automatically saved. Feel free to close this tab and come "
          "back later — your stories will be right where you left them. Visit **Portfolio** "
          "to review what has been recorded so far."
      )
  - No other changes. Do not modify _confirm_checkpoint or any logic path.

  tests/ (one new test):
  - Find how grill_ui is currently tested (grep for test_grill or look at test_nodes.py /
    tests/test_integration.py for the fake-st pattern used for UI tests).
  - test_checkpoint_leave_copy_shown: when grill_checkpoint is set to a non-empty string in
    session_state, the rendered output includes the text "come back" (or the exact copy above).
    Use the same fake-st injection pattern as existing grill UI tests.

Acceptance criteria (named tests):
- test_checkpoint_leave_copy_shown: info message is present when checkpoint is active.
- Existing grill_ui / checkpoint tests remain green.

DoD:
- make check green. No contract change. No logic change. Only copy + one test.
- Gemini 2.5 Pro review PASS (use the review template in GROOMING.md §Phase 8 header).
- Report READY FOR REVIEW with criterion→test mapping.
```

---

### ✅ 9I — Tailor: per-application specific instructions

> Read first: `web/streamlit_app.py` (tailor path, JD textarea around line 678),
> `workflows/nodes.py::tailor_node` (line ~1007), `workflows/prompts.py::TAILOR_SYSTEM_PROMPT`,
> `workflows/discovery_graph.py::build_discovery_workflow` (the `_ci_tailor_shim` closure from 8D).

**What:** Add an optional "Specific instructions" textarea below the JD input in the Tailor
view. Thread the value into `tailor_node` via the same keyword-only DI closure pattern as 8D —
no contract change, no `CareerEngineState` fields added.

```text
You are WS 9I for CareerEngine. Add a "specific instructions" textarea to the Tailor
view and thread it into tailor_node via keyword-only DI (same pattern as 8D _client).

Files to read BEFORE writing any code (in this order):
1. web/streamlit_app.py — find the tailor path. Locate the JD textarea (key="tailor_jd_text_input",
   line ~678) and all places build_runner() is called for the tailor flow. Note how tailor_jd_text
   is read from session_state before the runner call.
2. workflows/nodes.py::tailor_node (line ~1007) — read full signature and body. Note how
   TAILOR_SYSTEM_PROMPT is used in the client.generate() call.
3. workflows/prompts.py — read TAILOR_SYSTEM_PROMPT in full.
4. workflows/discovery_graph.py — find build_discovery_workflow() and _ci_tailor_shim. Read
   how the 8D _client closure capture works — you will follow the same pattern.

PAUSE CONDITIONS:
- If tailor_node is called via a different path than build_runner → build_discovery_workflow
  → _ci_tailor_shim. Surface the discrepancy.
- If threading _instructions into the closure would require adding a field to CareerEngineState.
  STOP: do NOT add state fields. Report and ask.
- If build_runner is called for the tailor path in more files than web/streamlit_app.py.

Design (follow exactly — do not deviate without asking):
  1. workflows/nodes.py::tailor_node:
     - Add `*, _instructions: str = ""` as a keyword-only parameter (after existing _client).
     - Build effective_system:
         extra = (
             f"\n\nAdditional instructions from the user (apply to this résumé only):\n"
             f"{_instructions.strip()}"
             if _instructions.strip() else ""
         )
         effective_system = TAILOR_SYSTEM_PROMPT + extra
     - Pass effective_system (not TAILOR_SYSTEM_PROMPT) to client.generate().

  2. workflows/discovery_graph.py::build_discovery_workflow():
     - Add `tailor_instructions: str = ""` parameter.
     - Update _ci_tailor_shim closure to pass _instructions=tailor_instructions to tailor_node.

  3. workflows/discovery_graph.py::build_runner():
     - Add `tailor_instructions: str = ""` parameter.
     - Thread to build_discovery_workflow(tailor_instructions=tailor_instructions).

  4. web/streamlit_app.py (tailor path):
     - Add below the JD textarea:
         st.text_area(
             "Specific instructions (optional)",
             key="tailor_instructions_input",
             max_chars=500,
             placeholder=(
                 "e.g. Emphasise cloud infrastructure experience. "
                 "Omit side projects. Use a formal tone."
             ),
             help="These instructions apply to this résumé only and are not saved.",
         )
     - Read instructions = ss.get("tailor_instructions_input", "").
     - Pass tailor_instructions=instructions to build_runner().

Acceptance criteria (named tests — exact names):
- test_tailor_node_appends_instructions: call tailor_node(state, _instructions="use formal tone");
  capture the system arg passed to client.generate() and assert it contains "use formal tone".
- test_tailor_node_empty_instructions_unchanged: call tailor_node(state, _instructions="");
  assert client.generate() receives exactly TAILOR_SYSTEM_PROMPT (no trailing newline/text).
- test_build_runner_threads_tailor_instructions: build_runner(tailor_instructions="be concise");
  run a tailor turn; assert the captured system prompt contains "be concise".
- Existing tailor tests remain green.

DoD:
- make check green. No contract change (no CareerEngineState fields added).
- Gemini 2.5 Pro review PASS.
- Report READY FOR REVIEW with criterion→test mapping.
```

---

### ✅ 9B — Portfolio: prominent "Add experience" CTA

> Read first: `web/portfolio.py` (full file), `web/streamlit_app.py` (portfolio route ~line 145),
> `web/portfolio_store.py::add_manual_entry` (signature only).

**What:** The "Add experience" form from 4D is currently placed below the entry list. Move it to
the top so it is the first thing a user sees on an empty portfolio. No persistence changes.

```text
You are WS 9B for CareerEngine. Move the "Add experience" form to the top of the Portfolio
view (before the experience list) so it is immediately discoverable.

Files to read BEFORE writing any code:
1. web/portfolio.py — read in full. Find exactly where the "Add experience" form/expander
   currently appears in the renderer. Note the EntryCard dataclass and build_portfolio_view.
2. web/streamlit_app.py — find the portfolio route (view_name == "portfolio"). Confirm how
   portfolio.py's renderer is invoked.

PAUSE CONDITIONS:
- If there is no "Add experience" form in web/portfolio.py (4D may have placed it elsewhere).
  Surface the location and ask before moving anything.
- If the form is already at the top of the rendered output.

Scope:
  web/portfolio.py:
  - In the renderer, move the "Add experience" expander/form so it appears BEFORE the first
    entry card is rendered, not after. If it is inside an expander, keep the expander closed
    (expanded=False) by default.
  - Add a visible label above the expander (outside it):
      st.caption("Add a role, project, or experience to your portfolio.")
    so the user sees the affordance without having to expand it.
  - Do not change the form fields, field validation, or the add_manual_entry call.
  - Do not change the entry list rendering.

  tests/:
  - test_add_experience_cta_precedes_entry_list: given a PortfolioView with at least one
    entry, assert the "Add" label string appears before the first entry's company/title in
    the sequence of render calls captured by the fake-st helper.

Acceptance criteria (named tests):
- test_add_experience_cta_precedes_entry_list: CTA rendered before entry list.
- Existing portfolio render tests remain green.

DoD:
- make check green. No contract change. No persistence change.
- Gemini 2.5 Pro review PASS.
- Report READY FOR REVIEW with criterion→test mapping.
```

---

### ✅ 9C — Editable profile section

> Read first: `schema.py::UserProfile` (line ~407: name, email, phone, location, links fields),
> `web/profile_store.py` (load_profile, save_profile), `web/portfolio.py` (renderer structure),
> `web/streamlit_app.py` (portfolio route ~line 145, and how load_profile is called ~line 297).

**What:** Add a "Profile" section to the Portfolio view where users can see and edit their saved
contact info (name, email, phone, location, links). `UserProfile` already exists; this is a UI
surface only — no schema changes.

```text
You are WS 9C for CareerEngine. Add an editable Profile section to the Portfolio view
so users can review and update their contact details without running a Tailor first.

Files to read BEFORE writing any code (in this order):
1. schema.py::UserProfile (line ~407) — read all fields: name, email, phone, location,
   links: list[str]. Note it is NOT frozen (mutable) and has a contract_version field.
2. web/profile_store.py — read load_profile and save_profile in full. Note what store +
   user_id they need.
3. web/portfolio.py — read in full. Understand the renderer structure and where the new
   section should be inserted (top of the page, before the "Add experience" CTA or after).
4. web/streamlit_app.py — find the portfolio route (~line 145). See how FirestoreWorkspaceStore
   and user_id are available there. Note that load_profile is already called elsewhere (~line 297).

PAUSE CONDITIONS:
- If UserProfile fields differ from: name, email, phone, location, links. Surface any diff.
- If load_profile / save_profile signatures differ from what you expect after reading.
- If the portfolio route does not have FirestoreWorkspaceStore available without additional
  imports. Surface and ask.

Scope:
  web/portfolio.py:
  - Add dataclass ProfileView(name: str, email: str, phone: str, location: str, links: list[str]).
  - Add pure function build_profile_view(profile: UserProfile) -> ProfileView.
  - Add render_profile_section(view: ProfileView, *, on_save: Callable[[UserProfile], None],
    st: Any) -> None:
      - st.subheader("Profile")
      - Two-column layout: name + email in col1/col2, phone + location in col1/col2.
      - Links: iterate view.links; for each, show the URL text + an "× Remove" button that
        pops the link and calls on_save immediately. Also show a text_input + "Add link" button
        to append a new link.
      - A "Save changes" button that calls on_save(UserProfile(name=..., email=..., ...)).
      - Keep the section collapsed in an st.expander("Profile", expanded=False) so it does
        not dominate the page. (Or expanded=True if the view model has no entries — ask the
        builder to decide.)
  - Place the Profile expander at the VERY TOP of the portfolio renderer (before the Add
    experience CTA and the entry list).

  web/streamlit_app.py (portfolio route):
  - Load profile: profile = load_profile(FirestoreWorkspaceStore(), user_id=user_id)
    (or reuse if already loaded — check).
  - Call render_profile_section(build_profile_view(profile), on_save=..., st=st) with
    on_save=lambda p: save_profile(FirestoreWorkspaceStore(), user_id=user_id, profile=p).

  tests/:
  - test_build_profile_view_maps_fields: build_profile_view(UserProfile(name="Alice",
    email="a@b.com", phone="123", location="Remote", links=["https://x.com"])) returns a
    ProfileView with all matching fields.
  - test_render_profile_section_calls_on_save: render_profile_section with fake-st; simulate
    clicking "Save changes"; assert on_save is called with a UserProfile whose name matches the
    input value.
  - test_render_profile_section_empty_profile: ProfileView with all empty fields renders
    without error; no crash on empty links list.

Acceptance criteria (named tests):
- test_build_profile_view_maps_fields
- test_render_profile_section_calls_on_save
- test_render_profile_section_empty_profile
- Existing profile_store + portfolio tests remain green.

DoD:
- make check green. No contract change (UserProfile is v2.6.0; no new fields).
- Gemini 2.5 Pro review PASS.
- Report READY FOR REVIEW with criterion→test mapping.
```

---

### ✅ 9K — Portfolio: per-experience progress indicator

> Read first: `web/portfolio.py` (EntryCard dataclass and build_portfolio_view),
> `schema.py::Entry` (entry_id, status, bullets), `schema.py::StarStory` (entry_id field).

**What:** Show a progress bar per entry in the Portfolio view indicating how many STAR stories
have been recorded, against a soft target of 3. Read-only; no new persistence.

```text
You are WS 9K for CareerEngine. Add a per-entry story progress indicator to the
Portfolio view.

Files to read BEFORE writing any code:
1. web/portfolio.py — read EntryCard and build_portfolio_view in full. Find how
   stories_by_entry is built and how story count per entry is derivable.
2. schema.py::Entry — read entry_id, status, type fields.
3. schema.py::StarStory — read entry_id (confirms the link to Entry).

PAUSE CONDITIONS:
- If EntryCard already has a story_count or progress field.
- If stories_by_entry is not a dict keyed by entry_id in build_portfolio_view.

Design:
  "Complete" for v1 = 3 STAR stories. progress_fraction = min(story_count / 3, 1.0).
  Display: after each entry's title/org/dates header line, render:
    if story_count == 0:
        st.caption("No stories yet — click 'Grill me about this' to start.")
    else:
        st.progress(progress_fraction,
                    text=f"{story_count} stor{'y' if story_count == 1 else 'ies'} recorded"
                         + (" ✓" if story_count >= 3 else ""))

Scope:
  web/portfolio.py:
  - Add story_count: int = 0 and stories_target: int = 3 to EntryCard.
  - In build_portfolio_view, populate:
      story_count=len(stories_by_entry.get(str(entry.entry_id), []))
    when building each EntryCard.
  - In the renderer, add the progress display after each entry header as described above.

  tests/:
  - test_entry_card_story_count_populated: build_portfolio_view with a fixture state where
    entry A has 2 linked StarStory objects and entry B has 0; assert card for A has
    story_count=2, card for B has story_count=0.
  - test_progress_renders_zero_state: EntryCard(story_count=0) → renderer outputs "No stories
    yet" copy (use fake st).
  - test_progress_renders_partial: EntryCard(story_count=2, stories_target=3) → renderer
    calls st.progress with a fraction between 0 and 1 (exclusive).
  - test_progress_renders_complete: EntryCard(story_count=3, stories_target=3) → st.progress
    called with fraction=1.0 and text contains "✓".

Acceptance criteria (named tests):
- test_entry_card_story_count_populated
- test_progress_renders_zero_state
- test_progress_renders_partial
- test_progress_renders_complete
- Existing portfolio tests remain green.

DoD:
- make check green. No contract change.
- Gemini 2.5 Pro review PASS.
- Report READY FOR REVIEW with criterion→test mapping.
```

---

### ✅ 9G — "Track application": harvest title + company from JD

> Read first: `web/streamlit_app.py::_render_save_application` (line ~776, read in full),
> `integration/model_client.py` (ModelClient.generate signature), `schema.py::Application`
> (company, job_title fields), `models/registry.py` (BULK_CHEAP capability).

**What:** Add a "✨ Extract from JD" button to the "Track application" form. On click, a single
cheap Flash call parses the pasted JD and pre-fills the company + job title inputs. Fields remain
fully editable. No cost gate required (single Flash call, < $0.001).

```text
You are WS 9G for CareerEngine. Add JD metadata extraction to the "Track application"
form so users don't have to type job title and company manually.

Files to read BEFORE writing any code (in this order):
1. web/streamlit_app.py::_render_save_application (line ~776) — read in full. Note the
   form keys: "save_app_company", "save_app_title". Find where the JD text comes from at
   this call site (look for ss.get("tailor_jd_text") or similar nearby).
2. integration/model_client.py — read ModelClient.generate(model_id, system, user) signature.
3. models/registry.py — find how to resolve a model_id for BULK_CHEAP capability.
4. web/streamlit_app.py — find how model client is resolved for the current user at the
   tailor/download page (look for _resolve_byok_key or similar client-building code). You
   need the same pattern to get a client at the _render_save_application call site.

PAUSE CONDITIONS — stop and report before writing any code if:
- The JD text is NOT available in session_state at the _render_save_application call site
  (i.e. ss.get("tailor_jd_text") is empty or absent). Surface this: "JD text is not in
  session_state at the track-application form. Options: (a) pass jd_text as a parameter to
  _render_save_application; (b) read from a different key. Please clarify."
- Model client resolution at this call site is not straightforward (requires runner setup).
  Surface the constraint and ask for the approach.
- Application.company or .job_title fields do not exist in schema.py.

Design:
  New pure function (in a new web/jd_utils.py):
    def extract_jd_metadata(jd_text: str, client: Any, model_id: str) -> tuple[str, str]:
        """Returns (title, company). Returns ("", "") on any failure."""
        system = (
            'Extract the job title and hiring company from the text. '
            'Return ONLY valid JSON: {"title": "...", "company": "..."}. '
            'Use empty string for unknown fields.'
        )
        try:
            raw = client.generate(model_id, system, jd_text[:3000])
            data = json.loads(raw)
            return str(data.get("title", "")), str(data.get("company", ""))
        except Exception:
            return "", ""

  In _render_save_application:
  - Add a "✨ Extract from job description" button ABOVE the company/title inputs.
  - On click: resolve client + model_id (BULK_CHEAP); call extract_jd_metadata;
    if result is non-empty, write to ss["save_app_company"] / ss["save_app_title"] and
    call st.rerun() to refresh the form with pre-filled values.
  - If JD text is empty when button is clicked: st.warning("No job description found —
    paste one in the Tailor tab first.") and do not call the LLM.

  tests/ (for web/jd_utils.py):
  - test_extract_jd_metadata_returns_title_company: fake client returns
    '{"title": "SWE", "company": "Acme"}'; assert returns ("SWE", "Acme").
  - test_extract_jd_metadata_handles_malformed_json: fake client returns "oops";
    assert returns ("", "") without raising.
  - test_extract_jd_metadata_truncates_long_jd: jd_text of 4000 chars; assert
    client.generate() is called with user text of exactly 3000 chars.

Acceptance criteria (named tests):
- test_extract_jd_metadata_returns_title_company
- test_extract_jd_metadata_handles_malformed_json
- test_extract_jd_metadata_truncates_long_jd
- Existing _render_save_application / application tests remain green.

DoD:
- make check green. No contract change.
- Gemini 2.5 Pro review PASS.
- Report READY FOR REVIEW with criterion→test mapping + note on JD text source resolution.
```

---

### ✅ 9E — Jobs: sort for-review list by relevance; scrollable container

> Read first: `schema.py::JobOpportunity` (all fields, especially `match_status`, `ai_rationale`),
> `schema.py::MatchStatus` (enum values), `web/jobs.py` (JobCard, build_jobs_view, render_jobs).

**What:** Sort the "For review" (soft-reject) and accepted job lists by relevance (best first)
and wrap each in a fixed-height scrollable container. Includes a mandatory PAUSE to surface the
lack of a numeric score field — the agent must ask before assuming a solution.

```text
You are WS 9E for CareerEngine. Sort the jobs lists by relevance and add scrollable
containers to prevent long lists from pushing the page down.

Files to read BEFORE writing any code (in this order):
1. schema.py::JobOpportunity — read ALL fields. Note match_status (MatchStatus enum) and
   ai_rationale (str). Check carefully whether there is ANY numeric score or confidence field.
2. schema.py::MatchStatus — list all enum values.
3. web/jobs.py — read JobCard dataclass (all fields), build_jobs_view (how for_review and
   accepted are built), and render_jobs (how the lists are rendered with st.container etc.).

PAUSE CONDITIONS (mandatory — do not proceed past this point without reporting):
- After reading JobOpportunity: if there is NO numeric score field (only MatchStatus enum),
  STOP and report exactly:
    "JobOpportunity has no numeric relevance score — only MatchStatus enum values.
     The for_review list is all SOFT_REJECT so MatchStatus gives no ordering signal.
     Options:
     (a) Sort by len(ai_rationale) descending as a cheap proxy for consideration depth.
         No contract change. May not reflect actual job quality.
     (b) Add relevance_score: float | None = None to JobOpportunity — additive, backward-
         compatible, minor contract bump to v2.9.0. The PrimaryAgent would set it.
     (c) Keep insertion order (no sort).
     Please choose before I proceed."
  Do NOT implement any option without explicit confirmation.
- If there is already a scroll container or sort in render_jobs.

Assuming user confirms option (a) — sort by rationale length (no contract change):
  Scope:
    web/jobs.py::build_jobs_view:
    - Before building JobCards from soft_reject and accepted lists, sort each by
      len(job.ai_rationale or "") descending:
          sorted_review = sorted(result.soft_rejected, key=lambda j: len(j.ai_rationale or ""), reverse=True)
          sorted_accepted = sorted(result.accepted_jobs, key=lambda j: len(j.ai_rationale or ""), reverse=True)
      (or the equivalent field names — confirm after reading the source)

    web/jobs.py::render_jobs (or wherever the lists are rendered):
    - Wrap the for_review card loop:
          with st.container(height=420):
              for card in view.for_review:
                  _render_job_card(card, ...)
    - Wrap the accepted card loop similarly if len(view.accepted) > 3.

  tests/:
  - test_build_jobs_view_sorts_for_review_by_rationale: two soft_reject jobs where job_A
    ai_rationale is longer than job_B; assert job_A card appears first in view.for_review.
  - test_build_jobs_view_sorts_accepted: same check for accepted list.

Acceptance criteria (named tests):
- test_build_jobs_view_sorts_for_review_by_rationale
- test_build_jobs_view_sorts_accepted
- Existing jobs tests remain green.

DoD:
- make check green.
- Contract change only if user confirmed option (b) — in that case bump to v2.9.0 additively
  and tag; otherwise no contract change.
- Gemini 2.5 Pro review PASS. Reviewer must confirm the chosen sort option is documented.
- Report READY FOR REVIEW with chosen option + criterion→test mapping.
```

---

### ✅ 9D — Better résumé template

> Read first: `templates/classic_resume.html` (read in FULL — all 237 lines),
> `schema.py::StructuredResume` (all fields), `web/resume_render.py` (full file),
> `tests/test_resume_render.py`.

**What:** Replace the thin `classic_resume.html` template with a professional multi-section
layout: Inter/system-ui font, proper experience section with bullets, two-column skills grid,
clean ATS-friendly margins. Jinja2 variable names unchanged; Python untouched.

```text
You are WS 9D for CareerEngine. Rewrite templates/classic_resume.html to produce a
professional, multi-section résumé with Inter/system-ui font and proper layout.

Files to read BEFORE writing any code (in this order):
1. templates/classic_resume.html — read THE ENTIRE FILE. List every Jinja2 variable
   ({{ resume.xxx }}, {% for %}, {% if %}) you find. You must not rename or remove any.
2. schema.py::StructuredResume — read all fields. Confirm each maps to a template variable.
3. web/resume_render.py — read in full. Note: (a) how the template is loaded (file path,
   base_url for WeasyPrint), (b) whether WeasyPrint loads external resources (fonts, images)
   and whether outbound HTTP is expected. Surface anything that could block a web font.
4. tests/test_resume_render.py — understand the existing test surface.

PAUSE CONDITIONS:
- If resume_render.py passes a restrictive base_url that would block @font-face or external
  CSS imports. Surface this: "WeasyPrint base_url is set to X — external font URLs may be
  blocked. Should I use system-ui only, or embed a font subset?" Do not guess; ask.
- If StructuredResume has fields used in the template that are not documented in schema.py.
  List them and ask how to handle.
- If the template uses Jinja2 `extends` or `macro` features that require other template files.

Font strategy (follow strictly):
  Use: font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif
  Do NOT add an @import for Google Fonts (network dependency at render time).
  Do NOT embed base64 font data (file size concern). system-ui provides a clean sans-serif
  fallback on all platforms.

Layout spec (implement exactly):
  - Page: A4 (210mm × 297mm), margins: 15mm top/bottom, 18mm left/right.
  - Name: 22pt, font-weight 600, no text-transform. Below: one-line contact string
    (email · phone · location, then links separated by ·). 9pt, color #555.
  - Section rule: each section heading at 9.5pt, font-weight 600, letter-spacing 1.5px,
    text-transform uppercase, followed by a 0.5px solid #ccc border-bottom, 4pt margin-bottom.
  - Sections in order: Summary → Experience → Skills → Education.
  - Summary: 10pt, color #333, max 5 lines, no label needed if the section heading "Summary"
    is present.
  - Experience: each role — company name bold + title normal on one line, dates right-aligned
    (use flex or table layout); then bullets as <ul> with 9.5pt, 14px line-height, 4px left
    padding, 3px margin-bottom per item; 8pt gap between roles.
  - Skills: render as a flex-wrap list of pill spans (background #f0f0f0, border-radius 3px,
    padding 2px 6px, 9pt, 4px gap).
  - Education: institution bold + degree normal + dates right-aligned; no bullets.
  Keep all existing Jinja2 variable references UNCHANGED. Only restructure HTML + CSS.

tests/ (new tests, do not remove existing ones):
- test_resume_template_has_experience_section: render with a fixture StructuredResume that
  has one experience entry with one bullet; assert output HTML contains the employer name and
  the bullet text inside a <li> element.
- test_resume_template_has_skills_section: rendered HTML contains at least one skill keyword.
- test_resume_template_has_education_section: rendered HTML contains the degree field value.
- test_resume_renders_to_pdf_without_error: call render_resume_pdf (or equivalent) with a
  fixture StructuredResume; assert returns non-empty bytes. (This test exercises WeasyPrint;
  mark @pytest.mark.slow if the suite defines that marker.)

Acceptance criteria (named tests):
- test_resume_template_has_experience_section
- test_resume_template_has_skills_section
- test_resume_template_has_education_section
- test_resume_renders_to_pdf_without_error
- Existing resume_render tests remain green.

DoD:
- make check green. No Python code changes (template only + tests).
- Gemini 2.5 Pro review PASS — reviewer confirms valid HTML, clean CSS, no Jinja2 regressions.
- Report READY FOR REVIEW with: (a) list of preserved Jinja2 variables; (b) font strategy used.
```

---

### ✅ 9A — Portfolio: delete and edit recorded details

> Read first: `web/portfolio_store.py` (full file — especially `_patch_session`),
> `schema.py::StarStory` (all fields; check for `story_id`), `schema.py::Entry` (bullets field),
> `web/portfolio.py` (EntryCard, renderer), `tests/test_portfolio_store.py`.

**What:** Add `delete_star_story` and `update_entry_bullet` to the portfolio-store seam, and
surface delete + edit-in-place controls in the Portfolio renderer. Includes a mandatory PAUSE if
`StarStory` has no `story_id` field — the agent must ask before adding one (contract bump).

> **PAUSE resolved (2026-07-07):** `StarStory` already has `story_id: UUID = Field(default_factory=uuid4)`
> (`schema.py` L178) and `entry_id: str` (L179). No contract bump needed — proceed with the
> `story_id`-based delete path. Do NOT re-pause on this.

```text
You are WS 9A for CareerEngine. Let users delete STAR stories and edit entry bullets
in the Portfolio view, turning the read-only portfolio into a correctable record.

Files to read BEFORE writing any code (in this order):
1. schema.py::StarStory — read ALL fields. Check whether a story_id field exists.
2. schema.py::Entry — read entry_id and bullets: list[str].
3. schema.py::CareerEngineState — confirm star_stories: list[StarStory] and work_timeline.
4. web/portfolio_store.py — read the FULL file. Understand _patch_session (the async
   read-modify-write seam), add_manual_entry, set_entry_highlight. These are your patterns.
5. web/portfolio.py — read EntryCard and the full renderer. Find where stories and bullets
   are currently displayed (they are likely inside the entry expansion or card body).
6. tests/test_portfolio_store.py — understand the test pattern (fake session service).

PAUSE CONDITIONS (mandatory — stop before writing any code):
- If StarStory does NOT have a story_id field: STOP and report:
    "StarStory has no story_id. Options:
     (a) Add story_id: str = Field(default_factory=lambda: str(uuid4())) — additive, minor
         contract bump to v2.9.0. Existing stories without it get a fresh id on next save.
     (b) Identify stories by (entry_id, positional index) — fragile if order changes.
     Please decide before I proceed."
  Do NOT add story_id without explicit confirmation.
- If _patch_session signature differs from add_manual_entry's usage pattern.
- If bullets on Entry is not a direct list[str].

Assuming story_id exists on StarStory (or is added per decision):

  Scope:
    web/portfolio_store.py:
    - Add async def _adelete_star_story(session_service, app_name, user_id, story_id: str):
        load state via session_service; filter out the StarStory whose story_id matches;
        save back. Idempotent: no-op if story_id not found.
    - Add sync wrapper: delete_star_story(story_id: str, *, session_id: str | None = None,
        app_name: str, user_id: str) — follow add_manual_entry's sync-wrapper pattern exactly.
    - Add async def _aupdate_entry_bullet(session_service, app_name, user_id, entry_id: str,
        bullet_index: int, new_text: str):
        load state; find Entry where str(entry.entry_id) == entry_id; update
        entry.bullets[bullet_index] = new_text.strip(); save back.
        Guard: if entry not found or bullet_index out of range, log a warning and return.
    - Add sync wrapper: update_entry_bullet(entry_id, bullet_index, new_text, ...).
    - Export new functions in __all__.

    web/portfolio.py:
    - Story delete: next to each StarStory display, add a small "🗑 Delete" button.
      On click (on_click callback pattern, not st.form), call delete_star_story(...).
      After deletion, call st.rerun() to refresh.
    - Bullet edit: next to each bullet text, add a "✎ Edit" button. On click, replace the
      static text with an st.text_input pre-filled with the current bullet text + a "Save"
      button. On save, call update_entry_bullet(...) then st.rerun().
    - Use st.session_state keys to track which bullet is in edit mode (e.g.
      f"editing_bullet_{entry_id}_{idx}"). Only one bullet editable at a time is acceptable.

    tests/:
    - test_delete_star_story_removes_from_state: fake session with 2 stories; call
      delete_star_story for story A's story_id; reload state and assert only story B remains.
    - test_delete_star_story_idempotent: call delete_star_story with a non-existent story_id;
      assert state is unchanged and no exception is raised.
    - test_update_entry_bullet_mutates_correctly: fake session with entry having bullets
      ["old bullet"]; call update_entry_bullet(entry_id, 0, "new bullet"); reload and assert
      bullet is "new bullet".
    - test_update_entry_bullet_out_of_range: bullet_index beyond list length; assert warning
      is logged and state is unchanged (no IndexError raised).
    - test_portfolio_renders_delete_story_button: EntryCard with a story; renderer emits a
      button whose label contains "Delete" or "🗑" (use fake st).

Acceptance criteria (named tests):
- test_delete_star_story_removes_from_state
- test_delete_star_story_idempotent
- test_update_entry_bullet_mutates_correctly
- test_update_entry_bullet_out_of_range
- test_portfolio_renders_delete_story_button
- Existing portfolio_store + portfolio tests remain green.

DoD:
- make check green.
- Contract change only if story_id addition confirmed — bump to v2.9.0 additively and tag.
- Gemini 2.5 Pro review PASS.
- Report READY FOR REVIEW with: (a) story_id pause-condition resolution; (b) criterion→test map.
```

---

### ✅ 9F — Tighten discovery parameters + smarter preference defaults

> Read first: `discovery/preferences.py` (default_session_preferences in full),
> `schema.py::SessionPreferences` (all fields), `web/jobs.py` (render_jobs preferences form),
> `web/preferences_store.py` (load_discovery_preferences), `web/streamlit_app.py` (jobs route).

**What:** Three layered improvements: (a) better UX copy in the preferences form; (b) smarter
defaults derived from the user's own portfolio when no preferences are saved yet; (c) expose
`max_results` as a visible control. The agent must PAUSE before touching `discovery/scout.py`.

```text
You are WS 9F for CareerEngine. Reduce irrelevant job results by improving the
preferences UX and initialising first-time defaults from the user's portfolio.

Files to read BEFORE writing any code (in this order):
1. discovery/preferences.py — read default_session_preferences() in full. Note the current
   target_roles list (Fractional Technology Leadership, etc.) — these are the operator's own
   criteria, not generic defaults.
2. schema.py::SessionPreferences — read ALL fields and descriptions.
3. web/jobs.py — find render_jobs. Read the preferences form (target_roles, nice_to_haves,
   dealbreakers inputs). Note current placeholder text (if any) and how preferences are
   loaded/saved.
4. web/preferences_store.py — read load_discovery_preferences. Note what it returns for a
   new user (default_session_preferences()).
5. web/streamlit_app.py — find the jobs route (~line 148). Check what objects are already
   loaded there (workspace, session state, user_id). Note whether CareerEngineState or
   work_timeline is available without an extra backend call.
6. web/session_loader.py — read try_load_latest_discovery_state signature; understand the
   cost of calling it at the jobs render site (it hits Firestore).

PAUSE CONDITIONS:
- If touching discovery/scout.py or discovery/primary.py is needed for any of (a)-(c).
  STOP: do NOT modify those files without explicit confirmation. Report the constraint.
- If loading CareerEngineState at the jobs render site would require a new Firestore call
  that is not already happening. Surface the cost and ask: "Loading state for preference
  derivation requires an extra Firestore read at the jobs page. Acceptable?" Wait for answer.
- If SessionPreferences fields differ from: target_roles, nice_to_haves, dealbreakers.

Scope — implement in this exact order; stop and report after each if something is unexpected:

  (a) UX copy improvements in render_jobs (web/jobs.py) — NO logic change:
  - Add help= text to the target_roles input:
      "Be specific: 'Senior Product Manager, B2B SaaS' beats 'Product Manager'. List 2–4 roles."
  - Add help= to nice_to_haves: "Technologies, industries, or company types you prefer."
  - Add help= to dealbreakers: "Hard requirements only — things you'd truly decline an offer for."
  - Add placeholder= to each so an empty field shows the guidance immediately.

  (b) Derive initial target_roles from portfolio on first use:
  - In web/preferences_store.py, add a helper:
      def derive_initial_roles(state: CareerEngineState) -> list[str]:
          """Return top-3 most recent Entry titles as initial target_roles suggestions."""
          sorted_entries = sorted(state.work_timeline,
                                  key=lambda e: (e.end_date or "9999"), reverse=True)
          return [e.title for e in sorted_entries[:3] if e.title]
  - In the jobs route (web/streamlit_app.py), if load_discovery_preferences returns the
    operator default (i.e. user has never saved preferences — check by comparing to
    default_session_preferences().target_roles), AND CareerEngineState is loadable:
      * Load state via try_load_latest_discovery_state (ONLY if confirmed acceptable above).
      * Call derive_initial_roles(state) and use as the pre-filled value for the target_roles
        input (NOT saved until user clicks Save — just the widget default value).
    If state is unavailable, fall back to the operator default — never crash.

  (c) NO scout.py changes in this ticket. Document in the PR that narrowing the scout query
  is a follow-up (9F-b) requiring a separate design decision.

  tests/:
  - test_jobs_view_help_text_on_target_roles: render_jobs with fake-st; assert the
    target_roles input is rendered with a non-empty help= kwarg.
  - test_derive_initial_roles_top_3: given state with 5 entries (oldest first), assert
    derive_initial_roles returns the 3 most recent titles.
  - test_derive_initial_roles_empty_state: state with no work_timeline entries; returns [].
  - test_jobs_view_fallback_if_no_state: if try_load_latest_discovery_state returns None,
    the jobs route renders without error using operator defaults.

Acceptance criteria (named tests):
- test_jobs_view_help_text_on_target_roles
- test_derive_initial_roles_top_3
- test_derive_initial_roles_empty_state
- test_jobs_view_fallback_if_no_state
- Existing preferences_store + jobs tests remain green.

DoD:
- make check green. No contract change (SessionPreferences not modified).
- discovery/scout.py and discovery/primary.py NOT modified.
- Gemini 2.5 Pro review PASS.
- Report READY FOR REVIEW with: (a)/(b)/(c) each marked done/skipped + criterion→test mapping.
```

---

### ◐ 9H — Resume download: inline chat for résumé-specific edits *(build on Phase 10)*

Not groomed to build spec. The frontend architecture decision is now recorded
([ARCHITECTURE.md §16](../ARCHITECTURE.md)): this ships on the Next.js + FastAPI stack, on top of
Phase 10 slices 10.4/10.6 (streaming grill/tailor). In Streamlit an in-memory résumé edit chat is
technically feasible but the UX is poor (every message requires a rerun), so this is deferred to
the post-migration frontend rather than built on Streamlit.

---

### ◐ 9L — (Stretch) Monthly achievements reminder *(email provider decision first)*

Not groomed to build spec. Depends on: email provider choice (SendGrid, Resend, or GCP Email);
opt-in / GDPR notice mechanism; and whether the in-app nudge alone (no email) is v1 scope.
The backend sweep mechanism (Cloud Scheduler → Cloud Run Job → pending_action) already exists
from 8C. Groom when the email provider is decided.

---

### ◐ 9M — (Stretch) Visual résumé section editor *(build on Phase 10)*

Not groomed to build spec. Requires React DnD or equivalent. No Streamlit equivalent is
practical. The frontend decision is recorded ([ARCHITECTURE.md §16](../ARCHITECTURE.md)); groom this
once the Phase 10 Next.js frontend (10.5/10.6) is in place.

---

## Phase 9 — live-testing bug fixes (found 2026-07-07)

> These are regressions/defects found while demoing the deployed dev app. They point at the
> Shared preamble + Definition of Done in [AGENT_EXECUTION_PROMPT.md](../AGENT_EXECUTION_PROMPT.md).
> Builders run on Sonnet; Opus reviews + merges. `make check` green per merge.

| ID | Summary | Size | Compat | Priority | Grooming |
|----|---------|------|--------|----------|----------|
| BUG-1 | Workspace saves fail: "Event loop is closed" (profile + track-application) | S | Streamlit | **Critical** | ✅ Ready |
| BUG-2 | Grill "Currently grilling" banner missing on first question after jump/resume | XS | Streamlit | Medium | ✅ Ready |

### ✅ BUG-1 — Workspace saves fail with "Event loop is closed"

> Read first (in this order): `web/async_runner.py` (FULL — read the module docstring, it
> describes this exact bug and the fix), `database/workspace_store.py` (FULL —
> `FirestoreWorkspaceStore`, note `asyncio.run` in `load`/`save`/`list_user_ids` and the client
> built in `__init__`), `config.py::get_firestore_async_client` (note: NOT cached),
> `web/profile_store.py` (`save_profile` = load-then-save), `web/application_store.py`
> (`save_tailored_application` = load-then-save), `tests/test_workspace_store*.py` /
> `tests/test_profile_store.py` / `tests/test_application_store.py` (test doubles + patterns).

**Symptom (two user-visible bugs, one root cause):**
- Saving Profile (name/email/phone/location/links) → *"Couldn't save your profile — please try again."*
- Save-as-tracked-application → *"Couldn't save the application just now: Event loop is closed"*.

**Root cause:** `FirestoreWorkspaceStore` bridges its async Firestore client to the sync
`WorkspaceStore` protocol with `asyncio.run()` **per call**, and constructs the `AsyncClient`
once in `__init__`. `save_profile` / `save_tailored_application` each call `store.load()` **then**
`store.save()` on the SAME store instance → two `asyncio.run()` calls that each create and then
**close** a fresh event loop, while REUSING the one `AsyncClient` whose gRPC channel bound to the
first (now closed) loop. The second call raises `RuntimeError: Event loop is closed`. Pure single
loads (dashboard) work because they are one `asyncio.run` on a fresh store. This is the exact
failure mode `web/async_runner.py` was written to prevent (the grill uses `run_async` and is fine).

```text
You are the BUG-1 fixer for CareerEngine. Fix "Event loop is closed" on workspace saves
(Profile save + Save-as-tracked-application) at the root cause in FirestoreWorkspaceStore.

Files to read BEFORE writing any code (in this order):
1. web/async_runner.py — FULL. The docstring describes this exact bug and the canonical fix
   (one persistent background event loop shared process-wide via run_coroutine_threadsafe).
2. database/workspace_store.py — FULL. Note asyncio.run() in load/save/list_user_ids and that
   the AsyncClient is built once in __init__ (client=... injectable for tests).
3. config.py::get_firestore_async_client — note it is NOT cached (fresh AsyncClient per call).
4. web/profile_store.py::save_profile and web/application_store.py::save_tailored_application —
   both do store.load(user_id) THEN store.save(user_id, ...) on ONE store instance.
5. jobs/pending_action_sweep.py — confirm the sweep also uses FirestoreWorkspaceStore (sync,
   standalone Cloud Run Job; no web loop). Your fix must not break the sweep.
6. tests/test_profile_store.py, tests/test_application_store.py, and any workspace_store test —
   understand the in-memory test double (InMemoryWorkspaceStore) and injected-client patterns.

PAUSE CONDITIONS (stop and report before writing code):
- If you find MORE than these two save paths reuse a single store across load+save, list them.
- If importing web/async_runner from database/ would be needed (layering inversion: database
  must NOT import from web). Report which approach you recommend (A vs B below) and WAIT if the
  layering choice is non-obvious.

Preferred fix (Approach A — minimal, layer-clean, self-contained per call):
  In database/workspace_store.py, stop reusing one AsyncClient across event loops. Create the
  AsyncClient INSIDE each async method (bound to that call's loop) when no client was injected,
  and close it in a finally block so no gRPC transport outlives its loop:
    - Keep __init__ accepting an optional injected `client` (tests pass InMemory double) AND an
      optional `client_factory` defaulting to config.get_firestore_async_client. Do NOT build the
      real client in __init__ anymore — store the factory; only use an injected client if given.
    - In _aload/_asave/_alist_user_ids: `client = self._client or self._client_factory()`; if we
      created it (not injected), `try: <use> finally: await client.close()`. Guard close() so an
      injected in-memory double (no close) is untouched.
  This makes every asyncio.run() self-contained: two asyncio.run calls in save_profile each get
  their own client on their own loop; no reuse across a closed loop.

Alternative (Approach B — only if the reviewer/owner prefers a shared loop): relocate the
  persistent-loop helper from web/async_runner.py to a layer-neutral module (e.g. integration/
  or a top-level async_bridge.py), update the web import, and route FirestoreWorkspaceStore's sync
  methods through it instead of asyncio.run. More efficient (one long-lived client) but larger
  blast radius. Do NOT choose B without explicit confirmation.

Scope (Approach A):
  database/workspace_store.py:
    - Refactor client acquisition as above (factory + per-call create/close; injected client
      short-circuits and is never closed by the store).
    - Behavior of load/save/list_user_ids is otherwise unchanged.
  Do NOT change web/profile_store.py or web/application_store.py logic (their load-then-save is
  fine once the store no longer reuses a dead loop). You MAY improve the user-facing error copy
  only if trivially in scope — otherwise leave it.

Tests (tests/test_workspace_store*.py — create if absent):
  - test_workspace_store_load_then_save_uses_fresh_client_each_call: inject a client_factory
    (monkeypatched / passed) that returns a fresh recording fake per call; construct ONE store;
    call load(user_id) then save(user_id, ws); assert the factory was invoked once per async op
    (i.e. the store did NOT reuse a single client across the two calls). This is the regression
    guard for the closed-loop reuse.
  - test_workspace_store_closes_created_client: the per-call created fake records close(); assert
    close() was awaited for a store-created client, and NOT called for an injected client.
  - test_injected_client_not_closed_by_store: pass a client explicitly; assert store uses it and
    never calls close() on it.
  - Keep existing profile_store / application_store / sweep tests green (they use in-memory doubles).

Acceptance criteria (named tests):
- test_workspace_store_load_then_save_uses_fresh_client_each_call
- test_workspace_store_closes_created_client
- test_injected_client_not_closed_by_store
- Existing test_profile_store.py, test_application_store.py, and pending-action-sweep tests green.

DoD:
- make check green (ruff, mypy --strict, pytest). No contract change.
- No layering inversion (database/ does not import web/).
- Gemini/Copilot review PASS.
- Report READY FOR REVIEW with: chosen approach (A/B) + rationale; criterion→test map;
  confirmation the sweep job path is unaffected.
```

---

### ✅ BUG-2 — Grill "Currently grilling" banner missing on the first question after resume

> Read first: `web/grill_ui.py` — `_entry_label`/`_frontier_label`/`_effective_frontier_label`
> (~L167), `_migrate_education_on_resume` (~L246), `_try_resume` (~L300), `render_grill` (banner at
> ~L655: `if not grill_complete and grill_entry_label: st.info(...)`), and
> `tests/test_grill_frontier_label.py`. Selection truth: `workflows/nodes.py::_get_frontier_entry`.

**Symptom (owner's words):** "grill me does not show the banner on the first question **after you
come back to it**. It does show in subsequent steps." i.e. the bug is on the **resume** path, not
on a fresh start or a "Grill me about this" jump.

**Original groomed diagnosis was WRONG (kept here as a caution):** the first draft claimed
`_apply_pending_jump`'s `session.advance()` clears `grill_frontier`, leaving an empty label on the
first question. Live reproduction (Pylance) **refuted** this — after both a fresh start and a jump,
`grill_frontier` stays SET and `_frontier_label` returns the correct label. The grill node's
opening-question branch (`workflows/nodes.py` ~L855) explicitly *re-writes* `grill_frontier`; it
never clears it. Lesson: verify a diagnosis against a reproduction before implementing.

**Real root cause (reproduced):** on resume, `_migrate_education_on_resume` **blanks**
`grill_frontier` to `""` whenever the pinned entry is no longer grillable — e.g. the user finished
that entry (status `GRILLED`) before leaving (`_frontier_needs_reset → True`). `_try_resume` then
set `grill_entry_label = _frontier_label(state)`, which reads `grill_frontier` directly and returns
`""` → no banner on the first question. The *next* turn's grill node auto-picks the next needs-work
entry via `_get_frontier_entry` and re-pins the frontier, so the banner reappears from then on.

**Fix (implemented, web/grill_ui.py only, no contract change):**
- Extracted `_entry_label(entry) -> str` ("Title · Org", title-only if no org, "" if None) and made
  `_frontier_label` delegate to it.
- Added `_effective_frontier_label(state) = _frontier_label(state) or _entry_label(_get_frontier_entry(state))`
  — when the frontier is blank, derive the label from the entry the grill node WILL pick next, using
  the graph's own selection function so the banner always matches the actual next question.
- `_try_resume` now sets `grill_entry_label = _effective_frontier_label(state)`. Start/jump/submit
  paths are unchanged (they already keep the frontier set; the helper is a safe superset).
- `from workflows.nodes import _get_frontier_entry` (web → workflows domain; `workflows.nodes` has
  "No UI imports", so no import cycle).

**Acceptance criteria (named tests, `tests/test_grill_frontier_label.py`):**
- `test_entry_label_title_and_org`, `test_entry_label_title_only`, `test_entry_label_none_is_empty`
- `test_effective_label_uses_frontier_when_set`
- `test_effective_label_falls_back_to_next_grillable_when_frontier_blank` — the regression guard
  reproducing the resume scenario (pinned entry GRILLED + frontier `""` → banner names the next
  needs-work entry, not `""`).
- `test_effective_label_empty_when_nothing_left_to_grill`
- Existing grill/frontier tests remain green.

**DoD:** `make check` green; no contract change; Copilot review PASS.

---

