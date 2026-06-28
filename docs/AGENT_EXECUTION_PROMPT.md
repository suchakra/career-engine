# CareerEngine — Agent Execution Prompt

Copy the block below to direct an implementation agent (or a fan-out of sub-agents) to execute the
plan. It encodes the non-negotiables so agents don't drift. Use the **Phase 0 prompt first and alone**;
only after the contract is frozen use the **fan-out prompt**.

---

## Model assignment & cost strategy

**Sonnet builds and tests. Opus reviews and gates.** You never pay Opus to write code — only to review
a diff, which is cheap relative to its value. The split:

| Job | Model | Why |
|-----|-------|-----|
| Phase 0 contract — *draft* | Sonnet | Mechanical once the design (these docs) is fixed |
| Phase 0 contract — *review before freeze* | **Opus** | A contract bug propagates to all six agents — the one place Opus review is mandatory |
| Workstreams WS-A…F — *build + tests* | Sonnet | Bulk of the work; isolated, well-specified |
| Workstream *review gate* | **Opus** | Catches correctness/security/coupling before "done" |
| Integration — *build* | Sonnet | Wiring against frozen interfaces |
| Integration — *review* | **Opus** | Last gate before the phase is called complete |

In Claude Code this is just the `model` parameter on the `Agent` tool (`model: "sonnet"` /
`model: "opus"`). Spawn the builder with `isolation: "worktree"`.

## The develop → review handshake (definition of done)

No agent may declare its own work finished. The loop for every workstream:

1. **Sonnet builder** implements its files, writes unit tests, runs them green, self-checks against its
   Definition of Done, then reports status **`READY FOR REVIEW`** (never `DONE`) and lists files +
   tests + anything dropped/TODO.
2. **Opus reviewer** reviews the diff against: correctness, the security checklist, no coupling/God
   objects, no hardcoded model names, no secrets in Firestore, contract compliance. Verdict is
   **`PASS`** or **`CHANGES REQUESTED`** with specific, evidence-backed findings.
