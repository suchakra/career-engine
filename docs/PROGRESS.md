# CareerEngine — Progress Tracker

> Single source of truth for **what's done vs. pending**. Update this at the end of every work
> session / sub-agent run. Keep entries terse. Legend: ✅ done · 🟡 in progress · ⬜ not started · 🚫 blocked.

Last updated: **2026-07-01** — *ALL of Phase 2 built & **Sonnet-reviewed PASS** (**381 tests** green). Core (2C + contract **v2.2.0** + 2D + 2A) tagged `contract-v2.2.0`; + UserWorkspace Firestore repo + 2B web-auth bootstrap + 2E capstone runbook/skill (Sonnet gate: 1 must-fix [try_bootstrap swallows non-auth errors] + 3 nits, all fixed). Pushed. **Copilot out for the month — Sonnet is the sole gate.** Next: Phase 3, or deferred thin wiring, or a live runbook dry-run.*

---

## Milestone status
| Phase | State | Notes |
|-------|-------|-------|
| Planning & architecture | ✅ | ARCHITECTURE.md, REFINED_PROJECT_PLAN.md, this file, AGENT_EXECUTION_PROMPT.md |
| Phase 0 — Contract Freeze | ✅ | Sonnet-built, Opus-reviewed (1 round: dead model IDs + Free-mode grilling fixed). Frozen, tag `contract-v1.0.0`. |
| Phase 1 — Core loop (CLI) | ✅ | WS-A/B/C/D + integration all merged & Opus-PASS. Turn-based CLI discovery loop runs end-to-end → PDF. 228 tests. Contract v1.1.0. |
| Phase 1.3 — Review hardening (no contract change) | ✅ | Done; stays v1.1.x, 230 tests. Required items from [REVIEW.md §7](REVIEW.md) all merged: docs truth (#7,#8), upgrade-signal band-aid + E2E test (#1,#11), model_client errors (#4), Firestore loud-fallback (#3). Optional #6 (FakeFirestore move) now tracked in Phase 1.7. |
| Phase 1.5 — Resume-aware + progressive discovery | ✅ | All five pieces built (contract v2.0.0, tag `contract-v2.0.0`, 317 tests). CORE (CONTRACT+GRILL+METRICS) Sonnet-built/Opus-reviewed/merged; INGEST + DISCOVERY Opus-built this session + Sonnet-reviewed PASS. Stale-docstring (#9) resolved. Deferred integration items (resume-file CLI wiring, full session-resume, discovery_turn in main graph) tracked in [HANDOFF.md](HANDOFF.md). |
| Phase 1.7 — Integration closure (deferred Phase-1 work) | ✅ | 1.7-A resume-file CLI wiring, 1.7-B true session resume (load-before-create), 1.7-C discovery_turn graph edge (contract **v2.1.0**, additive `coverage_confirmed`), 1.7-D FakeFirestore→`tests/fakes.py`. 339 tests. Sonnet PASS + Copilot PASS; **tagged `contract-v2.1.0`, pushed.** 3 optional non-blocking polish items in [REVIEW.md](REVIEW.md) deferred to Phase 2. |
| Phase 2 — Web / Infra / Async | ✅ | **All workstreams built & Sonnet-reviewed PASS (381 tests), tagged `contract-v2.2.0`, pushed.** 2C infra + contract v2.2.0 + 2D sweep + 2A dashboard + UserWorkspace Firestore repo + 2B web-auth bootstrap + 2E capstone runbook/skill. Deferred thin wiring (streamlit discovery-state load, sweep HTTP endpoint, terraform devcontainer dep) tracked in [HANDOFF.md](HANDOFF.md). Gate is Sonnet-only (Copilot out). |
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

## Phase 1.3 — Review hardening  *(no contract change; stays v1.1.x)*
Stabilize the foundation before launching 1.5 builders. Triage + rationale: [REVIEW.md §7](REVIEW.md).
- ✅ **#7** docs truth: ARCHITECTURE.md freshness header corrected (was "pre-implementation"); PROGRESS banner refreshed
- ✅ **#8** grooming sequencing contradiction resolved (CORE serial → INGEST ∥ DISCOVERY parallel)
- ✅ **#1 band-aid** upgrade signal: `TurnResult.from_state` now reads the real `_upgrade_required` side-channel via new `cli.session.read_raw_state` (drops the dead `current_question` string-match) and surfaces the signal's `user_message`
- ✅ **#11** added CLI→workflow upgrade-required E2E assertions in `tests/test_integration.py` (`TestUpgradeRequiredReachesCli`: shortfall → `upgrade_required=True`; normal turn → `False`)
- ✅ **#4** `integration/model_client.py` `generate()` no longer swallows transport errors into `""` — exceptions propagate (matches the default factory)
- ✅ **#3** Firestore: in-memory fallback is now LOUD (stderr warning naming the failure + "nothing will be persisted"); env-aware hard-stop policy remains a hosted-path decision in Phase 2 (decision: [REVIEW.md §5](REVIEW.md))
- ⬜ **#6** *(optional — now tracked in Phase 1.7)* move `FakeFirestoreClient` + its `_Fake*` helper hierarchy out of `database/firestore_session.py` into `tests/`; low value now, per [REVIEW.md §7.3](REVIEW.md)

## Phase 1.5 — Resume-aware ingestion & progressive discovery  *(contract v2.0.0)*
Spec: [ARCHITECTURE.md §12](ARCHITECTURE.md) · roadmap: [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md) · **groomed prompts + status: [GROOMING.md](GROOMING.md)**. **All 1.5 build pieces merged; integration closure moves to Phase 1.7.**
- ✅ **CONTRACT** v2.0.0: `work_timeline: list[Entry]`, `coverage_through`, `reference_date` (injected clock), `grill_frontier`; `entry_id` on `StarStory`; pillar fields removed; pure helpers `discovery_completeness` / `recent_window_complete`. Tag `contract-v2.0.0`.
- ✅ **GRILL**: entry-based grill loop (backward-chronological, jumpable frontier), discovery turn (confirm coverage, append discovered entries), skip already-quantified, ~15-yr soft horizon → summarized, 5-turn brake + HITL preserved. Minimal entry-based `ingest_node` seam (INGEST upgrades it).
- ✅ **METRICS**: `_contains_real_metric` extended (users/downloads/stars, team size, rank, dataset scale, citations, GPA) with per-pattern tests; eng patterns retained.
- ✅ **1.5-INGEST** `tools/resume_parser.py` — vision ingest (PDF/photo → multimodal Flash → timeline); `GeminiModelClient.generate_multimodal` + `MediaPart`; `ingest_node` derives `coverage_through` + handles vision-preseeded timelines. Bytes are PII (never persisted). PDFs sent natively (no rasterization dep). Note: SSRF guard (#2) is a URL-fetch concern — N/A to file/byte ingest; revisit if a URL-based resume fetch is added.
- ✅ **1.5-DISCOVERY** (cli/): `discovery_completeness` progress meter + portfolio depth, never-block consent-respecting nudge (snooze via `cli/prefs.py`, injected "today"), backward return loop. Stale-docstring (#9) resolved.
- 🟡 Exit demo (engine built; CLI surfacing partial — now tracked as **Phase 1.7**): stale resume → timeline → discovery adds roles → grilling → readiness nudge → resume backward. Helpers/nodes are tested; full end-to-end CLI wiring of resume-file upload + session-resume moves to Phase 1.7.

## Phase 1.7 — Integration closure (deferred Phase-1 work)  *(built; review in progress)*
- ✅ **1.7-A** resume-file upload wired into `grill` (`main.py --resume-file`; `cli/app.py` `guess_resume_mime`/`parse_resume_file` → `parse_resume` → `start(work_timeline=…)`). Parse failures surfaced; bytes never persisted; no-file path unchanged.
- ✅ **1.7-B** true session resume: `cli.session.get_session_state_if_exists` (load-before-create); `--session-id` = resume intent (loads prior state, no clobber); missing id → user-safe message.
- ✅ **1.7-C** `discovery_turn_node` wired into the main graph + router branch (contract **v2.1.0**, additive `coverage_confirmed`; fires once when a coverage boundary is unconfirmed; terminal-per-turn, no spin).
- ✅ **1.7-D** `FakeFirestoreClient` + `_Fake*` moved to `tests/fakes.py`; prod module exposes no test doubles.
- 🟡 Exit demo: resume-file → timeline → discovery turn (in-graph) → backward grilling → resume same session id → tailor (never gated). Unit/integration tested; one scripted end-to-end runbook remains for the capstone (Phase 2 polish).
- ⬜ **Tag `contract-v2.1.0`** after Sonnet + Copilot review PASS.

## Phase 2 — Web, Infra, Async  *(2C/contract/2D/2A built; Sonnet review in progress)*
- ✅ **2A** `web/` Streamlit dashboard — `main.py web` path; view-model + injectable renderer (testable without Streamlit runtime); pending-action surface + consent-respecting nudge (never gates tailoring).
- ✅ **contract v2.2.0** `UserWorkspace` + `Application`(+`ApplicationStatus`) + `PendingAction` (additive; per-user portfolio doc distinct from session state).
- ✅ **2C** `infrastructure/modules/*` (Cloud Run, Firestore, Artifact Registry, Secret Manager, Scheduler) + `envs/{dev,prod}` + README; Terraform SA grant `roles/secretmanager.secretAccessor` (least privilege); `make tf-check`/`deploy`/`destroy`. fmt+validate green both envs.
- ✅ **2D** `jobs/pending_action_sweep.py` — pure+idempotent 14-day sweep over `UserWorkspace` + `WorkspaceStore` orchestration with per-user error isolation (Cloud Scheduler→Cloud Run job; wiring via 2C scheduler module).
- ✅ **2B** web auth/session bootstrap — `web/bootstrap.py` ties the (already-built) `FirebaseAuthProvider` → stable user_id → workspace load; `try_*` safe unauthenticated path; streamlit login gate. (Provider from Phase-1 WS-D; glue is new.)
- ✅ **UserWorkspace Firestore repo** — `database/workspace_store.py` `FirestoreWorkspaceStore` (sync bridge over async client; keyed by user_id, contract-stamped, unknown-major refused, no secrets). The real `WorkspaceStore` for 2D + 2A.
- ✅ **2E** capstone packaging — `docs/CAPSTONE_RUNBOOK.md` (reproducible runbook + proof-point→evidence map + honest tradeoffs) + `skills/cloud_ops/SKILL.md`.
- 🟡 Exit criteria: `make check` (381) + `make tf-check` green (deterministic); `make deploy` needs GCP creds; web+CLI share state via the workspace repo. **Deferred thin wiring:** streamlit discovery-session load for the meter; sweep Cloud Run HTTP endpoint + IdP frontend token exchange. All under Sonnet gate (in progress) before push.

## Phase N — opportunistic value-adds (wanted; not v1-blocking)
- ⬜ Outcome learning, positive-reinforcement only — per user + per job type, learn what résumé format/wording correlated with reaching interview; transparent; opt-in anonymized global "what works" DB; reuses §8 async infra — [ARCHITECTURE.md §8.1](ARCHITECTURE.md)

## Backlog — post-v1 (NOT scheduled)
- ⬜ Interview preparedness (mock interviews from researched company+role question shapes) — [ARCHITECTURE.md §13](ARCHITECTURE.md)

## Phase 3 — Hardening & Eval
- 🟡 **`evaluation/user_simulator.py` + `test_config.json` (vague-applicant scenarios) — BUILT** (branch `feat/phase-3-eval`, 388 tests). Deterministic simulator drives the REAL Runner: vague answers pushed back → specific yields validated metric StarStory; 5-turn brake fires (qc=5); records Pro-escalation rate (0 happy / >0 when REASONING_HIGH refused). `evaluation/` now in gates (ruff+mypy+pytest). Under Sonnet+Copilot PR review.
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
- 2026-06-29 — **Contract amended 1.1.0 → 2.0.0** (BREAKING MAJOR; user-approved, no migration — no production data). Tag `contract-v2.0.0`. Added `Entry` model + `ExperienceType`/`EntryStatus` enums; `CareerEngineState` gains `work_timeline`/`coverage_through`/`reference_date`/`grill_frontier` and **loses** pillar fields (`target_competencies`, `active_gaps`, `current_pillar`); `StarStory` gains `entry_id`. Pure helpers `discovery_completeness`/`recent_window_complete` (nudge/meter only; gate nothing; use injected `reference_date`, never `datetime.now()`).
- 2026-06-29 — **Phase 1.5 COMPLETE** (INGEST + DISCOVERY landed; 285→317 tests). **Process note:** to conserve session budget, INGEST + DISCOVERY were built directly by Opus (inverting the usual Sonnet-builds rule) and then **Sonnet-reviewed** (verdict PASS, 0 must-fix; 4 optional nits all applied: enum-vs-string-literal, stronger adapter assertion, `_apply_entry_status_rules` preserves prior progress, test docstring accuracy). A Copilot review is also planned by the user. INGEST = vision parser + multimodal adapter (PDFs native, no rasterization dep; bytes are PII, never persisted). DISCOVERY = CLI-only nudge/meter/return-loop + `cli/prefs.py` snooze (UI state kept off `CareerEngineState`). Deferred integration items recorded in HANDOFF.
- 2026-06-29 — **Phase 1.5 CORE COMPLETE** (CONTRACT+GRILL+METRICS, one Sonnet worktree, Opus-PASS, merged `--no-ff`; 230→285 tests). Grill loop is now entry-based (backward-chronological, jumpable frontier), with discovery turn, already-quantified skip, ~15-yr soft horizon, and extended metric patterns; 5-turn brake + HITL preserved. Reviewer notes (non-blocking): `discovery_completeness` counts SKIPPED as done; `recent_window_complete` treats DOCUMENTED as incomplete (stricter than spec) — both defensible. Remaining 1.5: INGEST ∥ DISCOVERY.
- 2026-06-29 — **Phase 1.3 hardening COMPLETE** (stays contract v1.1.x; 228→230 tests). Merged #1 (upgrade-signal band-aid via `read_raw_state` + `TurnResult.upgrade_message`), #11 (CLI upgrade-required E2E test), #4 (model_client errors propagate, no `""` swallow), #3 (loud Firestore in-memory fallback). Optional #6 (FakeFirestore move) now carried into Phase 1.7 — moving it means relocating the whole `_Fake*` hierarchy; low value until the next Firestore touch. Root-cause fixes (#1b typed event, #2 SSRF, #9 stale docstring) remain folded into Phase 1.5 per the triage.

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
