# CareerEngine — Session Handoff / Resume Point

## 👉 YOU ARE HERE (updated 2026-07-07 — Phase 10 groomed: PR #59 merged; 5-PR cycle complete)
**`master` clean @ `db15e3c` · contract v2.8.0 · 703 tests (1 skipped) · all PRs merged.**
**Phases 1–7 + 8A + 8B + 8C + 8D + 8G + all of Phase 9 (9A/9B/9C/9D/9E/9F/9G/9I/9J/9K) + BUG-1 + BUG-2 COMPLETE. Phase 10 is groomed (build not started).**

**▶ NEXT — Phase 10 build, slice 10.1 (FastAPI skeleton + auth boundary)**

The Streamlit→Next.js+FastAPI decision is recorded in [ARCHITECTURE.md §16](ARCHITECTURE.md)
(AD-16.1..7: FastAPI over the unchanged domain, `schema.py` as wire contract, auth at the API
boundary, SSE grill, Cloud Run). Executable **API-first** build tickets 10.1–10.7 are ✅ Ready in
[GROOMING.md §Phase 10](GROOMING.md); sequencing in [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md).
Build one slice per PR, in order. **10.1 has a PAUSE point:** pick the auth shape (OIDC-at-FastAPI
session cookie vs Firebase ID-token bearer) and confirm against `auth/` before wiring protected routes.

**What shipped this session (5-PR cycle: 2 bug fixes + Phase 9 completion + Phase 10 groom):**