3. On `CHANGES REQUESTED`, **continue the same Sonnet agent** (via `SendMessage`, so it keeps its
   context — don't spawn a cold one) with the findings; it fixes and re-submits. Loop until `PASS`.
4. Only an Opus **`PASS`** flips that item to ✅ in `docs/PROGRESS.md`.

---

## ▶ Phase 0 — Contract Freeze (run this FIRST, single agent, no parallelism)
> Builder: **Sonnet**. Then a mandatory **Opus** review of the contract before you freeze it.

```
You are building CareerEngine, a privacy-first AI career-portfolio platform on Google ADK 2.0.
READ FIRST, in full: docs/ARCHITECTURE.md, docs/REFINED_PROJECT_PLAN.md, docs/PROGRESS.md.
Do ONLY Phase 0 (Contract Freeze). Do not start any other phase.

Hard rules:
- pip + venv. Pin every dependency in pyproject.toml. Pin google-adk to a real 2.0 release and
  VERIFY its actual import paths against the installed package — the snippets in ARCHITECTURE.md are
  structural, not final. If an import differs, follow the real API and note it in PROGRESS.md.
- Strict Pydantic for EVERYTHING that crosses a boundary. No free-text state hand-offs.
- config.py must expose CONTRACT_VERSION (semver), settings, client factories, and the access-mode
  flag (FREE vs BYOK).
- schema.py must define: CareerEngineState, StarStory, Capability enum
  (REASONING_HIGH/SPEED_FAST/BULK_CHEAP), the inter-agent message envelope, and UpgradeRequired.
  No secrets and no UI state in CareerEngineState. Identity (user_id) travels via session/context.
- models/registry.py, auth/provider.py (AuthProvider + KeyVault), database/, tools/, and the Runner
  are INTERFACES with typed stub signatures only — no real logic yet.
- Pin ruff + mypy in pyproject.toml and add a Makefile with real targets: lint (ruff), typecheck
  (mypy, strict), test (pytest), plus build/deploy/destroy stubs. `make lint typecheck test` must run
  green so every downstream builder inherits the same gates the Definition of Done requires.
- Add a golden type test that serializes→deserializes every Pydantic model (round-trip equality);
  wire it into `make test` and make it pass.

Deliverable: a type-checked contract with `make test` green. Do NOT declare it frozen yourself —
report status READY FOR REVIEW, list every file and the test results, and note any ADK import
deviations. An Opus reviewer must PASS it before it is frozen. Only then update docs/PROGRESS.md.
```

After the Sonnet draft, run this **Opus** review (mandatory before freeze):
```
You are reviewing the Phase-0 contract for CareerEngine before it is frozen and handed to six
parallel builders. READ docs/ARCHITECTURE.md and docs/REFINED_PROJECT_PLAN.md, then review
schema.py, config.py, models/registry.py, auth/provider.py, the stub interfaces, and the type test.
Check: every boundary is strictly Pydantic-typed; CONTRACT_VERSION present and stamped; Capability
enum + UpgradeRequired + message envelope correct; CareerEngineState carries no secrets/UI/identity;
interfaces are complete enough that WS-A…F won't need to change them; the golden serialize/deserialize
test truly covers every model; real google-adk 2.0 imports verified. A contract bug here multiplies
across all builders, so be adversarial. Verdict: PASS (safe to freeze) or CHANGES REQUESTED with
specific findings. Verify each finding before reporting it.
```

---

## ▶ Phases 1–3 — Fan-out (run AFTER Phase 0 is merged & frozen)

Assign one sub-agent per workstream, each in its **own git worktree**. Give each agent the shared
preamble + its workstream block. Then run the **integration** and **review** agents.

### Shared preamble (prepend to every workstream agent)
```
You are one of several parallel agents building CareerEngine on Google ADK 2.0.
READ FIRST: docs/ARCHITECTURE.md, docs/REFINED_PROJECT_PLAN.md, docs/PROGRESS.md.
The Phase-0 contract (schema.py, config.py, interfaces, CONTRACT_VERSION) is FROZEN — code against
it, do not change it. If you believe the contract is wrong, STOP and escalate; do not work around it.

Non-negotiables:
- Strict Pydantic; communicate state only as JSON validated against schema.py.
- No hardcoded model names — request capabilities via models/registry.py.
- Every node is a pure (CareerEngineState) -> CareerEngineState function. No God objects. No UI or
  Firestore imports inside workflows/.
- Stay strictly within YOUR files (listed below). Do not edit another workstream's files.

Definition of Done — you must satisfy EVERY item AND paste the proof. "I believe it works" is not
done; "here is the command and its output" is. The reviewer checks your evidence, not your word.

  Acceptance (behavioral):
  - Every acceptance criterion in YOUR workstream block below is met AND has a named test that
    asserts it. List each criterion -> the test function that proves it.
  - All architecture-specified FAILURE paths are handled and tested, not just the happy path
    (your WS block names them).

  Gates (mechanical) — paste the exact command + output for each:
  - `make lint` (ruff) clean · `make typecheck` (mypy) clean · `make test` green.
  - No regressions: the pre-existing/contract tests still pass — you broke no other workstream.
  - `python -c "import <your modules>"` runs with no import error.
  - Contract round-trip holds for every Pydantic model you touch:
    `Model.model_validate_json(x.model_dump_json()) == x`.

  Contract & safety (assert in tests, don't just claim):
  - No hardcoded model names anywhere (`grep -rn "gemini-" <your files>` returns nothing) —
    capabilities are requested via models/registry.py.
  - No secret/API key written to Firestore (assert in the relevant test).
  - CONTRACT_VERSION stamped on anything you persist or emit across a boundary.
  - Public functions/classes have type hints + a one-line docstring.

  Handoff:
  - You do NOT mark yourself done. Report status `READY FOR REVIEW` with: branch/worktree name,
    files changed, the criterion->test map, every gate command + its output, and an explicit list of
    anything deferred/capped/TODO (silence reads as "complete" — it isn't).
  - An Opus reviewer gates you. On CHANGES REQUESTED, fix and resubmit in this same session. Only an
    Opus PASS lets you tick docs/PROGRESS.md.
```

### WS-A — Workflow core
```
Build workflows/discovery_graph.py and workflows/nodes.py.
- Graph: ingest -> grill -> checkpoint(HITL) -> finalize -> tailor, with discovery_router and the
  5-turn checkpoint brake (see ARCHITECTURE.md §4.3).
- execute_grill_turn_node requests REASONING_HIGH; use Chain-of-Thought system prompts (decompose ->
  demand a metric -> plausibility-check -> restate as STAR) so Flash/Flash-Lite carries the load.
  Tone: senior peer over coffee; never say "STAR" to the user. On free-tier shortfall return
  UpgradeRequired, do not crash or silently degrade.
- checkpoint node is the Hydration Point: summarize the 5-turn delta, require user verification before
  committing. Unit-test each node as a pure function.

Acceptance criteria (your gate — each needs a named test):
- A vague answer ("I improved performance a lot") through execute_grill_turn_node is REJECTED — the
  node asks for a concrete metric rather than committing a StarStory.
- A specific answer ("cut p99 from 800ms to 120ms across 40 services") is accepted and produces a
  StarStory with result populated and metrics_validated=True.
- discovery_router returns "user_checkpoint_node" at question_count==5, "execute_grill_turn_node" at
  4 and 6, and "finalize_master_resume" when active_gaps is empty.
- The checkpoint node summarizes the 5-turn delta and does NOT commit until a verification flag is set.
- A REASONING_HIGH shortfall in Free Mode returns UpgradeRequired (typed), never raises/crashes.
- Each node proven pure: same input -> same output, injected deps mocked, no external mutation.
```

### WS-B — Tools & template
```
Build tools/web_scraper.py (two-step: fetch raw HTML, then BULK_CHEAP model strips nav/sidebars/
culture fluff to functional requirements + hard skills), tools/pdf_renderer.py (Jinja2 -> HTML ->
headless-Chrome PDF; sanitize/escape model output, never trust it as HTML), and
templates/classic_resume.html (clean, ATS-friendly). Map only VALIDATED state into the Jinja2 context.

Acceptance criteria (your gate — each needs a named test):
- Given a fixture JD HTML containing nav + sidebar + a "our mission/culture" block + a requirements
  list, the scraper output CONTAINS the hard skills/requirements and EXCLUDES the culture/mission text.
- pdf_renderer escapes hostile content: a StarStory field containing `<script>alert(1)</script>` does
  NOT appear as a live tag in the rendered HTML (it is escaped). Markdown like `**x**` doesn't break layout.
- Rendering a valid state produces a non-empty PDF file; rendering an invalid/partial state raises a
  validation error rather than silently emitting a broken document.
- The scraper requests BULK_CHEAP via the registry (no hardcoded model).
```

### WS-C — Persistence
```
Build database/firestore_session.py: a custom ADK 2.0 SessionService adapter. Documents keyed by
user_id (never by an API key or its hash). Stamp every document with CONTRACT_VERSION; refuse unknown
major versions. No secrets in Firestore.

Acceptance criteria (your gate — each needs a named test, Firestore faked/emulated):
- Round-trip: save(state) then load() returns an equal CareerEngineState.
- Documents are keyed by user_id (assert the document path); no document field ever contains an API key.
- A document stamped with an unknown MAJOR CONTRACT_VERSION is refused (raises); a differing MINOR
  version is accepted.
- Concurrent/last-write behavior is defined and tested (no silent partial writes).
```

### WS-D — Auth & secrets
```
Build auth/cli_auth.py (device/loopback OAuth via Identity Platform + local power-user escape hatch),
auth/firebase_auth.py (Identity Platform web), auth/key_vault.py (store/fetch the user's BYOK Gemini
key in Secret Manager, id ce-key-{user_id}; key never persisted to Firestore). Implement the
AuthProvider + KeyVault interfaces exactly.

Acceptance criteria (your gate — each needs a named test, Secret Manager + Firestore faked):
- KeyVault.store writes only to Secret Manager under ce-key-{user_id}; a test asserts NOTHING is
  written to the Firestore fake.
- KeyVault.fetch returns the stored key for the right user_id and raises for an unknown user_id.
- AuthProvider returns a STABLE user_id across repeated calls for the same identity.
- The CLI local escape hatch yields a usable (user_id, key) pair with NO network call.
- Access-mode resolution is correct: no user key -> FREE mode; user key present -> BYOK mode.
```

### WS-E — Infrastructure
```
Build infrastructure/ Terraform: reusable modules for Cloud Run, Firestore (Native), Artifact
Registry, Secret Manager, Cloud Scheduler; envs/dev and envs/prod roots; README.md + setup.sh. The
Cloud Run service account MUST be granted roles/secretmanager.secretAccessor in Terraform. Wire the
root Makefile deploy/destroy targets to the dev env.

Acceptance criteria (your gate — no live cloud needed):
- `terraform fmt -check`, `terraform validate`, and `terraform plan` succeed for BOTH envs/dev and
  envs/prod. Paste the plan summaries.
- The plan includes an IAM binding granting the Cloud Run SA roles/secretmanager.secretAccessor
  (show the resource).
- No hardcoded project IDs, regions, or secrets — everything is variables (grep proves it).
- `make deploy` / `make destroy` target the dev env and run a `terraform plan` dry-run in CI mode.
```

### WS-F — Evaluation
```
Build evaluation/user_simulator.py (ADK 2.0 UserSimulator role-playing a vague applicant) and
test_config.json. Assert the grill node pushes back and extracts numeric achievements; assert the
5-turn brake fires; record the Pro-escalation rate.

Acceptance criteria (your gate):
- An end-to-end scenario where the simulated applicant gives vague answers ends with >=1 StarStory
  whose result contains a numeric metric and metrics_validated=True (asserted, not eyeballed).
- The transcript shows the checkpoint brake firing at turn 5.
- The run records and prints the Pro-escalation rate (fraction of grills that returned UpgradeRequired
  / escalated to a paid model).
- The simulator hits the real Runner/graph interface (no bypass), and the test is deterministic
  (seeded or fixture-driven, not dependent on live model variance).
```

### Integration agent (after workstreams report done)
```
Wire main.py (CLI + Streamlit entry points) and the Runner across all workstreams. Run the full test
suite and the WS-A→B end-to-end demo (vague answer -> quantified STAR -> checkpoint@5 -> PDF). Any
interface mismatch is a contract violation: escalate for a CONTRACT_VERSION bump, do not patch around
it. Update docs/PROGRESS.md milestone table.
```

### Opus review gate (one per workstream — this is what flips an item to done)
```
Run on Opus. You are the review gate for ONE workstream's diff (the builder reported READY FOR
REVIEW). Review for: correctness bugs, God-object/coupling violations, hardcoded model names, secrets
in Firestore, missing input sanitization in scraper/PDF, IAM over-grants in Terraform, contract
compliance (Pydantic boundaries, CONTRACT_VERSION), and test adequacy (do the tests actually exercise
the logic?). Verify each finding before reporting it. Verdict: PASS or CHANGES REQUESTED with
specific, evidence-backed findings. On CHANGES REQUESTED, the findings go back to the SAME builder
agent (via SendMessage) to fix and resubmit; re-review until PASS. Only PASS authorizes ticking
docs/PROGRESS.md.
```

---

## How to actually launch these

These prompts are written for Claude Code's `Agent` / worktree-isolated sub-agents (or any agent
runner). Recommended cadence:
1. Run the **Phase 0** builder on **Sonnet**, then the **Phase 0 Opus review**. Fix until PASS, then freeze + merge.
2. Launch **WS-A…F** concurrently on **Sonnet**, each `isolation: "worktree"`. Each reports READY FOR REVIEW.
3. Run an **Opus review gate** per workstream; loop fixes via `SendMessage` to the same Sonnet builder until PASS.
4. Run the **integration** agent (Sonnet), then its **Opus review**.
5. Repeat the fan-out for Phase 2 and Phase 3 scopes.

Mapping to the `Agent` tool:
- Builder: `Agent(subagent_type: "general-purpose", model: "sonnet", isolation: "worktree", prompt: <shared preamble + WS block>)`
- Reviewer: `Agent(subagent_type: "general-purpose", model: "opus", prompt: <Opus review gate>)` — point it at the builder's branch/worktree diff.
- Re-work loop: `SendMessage(<builder agent id>, <Opus findings>)` — keeps the builder's context warm instead of restarting cold.

> Notes: a worktree is created automatically by `isolation: "worktree"` — you don't run git
> commands. Sub-agents consume tokens; launch them when you (the user) decide to. This document tells
> agents *what* to do and on *which model*; you control *when*.
