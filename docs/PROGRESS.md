# CareerEngine — Progress Tracker

> Single source of truth for **what's done vs. pending**. Update this at the end of every work
> session / sub-agent run. Keep entries terse. Legend: ✅ done · 🟡 in progress · ⬜ not started · 🚫 blocked.

Last updated: **2026-07-12** — *Phase 10 COMPLETE; `qa` env live; **FEATURE PARITY COMPLETE — all slices (P1–P5, PR #76–#83) merged to `master` and deployed to qa.** Next: walk the app on qa, then promote to dev + groom Phase 11. Historical Phase-10 detail below.* *Phase 10 built API-first; **slices 10.1 + 10.2 + 10.3 + 10.4 merged (PR #63, #64, #65, #66)**. PR #59 recorded the Streamlit→Next.js+FastAPI decision (ARCHITECTURE §16) + build tickets 10.1-10.7; PR #60 resolved the 10.1 auth shape (Firebase bearer, AD-16.4) + UI mockup + Phase 11 roadmap; PR #61 added the context-management strategy; PR #62 added the component inventory + AD-16.8 (TanStack Query data layer) + AD-16.9 (frontend test stack: Vitest/RTL/MSW/Playwright) + pinned Node 22 in the devcontainer; PR #63 shipped 10.1 (FastAPI app + Firebase-bearer auth boundary, `api/`, `GET /api/health` + `GET /api/me`); PR #64 shipped 10.2 (read APIs — protected `GET /api/dashboard` + `/api/portfolio` + `/api/jobs`, degrade-to-empty); PR #65 shipped 10.3 (write APIs — protected `POST /api/profile` + `/api/experience` + `/api/applications` + `PUT /api/preferences`, reusing the store write-seams, 422 on malformed body); PR #66 shipped 10.4 (grill API — protected `POST /api/grill` record + `GET /api/grill/stream` SSE, reusing `DiscoverySession`, `event: turn`/`done`/`error`, 422 on empty/bad input). contract v2.8.0. **Slice 10.5 (Next.js app shell) MERGED (PR #67, squash) — `frontend/` scaffold, foundational components, TanStack Query data layer (optimistic write→rollback), Firebase-bearer auth wiring, light/dark theme, Vitest/RTL/MSW + Playwright login e2e, `make frontend-check` lane + CI job; Copilot review addressed (9 comments). Presentation/transport only, no contract change.** **10.6 COMPLETE — 10.6a grill streaming UI (PR #68) + 10.6b tailor/résumé-export API (PR #69) + Tailor UI (PR #70)**, all Copilot-reviewed. Every Phase-10 UI screen is now live on Next.js + FastAPI. **Only 10.7 (cutover — delete Streamlit `web/`, deploy) remains, deferred to Phase 11** (pairs with 11.A's new prod-like env; current env frozen for Kaggle). Tailor export is a stateless POST-render RPC (`POST /api/resume/{fmt}`), not a cached GET — the domain has no server-side tailored-résumé store.*

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
| Phase 3 — Hardening / Eval | ✅ | Queue COMPLETE (PRs #1–#6): user-simulator eval, security review, observability, CoT/Pro-escalation gate (v2.3.0), Phase-2 deferred wiring, capstone dry-run. Detail below. |
| Phase 5 — Tailoring & résumé quality | ✅ COMPLETE | **5A DONE** (PR #29): real ATS-safe résumé grouped by role + education + JD-aligned skills; `web/resume_render.py` PDF/DOCX/MD. **5B DONE** (PR #31): save a tailored résumé as a tracked `Application` (dashboard + 14-day sweep; no contract change). **Persist Contact DONE** (PR #32, **contract v2.6.0**): `UserProfile` on `UserWorkspace` + `web/profile_store.py`; the Tailor contact header pre-fills + persists. **5C DONE** (PR #33): the web app now offers a **master résumé** download (Portfolio → "Build my master résumé") rendered through the SAME `StructuredResume` schema + `web/resume_render.py` as the tailored one (`master_structured_resume()`), so both are formatting-consistent. (The CLI's legacy `tools/pdf_renderer` remains a secondary demo path — full CLI unification is a follow-up.) **4E DONE** (PR #34, **contract v2.7.0**): pin an experience as tailoring priority — `Entry.highlighted` (additive) + a Portfolio pin/unpin toggle (`portfolio_store.set_entry_highlight`) + the Tailor always includes a pinned experience's achievements. **Pre-GA /security-review DONE** (PR #35): scoped the runtime SA's Secret Manager reads to `ce-key-*` (was project-wide) + per-secret auth grants + `user_id` validation; findings logged in [SECURITY.md](SECURITY.md). **Phase 5 COMPLETE.** See [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md) Phase 5. |
| Phase 4 — Portfolio Workbench | ✅ (4E deferred) | 4A sidebar nav (**PR #15**), 4B portfolio view (**#16**), 4C+4D steerable grill + add-experience seam (**#17**) — all shipped & **deployed** to dev, Copilot-reviewed, **no contract change**. 4E highlight/pin deferred (needs +minor bump). [GROOMING.md](GROOMING.md) Phase 4 / [ARCHITECTURE.md §14](ARCHITECTURE.md) / D10. |
| Phase 6 — Two-agent (A2A) job discovery (capstone) | ✅ merged (packaging pending) | **Merged to master via PR #30, tagged `contract-v2.5.0`, 560 tests.** Sonnet review PASS + Copilot addressed. Ontology (`JobOpportunity`/`EvaluationDiff`/…) → real FastMCP server `discovery/mcp_server.py` over a live key-free source → stateless `Scout` (MCP client) → stateful `PrimaryAgent` (deterministic hard-reject gate + injectable agentic evaluator + bounded MAX_ITERATIONS=3 loop → `EvaluationDiff`) → `career-engine discover` + idempotent `LedgerStore` → Tailor reuse. LIVE end-to-end run verified. **Pending:** PACKAGING only (video/writeup/README/diagram — user-owned). Spec [ARCHITECTURE.md §15](ARCHITECTURE.md); demo [DISCOVERY_DEMO.md](DISCOVERY_DEMO.md). |
| Phase 7 — Job Discovery web surface | ✅ COMPLETE | **7A** (PR #38, **contract v2.8.0**): `UserWorkspace.discovery_preferences` + `web/preferences_store.py`. **7B** (PR #39): Jobs nav view — `web/jobs.py`, `web/jobs_runner.py`, `_render_jobs` in `streamlit_app.py`. **7C**: "Tailor to this job." Post-7: HITL "Not interested" (PR #40), `StdioMcpClient` (PR #41), HITL "Keep this" (PR #42). ⚠️ Deploy gap — Jobs is wired in code; Cloud Run dev app needs Phase 8A redeploy. |
| Phase 8 — Operational hardening | 🟡 in progress | ✅ 8A · ✅ 8B (PR #43) · ✅ 8C (PR #44) · ✅ 8D (PR #45) · ✅ 8G (PR #46) · ⬜ 8E deployer-SA · ⬜ 8F HITL TTL. Groomed in [GROOMING.md §Phase 8](GROOMING.md). |
| Phase 9 — Replace Streamlit; proper product UI | ✅ done | ✅ 9J · ✅ 9B · ✅ 9K · ✅ 9I · ✅ 9G · ✅ 9C · ✅ 9E · ✅ 9D · ✅ 9A · ✅ 9F. |
| Open-core extensibility seam | ✅ | Backend plugin registry (`api/plugins.py`, `careerengine.plugins` entry points) + frontend feature flags (`frontend/src/lib/flags.ts`, `NEXT_PUBLIC_FEATURES`) + flagged `SidebarNav`. One-way dependency: core never imports the private layer. Zero plugins/flags in the OSS build. [ARCHITECTURE §17](ARCHITECTURE.md) (AD-17.1..4). Build the split when a private feature is real. |
| Phase 10 — Migrate to Next.js + FastAPI | ✅ done | ✅ 10.0 decision recorded ([ARCHITECTURE.md §16](ARCHITECTURE.md), PR #59); AD-16.8/16.9 client-data + toolchain (PR #62); **✅ 10.1 FastAPI skeleton + Firebase-bearer auth boundary (PR #63); ✅ 10.2 read APIs — dashboard/portfolio/jobs (PR #64); ✅ 10.3 write APIs — profile/experience/applications/preferences (PR #65); ✅ 10.4 grill API — record + SSE stream (PR #66)**. 10.5-10.7 are ✅ Ready build tickets in [GROOMING.md §Phase 10](GROOMING.md). API-first; building one slice per PR. **✅ 10.5 (Next.js App Router shell) MERGED (PR #67)** — foundational component inventory, TanStack Query data layer (optimistic write→rollback) over the 10.2/10.3 APIs, Firebase-bearer auth wiring + route guards, light/dark theme, Vitest/RTL/MSW unit+integration + Playwright login e2e, `make frontend-check` lane + CI job. Presentation/transport only, no contract change. **✅ Phase 10 COMPLETE (10.0–10.7b, PR #63–#72).** Streamlit gone; product runs on Next.js (App Router) + FastAPI, deployed as ONE container (static export served by FastAPI, AD-16.10). 10.7a = deploy artifact; 10.7b = Streamlit source removed (kept shared `web/` builders/stores + `web/async_runner`). **Next: stand up a `qa` env (new GCP project) → deploy → validate → promote to dev. Phase 11 not yet groomed.** |
| `qa` environment | ✅ done | Same-project 2nd Cloud Run service `career-engine-qa-app` (scale-to-zero, `min_instances=0`), reusing dev's Artifact Registry + `(default)` Firestore; `dev` untouched (Kaggle-visible). PR #74. Sign-in fixed in PR #75 (backend verifies Firebase JWTs via `google.oauth2.id_token.verify_firebase_token` — the OAuth2 tokeninfo endpoint rejects them). Deploy: `gh workflow run deploy.yml --ref master -f environment=qa`. Runbook: [QA_DEPLOY_RUNBOOK.md](QA_DEPLOY_RUNBOOK.md). |
| Feature parity (Next.js UI vs old Streamlit) | ✅ done | Every parity gap closed as its own gate-green slice. ✅ **P1** BYOK key management (PR #76) · ✅ **P2** Jobs "Find jobs" live discovery (PR #77) · ✅ **P3** résumé upload → vision-parse → seed the grill (PR #78) · ✅ **P4a** Dashboard first-run key card + Tailor "track as application" (PR #79) · ✅ **P4b** Portfolio entry actions — grill / pin / delete STAR story (PR #80) · ✅ **P4c** master résumé — `POST /api/master-resume`, deterministic so **no BYOK key** (PR #81) · ✅ **P5** Jobs "Not interested" (dismiss by company) + STAR bullet edit (PR #82). **All merged to `master` and deployed to qa** (run 29194226615; every new endpoint verified present in the served OpenAPI and still 401 without a bearer). Note: #81 was auto-closed when its stacked base branch was deleted on merge and was re-filed as **#83** — see the stacked-PR warning in [HANDOFF.md](HANDOFF.md). Every slice reuses an existing `web/` / `discovery/` / `auth/` seam — no new domain logic, no contract change (v2.8.0). |
| qa hardening (bugs found in live use) | 🟡 in progress | Bugs surfaced by real use of the qa deploy, each fixed with a regression test. ✅ **Profile / job-preferences never loaded back** (PR #84): the 10.3 writes shipped with NO read twins — the forms had nothing to hydrate from (a saved profile looked like it never persisted) AND, because the store does a full-document write, every save BLANKED the fields the form didn't post (email/phone/links; `nice_to_haves`). Adds `GET /api/profile` + `GET /api/preferences`; forms hydrate and merge. ✅ **Five more** (PR #85): grill resume (`GET /api/grill`, read-only, no model call), master résumé now carries the user's own bullets, résumé-parse progress indicator, dark-mode file input, **+ Add a bullet** (`POST /api/experience/{id}/bullet`). ✅ **Post-merge review of #85** (PR #86): #85's last two commits merged before Copilot re-reviewed and a follow-up review found the grill bug was NOT actually fixed — see the fixes in #86. ⬜ **Résumé merge/dedup** — a second résumé upload currently CLOBBERS the first (`create_session` is last-write-wins): every entry and STAR story is destroyed. Decision taken: merge + dedup on (title, org, dates), never destroy. ⬜ **Delete a bullet / an entry** (edit-only is half a tool). ⬜ **Copy quality — GROOMED** ([ARCHITECTURE §18](ARCHITECTURE.md) · [GROOMING §Copy quality](GROOMING.md)): a bullet is `story.result` verbatim — there is **no copywriting stage**, and S/T/A are discarded at render keeping only R. It is a missing stage (a prompt + node, **not** an agent). **CQ-1 bullet identity (`list[str]` → `list[Bullet]`, contract v2.9.0) is the prerequisite** for merge/dedup, delete AND the copywriter — sequence CQ-1 → CQ-2 merge → CQ-3 delete → CQ-4 copywriter-in-the-grill (human-validated ⇒ export needs no model call) → CQ-5 grill coverage → CQ-6 post-tailor/pre-render edit with a persist choice. |
| Live bug fixes | 🟡 in progress | ✅ BUG-1 workspace-save "Event loop is closed" + auth-redirect pin (PR #55) · ✅ BUG-2 grill banner missing on first question after resume (PR #56). Groomed in [GROOMING.md §Bugs](GROOMING.md). |

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

## Phase 8 — Operational hardening *(groomed; in progress)*

All tickets fully groomed in [GROOMING.md §Phase 8](GROOMING.md). Build them in order:

- ✅ **8A** Redeploy to dev — `gh workflow run deploy.yml --ref master -f environment=dev` dispatched
  (workflow run `28810378381`). Ships PRs #38–42 to Cloud Run; Jobs nav visible live after deploy.
- ✅ **8B** Dashboard "Find jobs" CTA — `DashboardView.can_find_jobs: bool = True`, `render_dashboard`
  emits "Find jobs" button routing to `session_state["view"] = "jobs"`, 2 named tests, Gemini PASS.
  PR #43 squash-merged; master @ `1d299cd`. **640 tests (1 skipped).**
- ✅ **8C** Wire the pending-action sweep — `career-engine sweep` CLI + `jobs/sweep_cli.py` core +
  `infrastructure/modules/cloud_run_job/` Terraform module + scheduler `token_type = "oauth2"` fix
  (Cloud Run Jobs Execute API requires OAuth2 access token, not OIDC JWT — would have been a silent
  runtime 401 without this fix). `InMemoryWorkspaceStore` added to `database/workspace_store.py` as
  production fallback. PR #44 squash-merged; master @ `73b909d`. **642 tests (1 skipped).**
- ✅ **8D** Multi-user model-client isolation — PR #45 squash-merged. Explicit DI via closure
  injection: 6 node functions gain `*, _client=None`; `build_runner(model_factory=None)` threads
  through; all 3 `_install_model_client` call sites replaced; 7 dead legacy module-level shims
  removed (Copilot review fix); 4 named isolation tests. 646 tests.
- ⬜ **8E** Deployer-SA least-privilege — narrow the deployer SA's GCP roles (Terraform-only; see
  [SECURITY.md](SECURITY.md) for the required-next-review list).
- ⬜ **8F** HITL TTL/override dashboard — a dedicated UI to list dismissed companies, allow un-dismissing,
  and optionally add TTL support to `InteractionLedger.rejected_companies`. Lower priority.

---

## Phase N — opportunistic value-adds (wanted; not v1-blocking)
- ⬜ Outcome learning, positive-reinforcement only — per user + per job type, learn what résumé format/wording correlated with reaching interview; transparent; opt-in anonymized global "what works" DB; reuses §8 async infra — [ARCHITECTURE.md §8.1](ARCHITECTURE.md)

## Backlog — post-v1 (NOT scheduled)
- ⬜ Interview preparedness (mock interviews from researched company+role question shapes) — [ARCHITECTURE.md §13](ARCHITECTURE.md)

## Phase 3 — Hardening & Eval  *(PR-based workflow: branch → Sonnet review → PR → Copilot review → squash-merge)*
- ✅ **`evaluation/user_simulator.py` + `test_config.json`** — merged via **PR #1** (squash, 389 tests). Deterministic simulator drives the REAL Runner: vague answers pushed back → specific yields validated metric StarStory; 5-turn brake fires (qc=5); records Pro-escalation rate (0 happy / >0 when REASONING_HIGH refused); `truncated` surfaces max_turns. `evaluation/` now in gates. Also landed the `wait-for-pr-review` skill. Sonnet PASS + Copilot addressed (both found the same 2 wait-skill must-fixes).
- ✅ **Security review** (key handling, IAM least-privilege, scraper/PDF injection) — merged via **PR #2** (squash, 398 tests). Fixed 2 exploitable findings: (1) HIGH — `FirebaseAuthProvider` never checked `aud`/`iss` (token substitution → cross-tenant impersonation); (2) MED–HIGH — `fetch_raw_html` SSRF (user-controlled URL → metadata/internal on Cloud Run). Added `docs/SECURITY.md` (threat model + review ledger + DNS-rebinding residual). Sonnet PASS (0 must-fix) + all 5 Copilot comments addressed. Confirmed NOT vulnerable: dev-hatch is CLI-only, PDF render autoescaped, keys use issuer-controlled `sub`.
- ✅ **Monitoring/logging** for graph hangs (observability) — merged via **PR #3** (squash, 405 tests). Added `workflows/observability.py` (`configure_logging` idempotent + `CE_LOG_LEVEL`; `log_operation` span: times, WARNs past `slow_ms`, logs+re-raises on error, monotonic clock). `_get_model_client()` now wraps in `_MonitoredModelClient` (times every `model.generate`); real client gets a per-request `HttpOptions` timeout from new `settings.model_timeout_seconds` (default 60s) so a network stall fails fast. `_run_turn` wrapped in a `graph.turn` span (in-memory ordinal, no extra state read). Wired into CLI + Streamlit entrypoints.
- ✅ **CoT tuning**; measure & reduce Pro-escalation rate — merged via **PR #4** (squash, 409 tests, **contract v2.3.0**, tag `contract-v2.3.0`). Implemented the **Free-Mode Pro-escalation gate**: `execute_grill_turn_node` emits typed `UpgradeRequired` once an entry hits `_MAX_FLASH_GRILL_ATTEMPTS` (=6) failed metric extractions (tracked in additive `CareerEngineState.grill_attempts`, reset on a validated metric); threshold sits above the 5-turn checkpoint so the brake fires first; BYOK never escalates. Tuned CoT prompts (accept digit-bearing approximate metrics; scaffold stuck users) to keep the rate low. Eval `persistent_vague` now escalates after the checkpoint. Sonnet PASS (1 nit) + 2 Copilot comments addressed. ARCHITECTURE §6.3 specifies the gate.

- ✅ **Phase 2 deferred wiring** — merged via **PR #5** (squash, 423 tests). (a) `web/session_loader.py` best-effort loads the user's latest discovery `CareerEngineState` for the progress meter (flat-state read matching `read_state`; applies today's date so the meter is a "now" view; empty on any failure), wired into `streamlit_app`. (b) `jobs/sweep_endpoint.py` — framework-agnostic `handle_sweep_request` verifying the Cloud Scheduler OIDC token (aud pinned to the service URL secure-by-default + iss + optional invoker-SA allowlist) then running `run_sweep`. (c) `terraform` feature added to `.devcontainer` (rebuild to take effect). Sonnet CHANGES-REQUESTED (1 false positive verified + 2 real must-fix) + 2 Copilot comments addressed.
- ✅ **Capstone runbook dry-run** — executed end-to-end via **PR #6** (424 tests). Deterministic evidence all green (`make check`, real-Runner→`%PDF` e2e, sweep, `tf-check`, no hardcoded model IDs). The **live** dry-run found + fixed a real bug: the Gemini model returns JSON `null` for STAR fields while `metrics_found=true`, crashing `StarStory` via `get(k, "")` → coerced with `get(k) or ""` + regression test. Documented the free-tier 5-req/min ceiling (a full live PDF needs a paid key; the deterministic e2e test is the reproducible PDF proof). Runbook drift reconciled (381→424, deferred-scope, terraform-in-devcontainer).

**Phase 3 queue COMPLETE** (all 5 items merged, PRs #2–#6). See [HANDOFF.md](HANDOFF.md) for what's next.

## Post-queue hardening (from real usage)
- ✅ **Repo public-ready** — root README + GitHub Actions CI/CD (PR #7) + proprietary LICENSE; real Dockerfile + Cloud Build, CI builds & smoke-tests the image (PR #8).
- ✅ **Grill hardening** — merged via **PR #9** (tag `contract-v2.4.0`, 434 tests) — three fixes surfaced by a live résumé run: (A) graceful `ModelAPIError` handling (quota/`429` → friendly resumable message, no crash); (B) `grill_answers` per-entry memory (extraction sees all answers; follow-up never re-asks); (C) frontier prioritization (current/substantive roles first via `end_date` present-first + experience-type weight). ARCHITECTURE §6.3.1.

---

## Decisions log (append-only)
- 2026-07-05 — **Tailor follow-ups shipped.** (PR #27) multi-format export: `web/exporter.py` renders
  the tailored résumé to **PDF** (WeasyPrint + autoescaped module-level template) and **DOCX**
  (`python-docx==1.2.0`); Tailor view offers PDF/Word/Markdown/JSON (rendered once per result). (PR #28)
  **JD-by-URL**: Tailor accepts a job-posting URL, scraped via the SSRF-guarded `scrape_job_description`
  (falls back to pasted text). No contract change (500 tests).
- 2026-07-04 — **Web Tailor shipped** (PR #26). In-app JD → tailored résumé: `web/tailor.py`
  reuses `finalize_master_resume_node` → `tailor_node` (assembles a master from current validated
  stories if the grill isn't finalized; never marks the session COMPLETE, so tailoring is never
  blocked), + pure `parse_tailored`/`tailored_to_markdown`. Streamlit view shows summary + selected
  achievements + Markdown/JSON download. Markdown export is the first slice of the multi-format
  exporter. Follow-ups: PDF/DOCX export, JD-by-URL scrape, save-as-tracked-application. No contract
  change (495 tests).
- 2026-07-04 — **Grill quality pass** (PR #24): web grill runs on **Pro** on the user's BYOK key
  (`ACCESS_MODE=BYOK` env + `DiscoverySession access_mode=BYOK`); **Skip this experience** control;
  education entries auto-summarized on resume (heals old sessions); entry-aware fallback question;
  "Grill me about this" jump now runs a turn. Plus the `ship-change` + reuse of `wait-for-pr-review`
  dev skills; process doc updated (Opus builds → Sonnet reviews → PR → Copilot reviews → merge → deploy).
- 2026-07-04 — **Durable web sessions fix (data-loss root cause).** A user's grilling from days
  earlier wasn't reappearing. Two coupled bugs: (1) the web grill used `InMemorySessionService`
  (in-process RAM) — nothing reached Firestore, and Cloud Run `min_instances=0` + redeploys wiped it;
  (2) `FirestoreSessionService` never overrode `append_event`, so even Firestore-backed sessions
  persisted ONLY `create_session`'s state and silently dropped every turn's `state_delta` on re-read.
  Fix: override `FirestoreSessionService.append_event` to write post-event state to Firestore
  (regression test proves it fails without the write); wire the web grill to `FirestoreSessionService`
  under a **stable per-user session id** (`web.session_loader.web_session_id`, app_name aligned with the
  readers) with **resume-on-load**; and point the portfolio-mutation seam at that same canonical id so
  grill + Portfolio + add-experience share ONE resumable session. No contract change (469 tests). The
  older in-memory data is unrecoverable (never persisted); going forward grilling is durable + resumes.
- 2026-07-04 — **Phase 4 (4A–4D) SHIPPED & deployed** (PRs #15/#16/#17, 467 tests, no contract
  change). 4A sidebar nav (`web/navigation.py`); 4B read-only Portfolio view (`web/portfolio.py` —
  experience tree + per-entry StarStories via `stories_by_entry`); 4C+4D portfolio-mutation seam
  (`web/portfolio_store.py`) — `add_manual_entry` (source="manual" entries; long-tenure breadth fix)
  + `set_grill_frontier` (jump the grill to a chosen entry). All Copilot-reviewed (4B: render bullets +
  empty-entry_id test; 4C/4D: cache the session service via `st.cache_resource`). 4E (highlight/pin)
  remains deferred behind an additive minor bump.
- 2026-07-04 — **D10 — Phase 4 "Portfolio Workbench" scoped & groomed.** Make the persisted portfolio
  visible/navigable/steerable in the web app: 4A sidebar nav (repurpose the empty left panel), 4B
  read-only Portfolio view (experience tree + per-entry recorded StarStories), 4C steerable grill (pin
  `grill_frontier` to a chosen `entry_id`), 4D add-experience manually via a tested portfolio-mutation
  seam (long-tenure breadth fix). **Key finding:** the persisted `CareerEngineState` already holds all
  the data (`work_timeline`, `entry_id`-linked stories, jumpable frontier, `source="manual"`) → 4A–4D
  need **no contract change**. Only deferred 4E (`Entry.highlighted`) bumps the contract (additive minor).
  Spec: [ARCHITECTURE.md §14](ARCHITECTURE.md); builds: [GROOMING.md](GROOMING.md) Phase 4.
- 2026-07-04 — Live-app fixes (PR #14, deployed): async Firestore client (`get_firestore_async_client`)
  for the workspace/session stores (the sync client failed on `await` → "couldn't reach your saved
  workspace"); reverted Cloud Run `concurrency=1` to the module default (it starved Streamlit's asset/
  websocket loads → "Rate exceeded" / "Failed to fetch module"). Single-user isolation now rests on
  `max_instances=1` + the (tracked) session-isolation work, not concurrency=1.
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
