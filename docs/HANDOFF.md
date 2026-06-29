# CareerEngine — Session Handoff / Resume Point

> Purpose: pick up cleanly after a session reset. Written 2026-06-29.
> Companion to [PROGRESS.md](PROGRESS.md) (live status), [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)
> (roadmap), [AGENT_EXECUTION_PROMPT.md](AGENT_EXECUTION_PROMPT.md) (builder/reviewer prompts).

## Where we are
- **Branch `master`, pushed to origin** at the commit that adds this file (run `git log --oneline -1`).
- **Contract: v1.1.0** (tags `contract-v1.0.0`, `contract-v1.1.0`). Changing `schema.py`/`config.py`/
  public interfaces requires a `CONTRACT_VERSION` bump.
- **Phase 0:** ✅ frozen. **Phase 1 builders WS-A/B/C/D:** ✅ all merged, Opus-PASS. `make check` on
  master = ruff clean, mypy --strict clean, **201 tests pass**.
- Worktrees for WS-A/B/C/D were pruned after merge.

## IN-FLIGHT: Phase-1 integration (INCOMPLETE — being fixed)
- A Sonnet builder is building the CLI integration: `main.py` (thin entrypoint) + `cli/` runtime +
  `integration/model_client.py` + `tests/test_integration.py`, plus a minimal change to
  `workflows/discovery_graph.py`.
- Background agent id: **`ad00b283a660575a5`**. Worktree: **`.claude/worktrees/agent-ad00b283a660575a5`**,
  branch `worktree-agent-ad00b283a660575a5`. **WIP is COMMITTED at `1a2f77d`** (snapshot — reset-safe).
- **Known-broken, fix in progress:** the e2e test `TestEndToEndRunnerFlow::test_vague_answer_rejected_
  no_story_committed` HANGS (infinite loop): the discovery loop is turn-based/HITL but was driven via a
  single `run_async` that loops with no pause for input. Fix = drive ONE turn per invocation, human input
  in the CLI layer (never inside run_async); every test must finish fast. Also 28 ruff + 6 mypy errors to clear.

### Resume the integration (do this first)
1. `git -C .claude/worktrees/agent-ad00b283a660575a5 status` and `... diff master --stat` to see its work.
2. **If the worktree has complete work** (`main.py`, `cli/`, `tests/test_integration.py`):
   - `cd` into it, run `make check` (ruff + mypy --strict + pytest). Expect green.
   - **Opus review gate** (verify, don't trust): the e2e test drives the real ADK Runner (not a bypass);
     the model-client adapter satisfies BOTH interfaces — `workflows.nodes` `.generate(model_id,system,user)`
     (injected via `set_model_client_factory`) AND `tools.web_scraper` `.generate_content_text(model=,system=,prompt=)`;
     access-mode key wiring (FREE→settings key, BYOK→`SecretManagerKeyVault.fetch_key`); `render_pdf`
     yields a non-empty `%PDF`; NO frozen-contract files (schema.py/config.py) edited; no hardcoded `gemini-`.
   - On PASS: commit on its branch (co-author trailer below), `git merge --no-ff` into master, run
     `make check` on master, then `git push origin master --follow-tags`. Update PROGRESS.md (tick
     `main.py` + the Phase-1 exit demo; set Phase 1 milestone ✅).
   - On issues: resume the same builder via its agent id with specific findings, or relaunch (prompt below).
3. **If the worktree is empty/partial/broken:** relaunch the integration builder. The full prompt is in
   the conversation that created agent `ad00b283a660575a5`; the scope is summarized in PROGRESS.md
   "Integration notes" and AGENT_EXECUTION_PROMPT.md "Integration agent" block.

## After integration merges → Phase 1 complete
Then proceed per [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md):
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
