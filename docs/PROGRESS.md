# CareerEngine — Progress Tracker

> Single source of truth for **what's done vs. pending**. Update this at the end of every work
> session / sub-agent run. Keep entries terse. Legend: ✅ done · 🟡 in progress · ⬜ not started · 🚫 blocked.

Last updated: **2026-06-28** — *Phase 0 contract FROZEN (Opus PASS). Ready for Phase 1 fan-out.*

---

## Milestone status
| Phase | State | Notes |
|-------|-------|-------|
| Planning & architecture | ✅ | ARCHITECTURE.md, REFINED_PROJECT_PLAN.md, this file, AGENT_EXECUTION_PROMPT.md |
| Phase 0 — Contract Freeze | ✅ | Sonnet-built, Opus-reviewed (1 round: dead model IDs + Free-mode grilling fixed). Frozen, tag `contract-v1.0.0`. |
| Phase 1 — Core loop (CLI) | ✅ | WS-A/B/C/D + integration all merged & Opus-PASS. Turn-based CLI discovery loop runs end-to-end → PDF. 228 tests. Contract v1.1.0. |
| Phase 1.5 — Resume-aware + progressive discovery | ⬜ | Spec'd ([ARCHITECTURE.md §12](ARCHITECTURE.md)). Vision ingest, role-based `work_timeline` (replaces pillars), gap-as-roles, apply-readiness gate, backward continuation. Contract v1.2.0. |
| Phase 2 — Web / Infra / Async | ⬜ | |
| Phase 3 — Hardening / Eval | ⬜ | |

---

## Phase 0 — Contract Freeze  *(blocking; do before any fan-out)*
- ✅ `pyproject.toml` — pinned deps; real `google-adk==2.0.0` import paths verified
- ✅ `.env.example`
- ✅ `config.py` — settings, `CONTRACT_VERSION=1.0.0`, client factories, `AccessMode` flag
- ✅ `schema.py` — `CareerEngineState`, `StarStory`, `Capability`, `AgentMessage` envelope, `UpgradeRequired`
- ✅ `models/registry.py` — capability→model resolver iface + Free/BYOK routing (Free serves grilling on 2.5-flash)
- ✅ `auth/provider.py` — `AuthProvider` + `KeyVault` interfaces (stubs)
- ✅ `database/` `tools/` `workflows/` Runner — typed stub signatures (real `discovery_router` brake)
- ✅ `Makefile` real `lint` (ruff) + `typecheck` (mypy strict) + `test` (pytest); `make check` green
- ✅ Golden type test + registry behavior test (34 tests) wired into `make test`
- ✅ **FROZEN**: contract tagged `contract-v1.0.0`; signatures change only via `CONTRACT_VERSION` bump

## Phase 1 — Core agent loop (CLI-first MVP)
- ✅ WS-A `workflows/discovery_graph.py` — graph, edges, `discovery_router`, 5-turn brake
- ✅ WS-A `workflows/nodes.py` — ingest / grill / checkpoint(HITL) / finalize / tailor + CoT prompts
- ✅ WS-C `database/firestore_session.py` — ADK SessionService adapter (in-memory fake for tests)
- ✅ WS-B `tools/web_scraper.py` — two-step fetch + BULK_CHEAP clean
- ✅ WS-B `tools/pdf_renderer.py` + `templates/classic_resume.html` (WeasyPrint; deviation noted)
- ✅ WS-* `models/registry.py` — resolver + Free/BYOK routing (Phase 0; capability detection deferred)
- ✅ WS-D `auth/cli_auth.py` + `auth/key_vault.py` (local + Secret Manager) + `firebase_auth.py`
- ✅ `main.py` + `cli/` + `integration/model_client.py` — CLI entrypoint wiring the ADK Runner (turn-based HITL loop)
- ✅ Exit demo: vague answer → quantified STAR → checkpoint@5 → PDF (e2e test via real Runner, asserts %PDF)

### Integration notes carried from WS reviews (for the integration step)
- WS-C `create_session` is last-write-wins (differs from ADK `InMemorySessionService` which raises on duplicate); ADK event log not durably persisted (state is). Confirm against Runner usage.
- WS-C `FakeFirestoreClient` lives in the prod module — candidate to move to `tests/`.
- WS-A grill uses `pending_user_answer`/`current_question`; CLI loop must set `pending_user_answer` and `checkpoint_verified`, and read `current_question`/`checkpoint_delta_summary`.
- No live `runner.run_async` end-to-end smoke yet — owned by integration / WS-F.

## Phase 1.5 — Resume-aware ingestion & progressive discovery  *(contract v1.2.0)*
Spec: [ARCHITECTURE.md §12](ARCHITECTURE.md) · roadmap: [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md). Not started.
- ⬜ Contract v1.2.0: `work_timeline: list[Role]`, `coverage_through`, `reference_date` (injected clock); `role_id` on `StarStory`; replace pillar fields with role-based + `grill_frontier`
- ⬜ `tools/resume_parser.py` — vision ingest (file/photo → multimodal Flash → timeline); multimodal entry point on model-client adapter
- ⬜ Rework `ingest_node` + grill loop to role-based; add discovery turn (confirm coverage, append missing roles); skip already-quantified bullets
- ⬜ Progressive discovery: `is_apply_ready` gate (last-5-yrs; new-grad fallback), `grill_frontier` backward continuation (jumpable; soft horizon), derived progress meter
- ⬜ Gate tailoring on `is_apply_ready`
- ⬜ Exit demo: stale resume image → timeline → discovery adds roles → role grilling → readiness unlocks tailoring → later session resumes backward

