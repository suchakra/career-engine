# CareerEngine — Refined Project Plan

> Companion to [ARCHITECTURE.md](ARCHITECTURE.md). Tracks scope, sequencing, and how to build this
> with parallel sub-agents. Live status lives in [PROGRESS.md](PROGRESS.md). The agent kickoff prompt
> is [AGENT_EXECUTION_PROMPT.md](AGENT_EXECUTION_PROMPT.md).
> The original spec (superseded — Gemini 1.5 / key-hash tenancy / "zero-knowledge") is retained in
> git history only: `git show 86fb10e:docs/PROJECT_PLAN.md`.

---

## 1. Locked decisions (2026-06-28)

| # | Decision | Consequence |
|---|----------|-------------|
| D1 | **Model-agnostic Capability Registry**, Flash/Flash-Lite baseline | Features request capabilities (`REASONING_HIGH`, `SPEED_FAST`, `BULK_CHEAP`); resolver picks the model. No hardcoded model strings. |
| D2 | **Free Mode + BYOK Mode** | Free Mode = managed keys → free-tier Flash. BYOK = user key in Secret Manager → paid models. Graceful "provide key / upgrade" prompt on `REASONING_HIGH` shortfall. |
| D3 | **Flash-Lite + Chain-of-Thought** over model size | Prompt engineering closes the gap to Pro; Pro is the exception, not the default. |
| D4 | **Real auth: Google Cloud Identity Platform** (not `SHA-256(key)`) | Stable `user_id`; key rotation no longer orphans data; async sweep is server-resolvable. |
| D5 | **Privacy-first, not zero-knowledge** | Per-user isolation + key encrypted in Secret Manager. ZK rejected because it breaks the server-side 14-day sweep. |
| D6 | **CLI-first, then Streamlit** | Validate the ADK loop in the terminal; Streamlit is a thin, swappable frontend-for-agents. |
| D7 | **Strict Pydantic + JSON contracts, versioned** | All boundaries typed; `CONTRACT_VERSION` stamped on every doc/message. |
| D8 (2026-06-29) | **Resume-aware, role-based, progressive discovery** (Phase 1.5, contract v2.0.0) | Vision ingest of existing resumes; `work_timeline` of entries **replaces** pillar `active_gaps`; the gap = more entries; nudge-based (NOT gated) readiness over a trailing-5-yr window + backward-chronological return loop. See [ARCHITECTURE.md §12](ARCHITECTURE.md). |

---

## 2. Phased roadmap

### Phase 0 — Contract Freeze  *(SEQUENTIAL · single agent · blocking)*
Nothing fans out until these are merged and frozen. They are the interfaces every other agent codes against.
- `pyproject.toml` (pinned `google-adk`, pydantic, jinja2, streamlit, google-cloud-* ), venv, `.env.example`
- `config.py` — settings, `CONTRACT_VERSION`, client factories, access-mode flag
- `schema.py` — `CareerEngineState`, `StarStory`, `Capability`, message envelopes, `UpgradeRequired`
- `models/registry.py` — capability→model resolver interface + Free/BYOK routing (stub bodies OK)
- `auth/provider.py` — `AuthProvider` interface, `KeyVault` interface (stub bodies OK)
- `database/` + `tools/` + Runner **interface signatures** as typed stubs
- `Makefile` skeleton (`lint test build deploy destroy`)
- One golden end-to-end **type test**: serialize→deserialize every model; CI gate.

**Exit criteria:** `make test` green on the contract; signatures will not change without a version bump.

### Phase 1 — Core agent loop (CLI-first MVP)  *(PARALLEL after freeze)*
- Workflow graph + nodes (ingest → grill → checkpoint(HITL) → finalize → tailor) with CoT prompts
- Firestore `SessionService` adapter
- `tools/web_scraper.py` (two-step), `tools/pdf_renderer.py`, `templates/classic_resume.html`
- `models/registry.py` real resolver + capability detection
- `auth/cli_auth.py` + `auth/key_vault.py` (local + Secret Manager)
- `main.py` CLI entrypoint wiring the Runner

