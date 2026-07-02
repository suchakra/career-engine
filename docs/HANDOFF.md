# CareerEngine — Session Handoff / Resume Point

## 👉 YOU ARE HERE (updated 2026-07-02)
**`master` (clean, synced at `5b047e7`), Phase 2 COMPLETE (contract v2.2.0). Phase 3 in progress — eval harness (PR #1) + security review (PR #2) merged; 398 tests green. Working the ordered Phase-3 queue via a PR-based workflow.**
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
  2. **Monitoring/logging** for graph hangs (observability). ⬅ NEXT
  3. **CoT tuning** — measure & reduce the Pro-escalation rate (eval harness now measures it).
  4. **Phase 2 deferred wiring** — Streamlit discovery-session load for the meter; sweep Cloud Run HTTP
     endpoint + IdP frontend token exchange. Also add `terraform` to the devcontainer (see memory).
  5. **Capstone dry-run** — execute [CAPSTONE_RUNBOOK.md](CAPSTONE_RUNBOOK.md) end-to-end; capture evidence.
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
