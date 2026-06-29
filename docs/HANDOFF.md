# CareerEngine — Session Handoff / Resume Point

## 👉 YOU ARE HERE (updated 2026-06-29)
**`master`, Phase 1.5 CORE just landed (contract v2.0.0) — verify clean & push; then fan out INGEST ∥ DISCOVERY.**
Phase 0 + Phase 1 + Phase 1.3 + **Phase 1.5 CORE** are built (285 tests; `make check` green: ruff +
mypy --strict + pytest). CORE = `1.5-CONTRACT` + `1.5-GRILL` + `1.5-METRICS`, built in one Sonnet
worktree, Opus-reviewed PASS, merged `--no-ff`, tagged **`contract-v2.0.0`**. The contract is now
**BREAKING v2.0.0**: `Entry` timeline replaces pillar fields; entry-based grill loop (backward-chronological,
jumpable frontier); `discovery_completeness`/`recent_window_complete` helpers; extended metric patterns.
- **NEXT (recommended):** **fan out the two remaining 1.5 workstreams in PARALLEL** — `1.5-INGEST`
  (vision parser; `nodes.py`/`tools/`) ∥ `1.5-DISCOVERY` (CLI nudge/meter/return-loop; `cli/` only).
  Disjoint files → safe to run concurrently. Each: Sonnet builder in worktree → Opus-review → merge.
- **To BUILD:** say "build 1.5-INGEST" and/or "build 1.5-DISCOVERY" → launch the GROOMING.md prompts
  (Sonnet, worktree) → Opus-review the diff → merge (master stays green). The 3 review open-questions
  are RESOLVED ([REVIEW.md §5](REVIEW.md)); #2 SSRF folds into INGEST, #9 stale-docstring into DISCOVERY.
- **To IDEATE:** read this file, then [ARCHITECTURE.md](ARCHITECTURE.md) + [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md); capture new ideas back into the docs (don't mutate a spec that's mid-build — version-gate instead).

---

> Purpose: pick up cleanly after a session reset. Written 2026-06-29.
> Companion to [PROGRESS.md](PROGRESS.md) (live status), [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)
> (roadmap), [AGENT_EXECUTION_PROMPT.md](AGENT_EXECUTION_PROMPT.md) (builder/reviewer prompts).

## Where we are
- **Branch `master`, pushed to origin** at the commit that adds this file (run `git log --oneline -1`).
- **Contract: v2.0.0** (tags `contract-v1.0.0`, `contract-v1.1.0`, `contract-v2.0.0`). Changing
  `schema.py`/`config.py`/public interfaces requires a `CONTRACT_VERSION` bump.
- **Phase 0:** ✅ frozen. **Phase 1 (WS-A/B/C/D + integration):** ✅ COMPLETE, all Opus-PASS & merged.
  **Phase 1.3 (review hardening):** ✅ done (stays v1.1.x). `make check` = ruff clean, mypy --strict
  clean, **230 tests pass (~8s)**. The CLI discovery loop runs end-to-end (turn-based HITL) and renders
  a PDF; the upgrade-required path now reads the real `_upgrade_required` signal.
- All Phase-0/Phase-1 worktrees pruned after merge. Phase 1.3 was done in-place on `master`.

## NEXT: Phase 1.5 fan-out (CORE done) — then Phase 2
**Phase 1.5** (resume-aware vision ingest + role/entry timeline + progressive discovery, contract
**v2.0.0**) is spec'd ([ARCHITECTURE.md §12](ARCHITECTURE.md)) and groomed into sonnet-ready
prompts — see **[GROOMING.md](GROOMING.md)** for the status table and launchable prompts.
- **CORE = DONE** — `1.5-CONTRACT` + `1.5-GRILL` + `1.5-METRICS` merged (contract v2.0.0, 285 tests, tag
  `contract-v2.0.0`). Remaining: `1.5-INGEST` ∥ `1.5-DISCOVERY` (both ✅ launchable in [GROOMING.md](GROOMING.md)).
- **Build order:** CORE ✅ merged (master green). Now fan out `1.5-INGEST` (nodes.py/tools) ∥ `1.5-DISCOVERY` (cli/)
  — disjoint files → Opus-review + merge each.
- To launch each follow-up: run its GROOMING.md prompt in a Sonnet worktree → Opus-review → merge. They
  touch disjoint files (INGEST=`nodes.py`/`tools`, DISCOVERY=`cli/`) so they can run concurrently.

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