**Exit criteria:** a terminal session grills a vague answer into a quantified STAR story, checkpoints
at turn 5, and renders a PDF. ✅ **DONE** (tag `phase-1-mvp`, 228 tests).

### Phase 1.5 — Resume-aware ingestion & progressive discovery  *(contract v2.0.0)*
Full spec in [ARCHITECTURE.md §12](ARCHITECTURE.md). **Breaking** contract amendment (v2.0.0 — removes
pillar fields); reworks WS-A's grill loop. (No migration burden — pre-release, no production data.) Scope:
- **Serves 0–5yr / early-career too:** `work_timeline` holds **experience entries** (jobs, internships,
  projects, research, leadership, …), not just jobs. Discovery is a **nudge, not a gate** over a
  trailing-5-year **window** (not a minimum) — applying is never blocked and nobody is gated on "having 5
  years" (see [ARCHITECTURE.md §12.4/§12.6](ARCHITECTURE.md)).
- **Contract v2.0.0:** add `work_timeline: list[Entry]`, `coverage_through`, `reference_date` (injected
  clock); add `role_id` to `StarStory`; **replace** pillar fields (`target_competencies`/`active_gaps`/
  `current_pillar`) with role-based equivalents + `grill_frontier`. `is_apply_ready` + progress meter derived.
- **Vision ingest** — new `tools/resume_parser.py`: file/photo → multimodal Flash → `work_timeline`.
  Add a multimodal entry point to the model-client adapter. PDF + images first; DOCX later.
- **Rework `ingest_node` + grill loop** to be role-based; add the **discovery turn** (confirm coverage,
  append missing roles). Reuse the existing STAR grilling per role; skip already-quantified bullets.
- **Progressive discovery engine:** `discovery_completeness` derived signal over the trailing-5-year
  **window** (a measure, not a gate); `grill_frontier` for backward-chronological continuation (jumpable;
  soft horizon ~10–15 yrs); derived progress meter. (The login **nudge UI** surfaces in Phase 2 on the
  Pending Action panel.)
