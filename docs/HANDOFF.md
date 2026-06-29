# CareerEngine — Session Handoff / Resume Point

## 👉 YOU ARE HERE (updated 2026-06-29)
**`master`, Phase 1.5 COMPLETE (contract v2.0.0). Two unpushed commits — review (Copilot) & push; next is Phase 2.**
Phase 0 + Phase 1 + Phase 1.3 + **all of Phase 1.5** are built (**317 tests**; `make check` green: ruff +
mypy --strict + pytest). CORE (`1.5-CONTRACT`+`1.5-GRILL`+`1.5-METRICS`) was Sonnet-built/Opus-reviewed/merged
(tag **`contract-v2.0.0`**). **INGEST + DISCOVERY** were built directly by Opus this session (token-efficient
path, user-approved) and **Sonnet-reviewed PASS** (0 must-fix; 4 nits applied). A Copilot review is planned.
- **Two local commits not yet pushed:** `feat(1.5): INGEST …`, `feat(1.5): DISCOVERY …`. Tree is clean.
- **NEXT (recommended):** **Phase 2** (web/infra/async) per [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md).
  Before/alongside Phase 2, optionally close the Phase-1.5 **deferred integration items** below.
- **Phase 1.5 deferred integration items** (engine + helpers are built and tested; CLI surfacing is partial):
  1. Wire resume-file upload into the `grill` command (`main.py`/`cli/app.py`): call
     `tools.resume_parser.parse_resume(bytes, mime)` and seed `start(work_timeline=…)`. The seam exists
     (`ingest_node` consumes a pre-seeded `work_timeline`); only the CLI option + file read are missing.
  2. Full session-resume for the return loop: `run_return_loop` + `has_resumable_work` are built/tested and
     the launch offer is gated on `--session-id`, but WS-C `create_session` is last-write-wins, so a real
     reload of prior state isn't wired yet (depends on the Phase-2 persistence pass).
  3. `discovery_turn_node` exists + is tested but is **not yet an edge in the main graph** — wire it into the
     CLI/graph flow when surfacing the "what have you done since?" discovery turn.
- **To IDEATE:** read this file, then [ARCHITECTURE.md](ARCHITECTURE.md) + [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md); capture new ideas back into the docs (don't mutate a spec that's mid-build — version-gate instead).

---

> Purpose: pick up cleanly after a session reset. Written 2026-06-29.
> Companion to [PROGRESS.md](PROGRESS.md) (live status), [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)
> (roadmap), [AGENT_EXECUTION_PROMPT.md](AGENT_EXECUTION_PROMPT.md) (builder/reviewer prompts).

## Where we are
- **Branch `master`** — origin is behind by 2 commits (INGEST, DISCOVERY) awaiting Copilot review + push.
- **Contract: v2.0.0** (tags `contract-v1.0.0`, `contract-v1.1.0`, `contract-v2.0.0`). Changing
  `schema.py`/`config.py`/public interfaces requires a `CONTRACT_VERSION` bump.
- **Phase 0:** ✅ frozen. **Phase 1 (WS-A/B/C/D + integration):** ✅ COMPLETE. **Phase 1.3:** ✅ done.
  **Phase 1.5:** ✅ COMPLETE (all 5 pieces). `make check` = ruff clean, mypy --strict clean,
  **317 tests pass (~6s)**. CLI discovery loop runs end-to-end (turn-based HITL) → PDF; entry-based grill
  loop; vision resume parser + multimodal adapter; progressive-discovery nudge/meter/return-loop.
- All Phase-0/Phase-1/Phase-1.5-CORE worktrees pruned. Phase 1.3 and Phase 1.5 INGEST+DISCOVERY were done
  in-place on `master`.

## NEXT: Phase 2 (web / infra / async)
Phase 1.5 is done. See the deferred Phase-1.5 integration items in the "YOU ARE HERE" banner above —
optionally close them before/alongside Phase 2. Phase 2 proceeds per
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