## Phase 2 — Web, Infra, Async
- ⬜ `main.py` Streamlit path — dashboard + pending-action surface (incl. progressive-discovery login nudge, consent-respecting)
- ⬜ `auth/firebase_auth.py` — Identity Platform (web)
- ⬜ `infrastructure/modules/*` — Cloud Run, Firestore, Artifact Registry, Secret Manager
- ⬜ Terraform SA grant `roles/secretmanager.secretAccessor`
- ⬜ `infrastructure/envs/{dev,prod}` + `infrastructure/README.md`
- ⬜ `jobs/pending_action_sweep.py` + Cloud Scheduler wiring (14-day)
- ⬜ `skills/cloud_ops/SKILL.md`
- ⬜ Exit: `make deploy` to dev; web+CLI share state; sweep flags stale apps

## Phase 3 — Hardening & Eval
- ⬜ `evaluation/user_simulator.py` + `test_config.json` (vague-applicant scenarios)
- ⬜ Monitoring/logging for graph hangs
- ⬜ Security review (key handling, IAM least-privilege, scraper/PDF injection)
- ⬜ CoT tuning; measure & reduce Pro-escalation rate

---

## Decisions log (append-only)
- 2026-06-28 — D1–D7 locked (see [REFINED_PROJECT_PLAN.md §1](REFINED_PROJECT_PLAN.md)).
- 2026-06-28 — Dropped Gemini 1.5 (legacy) and `tenant_id = SHA-256(key)`; adopted Identity Platform + Capability Registry.
- 2026-06-28 — Build process: **Sonnet builds + tests, Opus reviews + gates**. No self-declared "done"; only an Opus PASS ticks this file. Builders run in `isolation: "worktree"`.
- 2026-06-28 — **ADK 2.0 version installed: `google-adk==2.0.0`** (latest 2.x at time of Phase 0). See "ADK import path deviations" below.
- 2026-06-28 — **Model policy frozen**: defaults `gemini-2.5-flash` (FAST + Free reasoning baseline), `gemini-2.5-flash-lite` (bulk), `gemini-2.5-pro` (BYOK reasoning ceiling). 2.0 models removed (shut down 2026-06-01). Free Mode serves grilling on Flash+CoT; `UpgradeRequired` is a node-level validation signal, not a resolver refusal.
- 2026-06-28 — **Phase 0 contract FROZEN** after Opus PASS (tag `contract-v1.0.0`). Any change to schema.py / config.py / public interfaces now requires a `CONTRACT_VERSION` bump.
- 2026-06-29 — **Contract amended 1.0.0 → 1.1.0** (backward-compatible MINOR; user-approved). Added optional `CareerEngineState` fields: `pending_user_answer`, `current_question`, `professional_summary`, `master_resume_json`, `tailored_resume_json`, `jd_text`. Reason: WS-A had overloaded `raw_history_text` / `checkpoint_delta_summary` (colliding with WS-B's resume rendering). WS-B `pdf_renderer` now reads `professional_summary`. WS-A reworked to use dedicated fields. Existing 1.0.0 docs still load (defaults; WS-C version gate allows minor diffs).
- 2026-06-29 — Build fix: `config.py` uses `import google.cloud.firestore as firestore` form (mypy namespace-package quirk surfaced once cloud SDKs were installed).

## Blockers / open questions
- ⬜ Confirm exact `google-adk` 2.0 module/import names against the installed package → **RESOLVED** (see ADK deviations below).
- ⬜ Decide Free-Mode managed-key quota policy (per-user RPD cap to control platform cost).

## ADK 2.0 import path deviations from ARCHITECTURE.md
ARCHITECTURE.md describes ADK 2.0 in structural terms; the actual installed package differs in the following ways:

| Architecture.md concept | Actual google-adk 2.0.0 import |
|--------------------------|-------------------------------|
| "Workflow Runtime" (generic) | `google.adk.workflow.Workflow` — a Pydantic BaseModel subclass, NOT a function |
| "BaseNode" | `google.adk.workflow.BaseNode` — Pydantic model; subclass via `google.adk.workflow.Node` |
| "FunctionNode" | `google.adk.workflow.FunctionNode` — wraps a Python function; `parameter_binding='state'` binds from ctx.state |
| "Edge" | `google.adk.workflow.Edge` — `from_node`, `to_node`, `route` fields |
| "START sentinel" | `google.adk.workflow.START` — a special BaseNode instance |
| "DEFAULT_ROUTE sentinel" | `google.adk.workflow.DEFAULT_ROUTE == "__DEFAULT__"` |
| "Runner" | `google.adk.runners.Runner` — takes `node=`, `agent=`, or `app=` plus `session_service=` |
| "SessionService" | `google.adk.sessions.BaseSessionService` — abstract; `InMemorySessionService` is concrete |
| "LlmAgent" | `google.adk.agents.LlmAgent` — mode must be `'chat'` or `'task'`; task-mode agents cannot be static workflow graph nodes |
| No "UserSimulator" in 2.0.0 | Phase 0 stubs reference a `UserSimulator`; actual 2.0.0 package does not expose one. Phase 3 WS-F must verify availability or implement its own. |

All deviations have been followed in the Phase 0 stubs. The ARCHITECTURE.md snippets remain structural references; the real API is what matters.
