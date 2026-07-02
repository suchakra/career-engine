# CareerEngine — Session Handoff / Resume Point

## 👉 YOU ARE HERE (updated 2026-07-02)
**`master` at **contract v2.4.0** (tag `contract-v2.4.0`, PR #9 merged) — grill hardening from a live résumé run: graceful `ModelAPIError`, `grill_answers` memory, current/substantive-first frontier (ARCHITECTURE §6.3.1). Phase 3 COMPLETE (PRs #2–#6); repo public-ready with README + CI/CD + LICENSE + Dockerfile (PRs #7–#8). 434 tests green; `make check` + `make tf-check` clean; CI green on GitHub. No work in flight.**
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
- **Current model (since Phase 1.5 fan-out): Opus builds in-context, Sonnet reviews as the gate.** Chosen
  for token efficiency on small/coupled work — spawning cold Sonnet worktree builders re-derives context
  and costs more. Opus builds directly on `master`, commits per workstream (green each), then a Sonnet
  review agent re-runs all gates + reads the diff and returns PASS / CHANGES REQUESTED. **Copilot was a
  third independent gate but is out for the month → Sonnet is now the SOLE gate.**
- **Alternative (large, file-disjoint work): Sonnet builds in worktrees, Opus reviews** (`model: "sonnet"`,
  `isolation: "worktree"`). Use when workstreams are big and don't share files.
- No agent self-declares done; only a review PASS ticks `docs/PROGRESS.md`. The reviewer independently
  re-runs gates and reads the diff (don't trust the report).
- **master must stay green after every commit** (`make check`; `make tf-check` for infra). Contract
  changes require a `CONTRACT_VERSION` bump + tag after review PASS.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Known gotchas
- **Shared-env mypy coupling:** gates depend on installed packages; `make check` on master is the source
  of truth. (`config.py` already uses `import google.cloud.firestore as firestore` to avoid the namespace quirk.)
- **Two model-client interfaces** (nodes vs scraper) — integration adapter bridges both.
- **WS-C:** `create_session` is last-write-wins (vs ADK raise-on-duplicate); ADK event log not durably
  persisted (CareerEngineState is). `FakeFirestoreClient` lives in the prod module — candidate to move to `tests/`.
- **v1.1.0 conversational fields:** CLI sets `pending_user_answer` + `checkpoint_verified`; reads
  `current_question` + `checkpoint_delta_summary`. finalize→`professional_summary`+`master_resume_json`;
  tailor reads `jd_text`+`master_resume_json`, writes `tailored_resume_json`.