- **PR5 — Phase 10 groom (PR #59, docs-only):** recorded the web-platform migration decision in
  ARCHITECTURE §16 (the tech recommendation writeup), added Phase 10 to the plan roadmap, and rebuilt
  GROOMING §Phase 10 into ✅ Ready API-first build tickets 10.1–10.7. Copilot review: clean (no
  comments). No code / contract change.
- **9F (PR #58):** Jobs — preference-form guidance + `derive_initial_roles` portfolio-seeded defaults.
- **9A (PR #57):** Portfolio — delete STAR stories + edit résumé bullets (empty edit = no-op).
- **BUG-2 (PR #56):** Grill "currently grilling" banner missing on first question after resume.
- **BUG-1 (PR #55):** Workspace saves failing with "event loop is closed" + auth redirect-URI hotfix.

- **BUG-1 (PR #55):** Workspace saves failed with "Event loop is closed" (profile save +
  track-application). `FirestoreWorkspaceStore` reused one `AsyncClient` across two `asyncio.run()`
  calls; the gRPC channel bound to the first (closed) loop. Fixed via per-call `_acquire()`
  `@asynccontextmanager` creating a fresh client per async op (injected client never closed; factory
  client closed in `finally`, awaiting `close()` if awaitable). Ctor enforces client/client_factory
  mutual exclusivity. Also pinned `CE_AUTH_REDIRECT_URI` to `/oauth2callback` in deploy.yml + main.tf.
- **BUG-2 (PR #56):** Grill "📌 Currently grilling" banner missing on the **first question after
  resume**. On resume, `_migrate_education_on_resume` blanks `grill_frontier` when the pinned entry
  is no longer grillable; `_try_resume` derived the label straight from `grill_frontier` → empty
  banner until the next turn re-pinned. Fixed with `_effective_frontier_label(state)` = frontier
  label, else the label of the entry the grill node will pick next (`workflows.nodes._get_frontier_entry`,
  imported function-locally). Extracted `_entry_label` helper; 6 tests. No contract change.
  Note: the original groomed diagnosis (jump/advance clears the frontier) was refuted by reproduction
  and re-groomed in GROOMING.md.

**What shipped earlier (Phase 9 batch 2):**

- **9I (PR #48):** Tailor — optional Specific instructions textarea. Instructions placed in **user prompt** (not system) to prevent prompt injection. `_instructions` kwarg on `tailor_node` + `tailor_structured_resume`; threaded through `build_discovery_workflow`/`build_runner`. Help text says "not persisted to your profile".
- **9G (PR #51):** Track application — auto-extract title + company from JD via `web/jd_utils.py`. Null-safe with `_safe_str()`, markdown-fence stripping, `ModelAPIError` propagates, `UpgradeRequired.user_message` surfaced, form stays visible after API error.
- **9C (PR #52):** Portfolio — editable Profile section. `ProfileView` + `build_profile_view()` + `render_profile_section()` (expander, 2-col, links CRUD, Save). Load failure disables save (data-loss prevention). `ContractVersionError` re-raised in both load and save paths.
- **9E (PR #53):** Jobs — sort for-review and accepted lists by `ai_rationale` length descending (both fresh-result and prior/initial-entry paths). Lists wrapped in `st.container(height=420)`.
- **9D (PR #54):** Professional résumé template — `templates/classic_resume.html` rewritten with Inter/system-ui, A4 @page, Experience bullets, Skills pills, Education section. PDF test exercises the template directly via WeasyPrint.

**What shipped earlier (batch 1):**
- **9J (PR #47):** Checkpoint info copy in Grill view.
- **9B (PR #49):** Add-experience CTA moved before entry list.
- **9K (PR #50):** Per-entry STAR story progress indicator.

**Remaining Phase 9 tickets:** none — Phase 9 complete.

---
*Historical session notes follow (most recent first):*

**Latest this session:**
- **DURABLE WEB SESSIONS (data-loss root cause fixed):** the web grill was on `InMemorySessionService`
  (RAM only) AND `FirestoreSessionService` never persisted per-turn `append_event` deltas → grilling was
  never durable. Fixed: `append_event` override persists each turn; grill now uses `FirestoreSessionService`
  under a stable per-user id (`web_session_id`) with resume-on-load; portfolio seam shares that canonical
  id. No contract change (469 tests; regression test proves the persist). Older in-memory data is
  unrecoverable (was never written); new grilling persists + resumes. (PR pending — see below.)
- **Live bugs fixed & deployed (PR #14):** async Firestore client (`get_firestore_async_client`) →
  fixes "Couldn't reach your saved workspace"; reverted Cloud Run `concurrency=1` → fixes "Rate
  exceeded"/"Failed to fetch module".
- **Phase 4 "Portfolio Workbench" SHIPPED & deployed (PRs #15/#16/#17, 467 tests, no contract change):**
  - **4A** sidebar nav (`web/navigation.py`) — the empty left panel is now Dashboard/Portfolio/Grill/

---
*Historical session notes follow (most recent first):*

**Latest this session:**
- **DURABLE WEB SESSIONS (data-loss root cause fixed):** the web grill was on `InMemorySessionService`
  (RAM only) AND `FirestoreSessionService` never persisted per-turn `append_event` deltas → grilling was
  never durable. Fixed: `append_event` override persists each turn; grill now uses `FirestoreSessionService`
  under a stable per-user id (`web_session_id`) with resume-on-load; portfolio seam shares that canonical
  id. No contract change (469 tests; regression test proves the persist). Older in-memory data is
  unrecoverable (was never written); new grilling persists + resumes. (PR pending — see below.)
- **Live bugs fixed & deployed (PR #14):** async Firestore client (`get_firestore_async_client`) →
  fixes "Couldn't reach your saved workspace"; reverted Cloud Run `concurrency=1` → fixes "Rate
  exceeded"/"Failed to fetch module".
- **Phase 4 "Portfolio Workbench" SHIPPED & deployed (PRs #15/#16/#17, 467 tests, no contract change):**
  - **4A** sidebar nav (`web/navigation.py`) — the empty left panel is now Dashboard/Portfolio/Grill/
    Tailor nav + a compact applications list.
  - **4B** Portfolio view (`web/portfolio.py`) — read what's recorded per experience: the experience
    tree + each entry's STAR stories (`stories_by_entry`), status, and bullets.
  - **4C+4D** portfolio-mutation seam (`web/portfolio_store.py`) — **add a remembered experience/project**
    (`add_manual_entry`, the long-tenure breadth fix) and **"Grill me about this"** to steer the grill onto
    a chosen entry (`set_grill_frontier`; jumpable frontier honored by the router).
  - Spec [ARCHITECTURE.md §14](ARCHITECTURE.md); grooming [GROOMING.md](GROOMING.md) Phase 4; D10.

**▶ NEXT ACTION:** await user re-test of the grill on a FRESH session (Restart) — the checkpoint loop
could not be reproduced in isolation (regression test PR #25 proves confirm resolves over Firestore);
likely was redeploy-churn wedging + the empty-question issue, both fixed. Then continue the **multi-format
résumé exporter**: Markdown ships with Tailor (PR #26); **PDF** (make the renderer consume the tailored
JSON, not just stories) and **DOCX** (`python-docx`) are next; plus **JD-by-URL** (scraper) and
**save-as-tracked-application** for the Tailor flow. Other candidates: **4E** highlight/pin (needs an
additive-minor contract bump); pre-GA **/security-review**; custom domain.

**Web app now covers:** login → Grill (durable, Pro on BYOK, Skip, resume) → Portfolio (view/add/steer) →
**Tailor** (paste JD **or job-posting URL** → tailored résumé → **PDF / Word / Markdown / JSON** export) →
dashboard/meter. Ship changes with the [`ship-change`](../skills/ship-change/SKILL.md) skill.

**Phase 5 in progress.** **5A DONE & deployed** (PR #29): the tailored output is now a **real ATS-safe
résumé** — contact header · JD-aligned skills · **experience grouped by role** (via `StarStory.entry_id`
→ `Entry`) · education, downloadable as PDF/DOCX/MD, with the internal "why it fits" removed. Built in
`web/resume_builder.py` (deterministic assembly + one model call for selection/summary/skills) +
`web/resume_render.py`; the flat `web/tailor.py`/`web/exporter.py` were removed.
**▶ ACTIVE (branch `feat/discovery-a2a`) — CAPSTONE DELIVERABLE, due 2026-07-06 11:59pm PT.**
Pivot to a **two-agent (A2A) job-discovery** feature for the Kaggle capstone (concepts: Multi-agent · MCP ·
Agent skills · Security/HITL · Deployability · Antigravity). Design = the definitive spec (this session's
long "Multi-Agent Async Architecture Spec" message), **marrying Gemini's eval concepts with best-practice
SaaS** (my judgment is the guide; structured contracts over prose; reuse existing models).
**Deliverable cut (today; rest = roadmap):** stateful **Primary** (Groomer/Tailor, Pro) ⇄ stateless
**Scout** (Fetcher, Flash) **in-process** with the typed `EvaluationDiff` contract; real **MCP server**
(separate process, live no-key source e.g. Remotive/HN-Algolia) exposing `search_jobs`+`fetch_jd`;
**bounded loop MAX_ITERATIONS=3**; deterministic ledger HARD_REJECT + agentic eval → `match_status`+
`ai_rationale`; commit ACCEPTED/SOFT_REJECT to Firestore (idempotent `job_id`); **CLI `career-engine
discover`** demo; **on-demand Tailor reuses the deployed tailor**. Roadmap: async worker+spin-down, network
A2A, Podman sandbox, full HITL dashboard (TTL/override), multi-user.
**DONE this session:** contract **v2.5.0** ontology committed on the branch — `JobOpportunity`,
`EvaluationDiff`, `ScoutDirective`, `SessionPreferences`, `InteractionLedger`, enums, `make_job_id()` +
tests (`tests/test_discovery_schema.py`), 509 green.
**EVAL CRITERIA (user's real prefs — use as default `SessionPreferences` + Primary test fixture; later a UI
form per customer):** target_roles = Fractional Technology Leadership / consulting / highly-autonomous
Principal-level eng (e.g. via BitCrafty Inc.). nice_to_haves (soft) = AWS infra (SAP-C02-level), multi-agent
AI orchestration (ADK/LangGraph/MCP), containerized sandboxing (Podman/Linux), agile-startup / autonomous-
pipeline teams. dealbreakers (HARD_REJECT) = traditional W2 middle-management; deeply bureaucratic
enterprise; rigid 100% on-site; pure maintenance-only roles. (Plus already-applied from the ledger.)
**Package naming decision:** the whole two-agent feature lives under **one package `discovery/`** (not the
literal `mcp/` + `agents/` paths sketched earlier) — a top-level `mcp/` dir would **shadow the installed
`mcp` SDK** on `sys.path`. So: `discovery/job_source.py`, `discovery/mcp_server.py`, `discovery/scout.py`,
`discovery/primary.py`.
**NEXT build order:**
- ✅ **(1) MCP server DONE** — `discovery/mcp_server.py` (real FastMCP, stdio, `python -m discovery.mcp_server`)
  exposes `search_jobs` + `fetch_jd`; logic in `discovery/job_source.py` (pure/injectable, **live key-free
  Remotive source**, SSRF-guarded via the scraper's `_assert_safe_url`, normalises → `JobOpportunity` with
  `make_job_id`). Tests `tests/test_job_source.py` + `tests/test_mcp_server.py`; `mcp==1.28.1` pinned;
  `discovery/` added to Makefile gates. **523 green**, live smoke fetched real jobs. (branch, uncommitted→commit next)
- ✅ **(2) Scout DONE** — `discovery/scout.py`: stateless Fetcher; accesses data **only** through the MCP
  tool surface (`JobToolClient`), never importing `job_source`. `InProcessMcpClient` dispatches through the
  real FastMCP machinery (`mcp.call_tool`) — a genuine MCP client interaction, key-free + subprocess-free for
  tests/demo (stdio subprocess transport = roadmap). Tests `tests/test_scout.py`.
- ✅ **(3) Primary + bounded loop DONE** — `discovery/primary.py`: stateful Evaluator/Orchestrator.
  Deterministic `hard_reject_reason` gate (ledger already-applied / rejected company / dealbreaker keyword →
  drop, no model). Injectable `BatchEvaluator`: key-free `HeuristicEvaluator` (default, demoable) vs agentic
  `ModelEvaluator` (REASONING_HIGH→Pro on BYOK, one batch call, JSON-parsed, **falls back to heuristic on any
  parse/API error**). Pure `evaluate_batch(...) → EvaluationDiff` (stamps `match_status`+`ai_rationale`,
  computes `next_directive`). `PrimaryAgent.discover()` = MAX_ITERATIONS=3 loop, dedupes by `job_id`,
  refines directive (excludes missed companies), stops at `desired_total` or the cap. Tests
  `tests/test_primary.py`. **551 green.**
- ✅ **(4) CLI `discover` DONE** — `career-engine discover [--count N --max-iterations M --firestore]`
  (`main.py` thin cmd → `discovery/cli.py`). `run_discover` (testable, offline) runs a pre-wired Primary,
  prints ACCEPTED/FOR-REVIEW with rationale, persists accepted via a `LedgerStore`; `discover_command`
  (IO seam) resolves auth, hydrates the ledger, wires Scout+ModelEvaluator. `discovery/store.py`:
  `InMemoryLedgerStore` (default) + sync `FirestoreLedgerStore` (`discovered_jobs/{uid}/jobs/{job_id}`,
  idempotent, no secrets). `discovery/preferences.py`: `default_session_preferences()` = the operator's
  real EVAL CRITERIA. Tests `tests/test_ledger_store.py` + `tests/test_discovery_loop_cli.py`. **557 green;
  LIVE end-to-end run against real Remotive succeeded** (3 iters, ranked output, idempotent persist).
- ✅ **(5) Tailor reuse DONE** — `discover --tailor-session <SID> [-o pdf]` closes the loop: the top ACCEPTED
  job's cleaned `raw_description` is fed straight into the existing/deployed `run_tailor_command` (no new
  résumé code). `select_top_match(result)` picks the first strong match; without the flag, discover prints a
  ready-to-run `career-engine tailor …` hint. Tests added. **559 green.**

**▶ ALL 5 BUILD STEPS DONE.** The demoable slice is complete: `career-engine discover` runs the live
two-agent A2A loop (Scout ⇄ MCP ⇄ Primary) → ranked matches + rationale → idempotent persist → optional
Tailor. Safety-net floor (deployed grill→tailor) untouched.

**▶▶ MERGED (2026-07-05): PR #30 squash-merged to `master`, tagged `contract-v2.5.0`, branch deleted.**
Both review gates cleared — **Sonnet PASS** (independently re-ran `make check`; 0 must-fix) + **Copilot**
(3 comments; fixed the real id-collision bug + doc timestamp, deferred Firestore `get_all()` batching with
rationale). Fixes folded in: skip id-less postings, catch `ScraperError` in `discover`, simplify
`APPROVE_BATCH`. **master is green (560 tests), tree CLEAN.** The two-agent A2A discovery feature is DONE.

**RESUME NEXT SESSION — remaining before submission (due 2026-07-06 11:59pm PT):**
1. **PACKAGING** (user-owned): video + writeup + README + architecture diagram. User is running NotebookLM
   on the docs to draft script/diagram/writeup/README — **review those drafts against the code so nothing
   overclaims.** Best NotebookLM source set: `docs/ARCHITECTURE.md` §15, `docs/DISCOVERY_DEMO.md` (verified
   demo commands to record), this file, and the merged PR #30.
2. **Record the demo** from `docs/DISCOVERY_DEMO.md` (CLI, terminal capture — no deploy needed). For
   real-reasoning rationales, export a BYOK `DEV_GEMINI_KEY` in the shell (never in code/chat).
3. Optional: a README "Job Discovery" section (20-pt docs score).
**Deploy is NOT required** (discover is a CLI demo; the deployed web grill→tailor floor is unaffected).
**Deferred roadmap (not blocking):** network/stdio A2A, Podman sandbox, async worker + spin-down, full HITL
dashboard (TTL/override), multi-user session isolation, Firestore `get_all()` batching. (See ARCHITECTURE §15.5.)
**PACKAGING (protected, own session Mon eve):** 5-min video, writeup, README + architecture diagram (~40+
pts; can be drafted in parallel by a designer/communicator). **Rule: nothing risky Monday; capture demo
footage EOD Sunday.**
**Deferred (pre-capstone Phase 5):** persist Contact (+minor); 5B save-as-application; 5C one renderer;
4E highlight; pre-GA /security-review; grill re-test (checkpoint loop unreproducible, PR #25).

- **Live dev URL:** https://career-engine-dev-app-ontyg6kaja-uc.a.run.app. Project `gen-lang-client-0513394764`, region us-central1.
- **CI/CD (works):** `gh workflow run deploy.yml --ref master -f environment=dev` → keyless WIF → docker build+push → `terraform apply`. State in GCS bucket `gen-lang-client-0513394764-tfstate` (prefix `envs/dev`). Repo *variables* drive it (GCP_PROJECT_ID/WIF_PROVIDER/DEPLOY_SA/TF_STATE_BUCKET/AR_LOCATION/CE_AUTH_*).
- **What shipped (PR #11 + follow-ups):** Streamlit OIDC login (`st.login`); `web/grill_ui.py` interactive grill (start→Q&A→checkpoint→finalize→PDF); BYOK key set-once in Secret Manager (revoke/replace); Terraform auth wiring + scoped `ce-key-*` IAM + `datastore.user`; single-user isolation (`max_instances=1`, concurrency=1); `docker-entrypoint.sh` writes secrets.toml (json-escaped) from env.
- **Bootstrap done out-of-band (one-time, NOT in main state):** billing link, OAuth client (Console), `cloudresourcemanager` + `serviceusage` + others enabled, WIF pool/provider `github-pool`/`github-provider` (repo-conditioned), deployer SA `career-engine-deployer`, GCS state bucket. Secret VALUES (`ce-auth-client-secret`, `ce-auth-cookie-secret`, `ce-key-*`) set out-of-band, never in state.
- **REQUIRED before GA:** a `/security-review` of web login + paid-key storage + broad deployer-SA roles (see [SECURITY.md](SECURITY.md) "Required next review").
- **Remaining follow-ups:** (a) web PDF upload (`st.file_uploader`→`parse_resume`) — the résumé starting point; (b) custom domain `career-engine.bitcrafty.cloud` (hyphenated) via Cloudflare + update OAuth redirect + `CE_AUTH_REDIRECT_URI`; (c) sweep endpoint HTTP adapter (deferred; scheduler 404s until then); (d) curate deployer-SA roles down.
- **Deadline:** Kaggle × Google submission **2026-07-06**.
- **Grill hardening (feat/grill-hardening, contract v2.4.0):** from the user's real run — (A) graceful `ModelAPIError` handling so a `429`/quota shows a friendly resumable message, not a crash; (B) `grill_answers` per-entry memory (accumulated extraction + no re-asking); (C) frontier ranks current/substantive roles first (`end_date` present-first + experience-type weight). See ARCHITECTURE §6.3.1.
- **Deadline:** Kaggle × Google submission **2026-07-06** — product + writeup + video.
- **Known live-run constraint:** the Gemini **free tier is 5 req/min + 20/day**; a full live session needs a paid/raised-quota key (deterministic tests prove the pipeline without one).
- **Workflow (Copilot budget reset):** each chunk = **new branch → build → `make check` green → Sonnet
  review (subagent) + fix → push → `gh pr create` → request Copilot (`gh api --method POST
  repos/{owner}/{repo}/pulls/N/requested_reviewers -f 'reviewers[]=copilot-pull-request-reviewer[bot]'`,
  reviewer surfaces as login `Copilot`) → wait via `skills/wait-for-pr-review` → read comments
  (`gh api repos/{owner}/{repo}/pulls/N/comments`) → address → squash-merge (`gh pr merge N --squash
  --delete-branch`)**. `gh` authed as `suchakra`; jq + terraform + gh all present.
- **ORDERED QUEUE (one PR each, in order):**
  1. **Security review** ✅ DONE — merged via **PR #2** (squash, 398 tests). Fixed HIGH auth
     `aud`/`iss` gap + MED–HIGH scraper SSRF; added [SECURITY.md](SECURITY.md). Sonnet PASS +
     Copilot addressed.
  2. **Monitoring/logging** for graph hangs ✅ DONE — merged via **PR #3** (405 tests):
     `workflows/observability.py` + monitored model client + per-request model timeout
     (`settings.model_timeout_seconds`) + `graph.turn` span.
  3. **CoT tuning** ✅ DONE — merged via **PR #4** (409 tests, **contract v2.3.0**, tag
     `contract-v2.3.0`): Free-Mode Pro-escalation gate in `execute_grill_turn_node` (per-entry
     `grill_attempts`, escalates after 6 failed attempts, above the checkpoint boundary) + CoT tuning.
  4. **Phase 2 deferred wiring** ✅ DONE — merged via **PR #5** (423 tests): `web/session_loader.py`
     (meter discovery-state load, wired into `streamlit_app`); `jobs/sweep_endpoint.py` (OIDC
     aud/iss-verified sweep handler); `terraform` in `.devcontainer` (rebuild to take effect).
  5. **Capstone dry-run** ✅ DONE — merged via **PR #6** (424 tests). Executed end-to-end; the live
     run found + fixed a real null-STAR-field crash; free-tier 5-req/min ceiling documented (live PDF
     needs a paid key). Evidence captured in [CAPSTONE_RUNBOOK.md](CAPSTONE_RUNBOOK.md).
- **Infra/repo hygiene DONE (PR #7):** root [README.md](../README.md); CI (`.github/workflows/ci.yml`
  — `make check` + `make tf-check` on push/PR, credential-free, green on GitHub) + manual WIF deploy
  (`.github/workflows/deploy.yml`); proprietary [LICENSE](../LICENSE). Fixed a build portability bug
  the local env masked (bogus setuptools backend → `setuptools.build_meta` + explicit packages).
  `.env`/`*.tfvars` git-ignored — safe to make the repo public.
- **Deploy image DONE (PR #8):** `Dockerfile` (Streamlit on `$PORT`, non-root, WeasyPrint libs),
  `.dockerignore` (no secrets), `cloudbuild.yaml`, `make build`/`make cloud-build`; CI builds +
  smoke-tests the image. Deploy path is now complete end-to-end except live GCP creds.
- **What's next (queue exhausted):** no scheduled work remains. Candidate follow-ups (unscheduled) —
  **GCP live setup** (create the WIF pool/provider + repo secrets, `gcloud builds submit` an image,
  `make deploy`, run the `deploy.yml` dispatch); the outermost Phase-2 glue (mount
  `jobs/sweep_endpoint.py` in a served app + Identity Platform *frontend* token exchange); a
  **dev-only web view** so the Streamlit dashboard is demoable locally without an IdP token; a live
  PDF pass with a paid/raised-quota key. Await direction before starting.
- **State:** tags `contract-v1.0.0…v2.2.0`; gates `make check` (389) + `make tf-check`. Phase 2 deferred
  thin wiring (item 4 above) is logic-built+tested, only outer glue remains.
Phase 1.7 DONE (tagged `contract-v2.1.0`, pushed). Phase 2 increment built this session, Opus-direct
(unpushed):
  - **2C** Terraform infra (`infrastructure/` modules + dev/prod + README + Makefile `tf-check`/`deploy`/`destroy`).
    `fmt`+`validate` green BOTH envs; `plan`/`apply` need GCP creds (operator step).
  - **contract v2.2.0** (additive): `UserWorkspace` (per-user portfolio doc) + `Application`/`ApplicationStatus`
    + `PendingAction`. Decided: a NEW UserWorkspace model (not fields on CareerEngineState).
  - **2D** `jobs/pending_action_sweep.py` — pure+idempotent 14-day sweep + `WorkspaceStore` orchestration.
  - **2A** `web/` Streamlit dashboard — pure view-model + injectable renderer (testable sans Streamlit);
    `career-engine web` launches it. Tailoring never gated.
- **terraform was installed ad-hoc in the devcontainer — see memory: add it as a devcontainer dependency.**
- **NEXT:** Copilot-gate the Phase-2 diff (`4f240ac..HEAD`) → tag `contract-v2.2.0` → push. Then:
  **2B** (web auth/Identity Platform), the **Firestore `UserWorkspace` repository** (real `WorkspaceStore`
  backing 2D + 2A; + streamlit auth/session load), **2E** (capstone runbook + evidence, `skills/cloud_ops/SKILL.md`).
- **Deferred wiring (not yet built):** `UserWorkspace` Firestore load/save; streamlit auth + state load
  (currently renders empty workspace). Both are thin adapters over tested logic.
Phase 0 + Phase 1 + Phase 1.3 + Phase 1.5 + **all of Phase 1.7** are built (**339 tests**; `make check`
green). Sonnet review verdict **PASS** (0 must-fix; 4 nits applied incl. a discovery-turn empty-question
fallback). Phase 1.7 closed the deferred Phase-1/1.5 integration seams, all Opus-built this session +
Sonnet-reviewed (Copilot gate planned):
  - **1.7-A** resume-file upload wired into `grill` (`--resume-file`).
  - **1.7-B** true session resume (`get_session_state_if_exists`, load-before-create).
  - **1.7-C** `discovery_turn_node` wired into the main graph + router branch — contract bumped
    **v2.0.0 → v2.1.0** (additive `coverage_confirmed`; user-approved).
  - **1.7-D** FakeFirestore doubles moved to `tests/fakes.py`.
- **Pushed:** the full 1.7 series + reviews + tag `contract-v2.1.0` are on origin/master. Tree clean.
- **NEXT:** **Phase 2** (web/infra/async) per [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md).
- **Carried into Phase 2 polish** (non-blocking): the scripted end-to-end capstone runbook (resume-file →
  discovery → resume → tailor), plus Copilot's 3 optional 1.7 nits in [REVIEW.md](REVIEW.md) —
  (1) friendlier message for extensionless resume files, (2) a `coverage_through` schema docstring note
  that only `ingest_node` writes it, (3) make the resume-CLI test resilient to a `resolve_auth_and_client` rename.
- **To IDEATE:** read this file, then [ARCHITECTURE.md](ARCHITECTURE.md) + [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md); capture new ideas back into the docs (don't mutate a spec that's mid-build — version-gate instead).

---

> Purpose: pick up cleanly after a session reset. Written 2026-06-29.
> Companion to [PROGRESS.md](PROGRESS.md) (live status), [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)
> (roadmap), [AGENT_EXECUTION_PROMPT.md](AGENT_EXECUTION_PROMPT.md) (builder/reviewer prompts).

## Where we are
- **Branch `master`** — origin behind by the Phase-1.7 series + docs, awaiting Copilot review + push.
- **Contract: v2.1.0** (tags `contract-v1.0.0`, `contract-v1.1.0`, `contract-v2.0.0`; **`contract-v2.1.0`
  to be tagged after review**). v2.1.0 adds `coverage_confirmed` (additive, backward-compatible).
  Changing `schema.py`/`config.py`/public interfaces requires a `CONTRACT_VERSION` bump.
- **Phase 0:** ✅ frozen. **Phase 1 (WS-A/B/C/D + integration):** ✅ COMPLETE. **Phase 1.3:** ✅ done.
  **Phase 1.5:** ✅ COMPLETE (all 5 pieces). `make check` = ruff clean, mypy --strict clean,
  **317 tests pass (~6s)**. CLI discovery loop runs end-to-end (turn-based HITL) → PDF; entry-based grill
  loop; vision resume parser + multimodal adapter; progressive-discovery nudge/meter/return-loop.
- All Phase-0/Phase-1/Phase-1.5-CORE worktrees pruned. Phase 1.3 and Phase 1.5 INGEST+DISCOVERY were done
  in-place on `master`.

## NEXT: Phase 1.7 then Phase 2 (web / infra / async)
Phase 1.5 is done. Phase 1.7 closes the deferred integration seams listed in the "YOU ARE HERE"
banner above. After that, Phase 2 proceeds per
[REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md):
- **Phase 2:** Streamlit web workspace (reuse the `cli/` runtime seam), `infrastructure/` Terraform
  (Cloud Run, Firestore, Artifact Registry, Secret Manager + SA `secretAccessor`, Cloud Scheduler;
  envs dev/prod), `jobs/pending_action_sweep.py` (14-day), `skills/cloud_ops/SKILL.md`.
- **Phase 3:** `evaluation/user_simulator.py` + `test_config.json`, monitoring/logging, security review.
- Launch as Sonnet builders in worktrees, fan-out where files are disjoint.

## Process (how we work — keep doing this)
**Use the [`ship-change`](../skills/ship-change/SKILL.md) skill for every code change** — it encodes
this whole loop (branch → gate → dual review → merge → deploy → verify) so it runs the same way each
time, and its `scripts/deploy_and_verify.sh` automates the merge+deploy+verify tail. Use the sibling
[`wait-for-pr-review`](../skills/wait-for-pr-review/SKILL.md) skill to block for Copilot's review instead
of hand-rolling a poll loop.

**The standard per-change loop (every code change goes through this) — updated 2026-07-06:**
1. **Subagent builds** the change on a fresh branch (`fix/…`, `feat/…`). Subagents are Sonnet
   by default; worktree-isolated for large changes (`isolation: "worktree"`).
2. **`make check` green** (ruff + mypy --strict + pytest) — plus `make tf-check` for infra changes.
   Subagent must not declare done unless gates pass.
3. **Gemini 2.5 Pro reviews** the diff as an independent gate — launched as a separate review subagent
   (`model: "Gemini 2.5 Pro (Google)"`). Reviewer re-runs gates, reads the diff, returns
   PASS / CHANGES REQUESTED with a reason list. Address CHANGES REQUESTED and re-review before pushing.
   *(Replaces the old Sonnet/Opus review step — Claude subscription ended.)*
4. **PR created** (`gh pr create`), then **Copilot review requested**
   (`gh api --method POST repos/{owner}/{repo}/pulls/N/requested_reviewers -f
   'reviewers[]=copilot-pull-request-reviewer[bot]'`; surfaces as login `Copilot`).
5. **Address Copilot comments** (fix + reply), CI green.
6. **Squash-merge** (`gh pr merge N --squash --delete-branch`).
7. **Deploy** (`gh workflow run deploy.yml --ref master -f environment=dev`) + verify HTTP 200 live.
8. **Reconcile docs** in the same session (PROGRESS/HANDOFF/etc.).

So: **Subagent builds → Gemini 2.5 Pro reviews → PR → Copilot reviews → address → merge → deploy.**
Two independent review gates (Gemini + Copilot) plus CI.
- **For large, file-disjoint work:** launch parallel Sonnet subagents in worktrees; Gemini 2.5 Pro
  reviews each branch independently before its PR.
- No agent self-declares done; only a review PASS ticks `docs/PROGRESS.md`. The reviewer independently
  re-runs gates and reads the diff.
- **master must stay green after every commit** (`make check`; `make tf-check` for infra). Contract
  changes require a `CONTRACT_VERSION` bump + tag after review PASS.

## Known gotchas
- **Shared-env mypy coupling:** gates depend on installed packages; `make check` on master is the source
  of truth. (`config.py` already uses `import google.cloud.firestore as firestore` to avoid the namespace quirk.)
- **Two model-client interfaces** (nodes vs scraper) — integration adapter bridges both.
- **WS-C:** `create_session` is last-write-wins (vs ADK raise-on-duplicate); ADK event log not durably
  persisted (CareerEngineState is). `FakeFirestoreClient` lives in the prod module — candidate to move to `tests/`.
- **v1.1.0 conversational fields:** CLI sets `pending_user_answer` + `checkpoint_verified`; reads
  `current_question` + `checkpoint_delta_summary`. finalize→`professional_summary`+`master_resume_json`;
  tailor reads `jd_text`+`master_resume_json`, writes `tailored_resume_json`.
