# CareerEngine — Session Handoff / Resume Point

## 👉 YOU ARE HERE (updated 2026-06-30)
**`master`, Phase 1.7 BUILT + Sonnet-reviewed PASS + **Copilot-reviewed PASS** (contract v2.1.0). Tag `contract-v2.1.0` → push → Phase 2.**
Phase 0 + Phase 1 + Phase 1.3 + Phase 1.5 + **all of Phase 1.7** are built (**339 tests**; `make check`
green). Sonnet review verdict **PASS** (0 must-fix; 4 nits applied incl. a discovery-turn empty-question
fallback). Phase 1.7 closed the deferred Phase-1/1.5 integration seams, all Opus-built this session +
Sonnet-reviewed (Copilot gate planned):
  - **1.7-A** resume-file upload wired into `grill` (`--resume-file`).
  - **1.7-B** true session resume (`get_session_state_if_exists`, load-before-create).
  - **1.7-C** `discovery_turn_node` wired into the main graph + router branch — contract bumped
    **v2.0.0 → v2.1.0** (additive `coverage_confirmed`; user-approved).
  - **1.7-D** FakeFirestore doubles moved to `tests/fakes.py`.
- **Unpushed commits:** the 1.7 series (`feat(1.7-B)`, `feat(1.7-A)`, `refactor(1.7-D)`, `feat(1.7-C)`)
  + this docs reconcile. Tree clean.
- **BEFORE moving on:** **tag `contract-v2.1.0`**, flip Phase 1.7 to ✅ in PROGRESS.md, push.
- **NEXT:** **Phase 2** (web/infra/async) per [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md). The only
  1.7 leftover is a single scripted end-to-end capstone runbook (resume-file → discovery → resume →
  tailor), folded into Phase 2 demoability polish.
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
- **Sonnet builds, Opus reviews & merges.** Spawn builders with `model: "sonnet"`, `isolation: "worktree"`.
  No agent self-declares done; only an Opus PASS merges. Reviewer must independently re-run gates and
  read the diff (don't trust the report).
- **master must stay green after every merge** (`make check`). Merge with `--no-ff`.
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