- **Applying/tailoring is NEVER blocked.** Discovery is a persistent, consent-respecting **nudge** shown
  on each apply/tailor when the window is incomplete ("results are stronger with more filled in — now /
  later"), snooze-able. Autonomy first.

**Exit criteria:** upload a stale resume (image/PDF) → timeline parsed → "since 2022?" discovery adds
missing roles → role-by-role grilling → `is_apply_ready` unlocks tailoring; returning a later session
resumes grilling backward from the frontier.

### Phase 2 — Web, Infra, Async  *(PARALLEL)*
- Streamlit workspace (`main.py` web path) — dashboard, pending-action surface
- `auth/firebase_auth.py` (Identity Platform web)
- `infrastructure/` Terraform: Cloud Run, Firestore, Artifact Registry, Secret Manager + SA
  `secretAccessor`, Cloud Scheduler; `envs/{dev,prod}`; `README.md`
- `jobs/pending_action_sweep.py` (14-day sweep) + scheduler wiring
- `skills/cloud_ops/SKILL.md`

**Exit criteria:** deploy to `dev` via `make deploy`; web + CLI share state; sweep flags stale apps.

### Phase 3 — Hardening & Eval  *(PARALLEL)*
- `evaluation/user_simulator.py` + `test_config.json` (vague-applicant adversarial scenarios)
- Monitoring/logging dashboards for graph hangs
- Security review (key handling, IAM least-privilege, injection in scraper/PDF)
- CoT prompt tuning to push Flash-Lite coverage; measure Pro-escalation rate

### Phase N — opportunistic value-adds (wanted; NOT v1-blocking; build when feasible)
- **Outcome learning (positive-reinforcement)** ([ARCHITECTURE.md §8.1](ARCHITECTURE.md)): async-learn,
  per user + per job type, which résumé format/wording correlated with **reaching interview** — positive
  signal only (never penalize rejections). Transparent to the user; private unless they opt in to
  contribute anonymized patterns to a global "what works per job type" DB. Reuses §8 async infra → cheap
  once Phase 2 ships; nothing depends on it.

### Future / Backlog — post-v1 (NOT in scope)
- **Interview preparedness** ([ARCHITECTURE.md §13](ARCHITECTURE.md)): on "interview scheduled," research
  the company+role's typical interview shape (coding / system design / behavioral) and run agent-driven
  **mock interviews** with feedback, reusing the grilling machinery + portfolio + web search. Distant future.

---

## 3. Parallelization strategy (dev-time sub-agents)

The architecture's strict layering is *deliberately* built for fan-out. The rule: **freeze the
contract, then parallelize along dependency-free workstreams, then integrate.**

### 3.1 Why it works here
- Every node is `(state) -> state` and pure → independently buildable and unit-testable.
- UI / persistence / auth / models are injected interfaces → a stub satisfies a dependency, so an
  agent never waits on another agent's *implementation*, only its *signature* (frozen in Phase 0).
- Pydantic + JSON contracts mean agents hand off validated objects, not prose → no drift.

### 3.2 Workstreams after the Phase-0 freeze (run concurrently)
| WS | Scope | Depends only on |
|----|-------|-----------------|
| **A — Workflow** | `discovery_graph.py`, `nodes.py`, CoT prompts | `schema`, `models` iface |
| **B — Tools** | `web_scraper.py`, `pdf_renderer.py`, `classic_resume.html` | `schema`, `models` iface |
| **C — Persistence** | `firestore_session.py` | `schema` |
| **D — Auth/Secrets** | `cli_auth.py`, `firebase_auth.py`, `key_vault.py` | `auth/provider` iface |
| **E — Infra** | Terraform modules + envs, Makefile | naming conventions only |
| **F — Eval** | `user_simulator.py`, `test_config.json` | `schema`, Runner iface stub |

### 3.3 Orchestration pattern (Sonnet builds, Opus reviews)
Cost model: **Sonnet does all building + testing; Opus only reviews diffs** (cheap relative to its
value). No agent declares its own work done — an Opus PASS is the gate. See
[AGENT_EXECUTION_PROMPT.md](AGENT_EXECUTION_PROMPT.md) for the develop→review handshake.

1. **Contract agent (Sonnet, solo)** drafts Phase 0 → **Opus reviews the contract** (mandatory; a
   contract bug propagates to all six builders) → fix until PASS → **freeze**.
2. **Fan-out:** one **Sonnet** builder per workstream, each in an **isolated git worktree** (the
   harness creates it via `isolation: "worktree"` — not manual git, not sub-repos). Each reports
   `READY FOR REVIEW`, never `DONE`.
3. **Opus review gate** per workstream; `CHANGES REQUESTED` loops back to the *same* Sonnet builder
   (via `SendMessage`, context intact) until `PASS`. Only PASS ticks PROGRESS.md.
4. **Integration agent (Sonnet)** wires `main.py` + Runner; interface mismatches are contract
   violations → escalate for a `CONTRACT_VERSION` bump, don't patch around. Then an **Opus** review
   closes the phase.

### 3.4 Guardrails against agent-drift
- Sub-agents return **validated JSON against `schema.py`**, never free-text state.
- No agent edits another workstream's files; shared changes go back through the contract agent + a
  `CONTRACT_VERSION` bump.
- Each agent must run `make test` (or its workstream's tests) green before reporting done.
- `log()` any scope dropped or capped — silent truncation reads as "done" when it isn't.

### 3.5 Scope discipline
Match agent count to the phase. Phase 0 = **one** agent (no parallelism — it's the contract). Phases
1–3 = up to 6 concurrent workstream agents + 1 integration + 1 reviewer. Don't spawn agents the user
hasn't asked for; this plan documents *how*, the user decides *when* to launch.

---

## 4. Open risks to watch
- **ADK 2.0 import paths** — pin the version in Phase 0 and verify actual module names against the
  installed package; the snippets in ARCHITECTURE.md are structural, not final.
- **Google model churn** — the Capability Registry isolates this; revisit default model mappings each phase.
- **CLI OAuth UX** — device/loopback flow must stay frictionless for the "power-user CLI" tenet.
- **Pro-escalation rate** — if too many free-tier grills escalate, invest in CoT prompts before code.
