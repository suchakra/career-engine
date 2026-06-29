# CareerEngine — Session Handoff / Resume Point

> Purpose: pick up cleanly after a session reset. Written 2026-06-29.
> Companion to [PROGRESS.md](PROGRESS.md) (live status), [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)
> (roadmap), [AGENT_EXECUTION_PROMPT.md](AGENT_EXECUTION_PROMPT.md) (builder/reviewer prompts).

## Where we are
- **Branch `master`, pushed to origin** at the commit that adds this file (run `git log --oneline -1`).
- **Contract: v1.1.0** (tags `contract-v1.0.0`, `contract-v1.1.0`). Changing `schema.py`/`config.py`/
  public interfaces requires a `CONTRACT_VERSION` bump.
- **Phase 0:** ✅ frozen. **Phase 1 (WS-A/B/C/D + integration):** ✅ COMPLETE, all Opus-PASS & merged.
  `make check` on master = ruff clean, mypy --strict clean, **228 tests pass (~5s)**. The CLI discovery
  loop runs end-to-end (turn-based HITL) and renders a PDF.
- All Phase-0/Phase-1 worktrees pruned after merge. No work in flight.

## NEXT: Phase 1.5 (groomed) — then Phase 2
**Phase 1.5** (resume-aware vision ingest + role/entry timeline + progressive discovery, contract
**v2.0.0**) is spec'd ([ARCHITECTURE.md §12](ARCHITECTURE.md)) and partly groomed into sonnet-ready
prompts — see **[GROOMING.md](GROOMING.md)** for the grooming status table and launchable prompts.
- **Ready to launch now:** `1.5-CONTRACT` (blocking, solo, freeze first), then `1.5-INGEST`.
- **Still to groom:** `1.5-GRILL` (draft), `1.5-DISCOVERY` (todo), `1.5-METRICS` (draft).
To build: groom GRILL → launch CONTRACT (Sonnet, freeze via Opus) → fan out INGEST ∥ GRILL → DISCOVERY.

Phase 2 (after 1.5) proceeds per [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md):
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
