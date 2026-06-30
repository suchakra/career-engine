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

1. Phase 1.7 (integration closure of deferred Phase-1 work).
2. Phase 2 (web/infra/async fan-out once 1.7 is merged).

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

## Not groomed here

Phase 3 hardening/eval and post-v1 backlog remain intentionally out of launch scope for this pass.
