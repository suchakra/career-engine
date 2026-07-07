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
| D9 (2026-06-29) | **Capstone-deliverable discipline** (Google X Kaggle 5-day intensive) | Prioritize a demoable end-to-end slice, reproducible setup/gates, and evidence artifacts over speculative scope. Phase 1.7 closes integration seams before broad Phase 2 fan-out. |
| D10 (2026-07-04) | **Portfolio Workbench** (Phase 4) — surface + steer the gathered data | The web app makes the persisted portfolio **visible** (experience tree + per-entry recorded stories), **navigable** (sidebar), and **user-steerable** (add a project; jump the grill to a chosen experience). Reads existing `CareerEngineState`; needs **no contract change** for 4A–4D (only deferred 4E `highlight` bumps the contract). See [ARCHITECTURE.md §14](ARCHITECTURE.md). |

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
  clock); add `entry_id` to `StarStory`; **replace** pillar fields (`target_competencies`/`active_gaps`/
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

### Phase 1.7 — Integration closure (deferred Phase-1 work)  *(SEQUENTIAL, short hardening pass)*
This phase is the formal home for deferred Phase-1/1.5 integration seams. It is intentionally
small and execution-oriented so Phase 2 can fan out cleanly.
- **1.7-A CLI resume-upload wiring:** add `--resume-file` support to `grill` and seed
  `start(work_timeline=...)` using `tools.resume_parser.parse_resume`.
- **1.7-B Session resume correctness:** load and resume prior state for return-loop flows instead of
  relying on last-write-wins `create_session` semantics.
- **1.7-C Discovery graph integration:** wire `discovery_turn_node` into the main graph/CLI path.
- **1.7-D Persistence test hygiene:** move fake Firestore hierarchy out of production module into
  `tests/` to keep runtime modules production-only.

**Exit criteria:** user can start from a resume file, pause, resume the same session, continue backward
discovery through the wired graph, and complete `make check` with no production test-fake classes.

### Phase 2 — Web, Infra, Async  *(PARALLEL after Phase 1.7)*
- Streamlit workspace (`main.py` web path) — dashboard, pending-action surface
- `auth/firebase_auth.py` (Identity Platform web)
- `infrastructure/` Terraform: Cloud Run, Firestore, Artifact Registry, Secret Manager + SA
  `secretAccessor`, Cloud Scheduler; `envs/{dev,prod}`; `README.md`
- `jobs/pending_action_sweep.py` (14-day sweep) + scheduler wiring
- `skills/cloud_ops/SKILL.md`

**Exit criteria:** deploy to `dev` via `make deploy`; web + CLI share state; sweep flags stale apps;
capstone demo path (resume upload → grill/discovery continuation → tailoring → pending-action surface)
is reproducible in one scripted runbook.

### Phase 3 — Hardening & Eval  *(PARALLEL)*
- `evaluation/user_simulator.py` + `test_config.json` (vague-applicant adversarial scenarios)
- Monitoring/logging dashboards for graph hangs
- Security review (key handling, IAM least-privilege, injection in scraper/PDF)
- CoT prompt tuning to push Flash-Lite coverage; measure Pro-escalation rate

### Phase 4 — Portfolio Workbench  *(PARALLEL-ish; UI-forward; mostly no contract change)*
Full spec in [ARCHITECTURE.md §14](ARCHITECTURE.md); groomed build prompts in
[GROOMING.md](GROOMING.md) Phase 4. Make the gathered career data visible, navigable, and steerable in
the web app. Ordered so each slice is independently shippable:
- **4A — Sidebar navigation shell.** Repurpose the empty left panel into persistent nav
  (Dashboard / Portfolio / Grill / Tailor) + identity/sign-out + a compact applications list. Pure UI;
  no schema/contract change. Quick win against the "bothersome empty panel."
- **4B — Portfolio view (peruse recorded details).** Read-only view over the persisted discovery state:
  `work_timeline` as an experience tree; select an `Entry` → its recorded `StarStory`s (grouped by
  `entry_id`), status, and bullets. New pure helper `stories_by_entry`; no contract change.
- **4C — Steerable grill (jump to an experience).** "Grill me about this" pins `grill_frontier` to the
  chosen `entry_id` before the next turn (jumpable frontier already honored by the router). Lets the user
  override reverse-chronological order. No contract change.
- **4D — Add an experience/project manually.** UI to add an `Entry` (`source="manual"`, e.g. a `PROJECT`
  under an existing org) into `work_timeline`, persisted so it shows in the tree and is immediately
  grillable — the long-tenure breadth fix. Introduces the tested **portfolio-mutation seam** (AD-14.2).
  No contract change.
- **4E — (DEFERRED) Highlight/pin an experience for tailoring priority.** Add `Entry.highlighted`; the
  tailor prioritizes highlighted stories. The ONE item needing a contract bump (additive minor). Build
  only when asked ("maybe some day").

**Exit criteria:** from the deployed web app a user can navigate via the sidebar, open the Portfolio view
and read what was recorded per experience, add a remembered project under a long tenure, and start a grill
targeted at that specific experience — without any contract break for 4A–4D.

### Phase 5 — Tailoring & résumé quality  *(NEXT; the output must be a REAL résumé)*
Status: **planned, not started.** The Grill → Portfolio → Tailor loop ships (PRs #26/#27/#28: tailor by
paste/URL → PDF/DOCX/MD/JSON), but the **output is not yet a real résumé** — see live feedback
(2026-07-05, `demo_output/example.md`): a summary paragraph + ~5 "talking points" (headline + expanded
text + an internal *"why it fits"* note), with **no contact header, no role/company/date structure, no
skills section, no education** — not an ATS-parseable document.

- **5A — Real, ATS-safe résumé output (HIGH — the headline gap).**
  Research and adopt a standard **ATS-safe** structure (reverse-chronological, single-column, standard
  section headings) and restructure the finalize + tailor output to a proper résumé schema:
  - **Contact header** (name, email, phone, location, LinkedIn). Needs a source — extend
    `tools/resume_parser.py` to capture contact from the uploaded résumé and/or add a small profile form.
    (Likely an additive `Contact`/`Profile` model → MINOR contract bump.)
  - **Professional summary** (already produced).
  - **Skills** section, **keyword-aligned to the JD** — ATS ranks on keyword match, so surface the
    JD's hard skills the candidate actually has.
  - **Experience grouped BY ROLE** — company · title · location · dates, with the STAR bullets under each.
    Reuse `StarStory.entry_id` → `Entry` to reconstruct real work history instead of a flat achievement
    list. This is the core fix: bullets must live under their employer/role, chronologically.
  - **Education / certifications** sections (already captured as EDUCATION entries).
  - **Drop the internal `_Why it fits_`** from the document (keep it, at most, as a separate on-screen
    explanation — it is not résumé content).
  - **Selection/leveling** — a Sr. Eng Manager résumé must not lead with a volunteering/hackathon bullet;
    weight by seniority + JD relevance.
  - Update the **PDF/DOCX/Markdown** renderers (`web/exporter.py`, `tools/pdf_renderer.py`) to this
    structure so all formats emit a real résumé.
- **5B — Save as a tracked application.** Tailor → record the JD + tailored résumé as an `Application`
  on the `UserWorkspace` → shows in the dashboard "Tracked applications" and enters the 14-day
  follow-up sweep. Closes the apply → track → follow-up loop. (Reuses existing `Application` model; no
  contract change.)
- **5C — One structured renderer for master + tailored.** The master PDF currently renders from
  `extracted_star_stories`, not the finalized JSON; render both master and tailored from the same
  structured résumé so formatting is consistent.
- **(from Phase 4) 4E — Highlight/pin an experience** for tailoring priority — additive-MINOR contract bump.
- **Pre-GA `/security-review`** (web OIDC login + paid BYOK-key storage + broad deployer-SA roles) —
  the required review flagged in [SECURITY.md](../docs/SECURITY.md) before real users / GA.

**Exit criteria:** tailoring produces a document a recruiter/ATS would accept as a real résumé — contact
header, JD-aligned skills, reverse-chronological experience grouped by role with quantified bullets,
education — downloadable as PDF/DOCX/MD, with the internal reasoning removed; and a tailored résumé can be
saved as a tracked application.

### Phase 10 — Web platform migration: Streamlit → Next.js + FastAPI  *(SEQUENTIAL, API-first)*
> Phases 6–9 (A2A discovery, web discovery surface, auth/deploy hardening, UI polish) shipped after
> this plan's roadmap was last expanded; their sequencing/status is canonical in
> [PROGRESS.md](PROGRESS.md) and their build specs in [GROOMING.md](GROOMING.md). Phase 10 is the next
> planned macro-phase.

Retire the Streamlit web surface in favour of a **Next.js (React, App Router) frontend over a FastAPI
JSON API.** The Python **domain is unchanged** — only presentation + transport. Accepted decision
(rationale, auth model, streaming, deploy topology, API sketch) recorded in
[ARCHITECTURE.md §16](ARCHITECTURE.md); build slices + acceptance criteria in
[GROOMING.md](GROOMING.md) Phase 10. Sequenced **API-first** so the backend is provable before the
React shell exists:

- **10.0** — architecture decision record (ARCHITECTURE.md §16) + this sequencing. **Done as grooming.**
- **10.1** — FastAPI skeleton + auth boundary (verified token → `user_id`; reuse `auth/`).
- **10.2** — read APIs (dashboard, portfolio, jobs), typed from `schema.py`, wrapping existing stores.
- **10.3** — write APIs (profile, add experience, track application, preferences) over BUG-1-fixed stores.
- **10.4** — grill API with SSE streaming over `DiscoverySession`.
- **10.5** — Next.js app shell + routing + auth wiring (consumes 10.1–10.3).
- **10.6** — Next.js grill (streaming) + tailor + résumé export (consumes 10.4; unblocks 9H/9M).
- **10.7** — cutover: delete `web/` Streamlit, reconcile redirect URIs / infra / docs, contract-gate.

**Exit criteria:** the deployed product runs on Next.js + FastAPI with the Streamlit surface removed;
auth callback/redirect URIs are fully controlled at the API boundary; the grill streams; and no domain
behaviour or `CONTRACT_VERSION` changed as a result of the migration itself.

### Phase 11 — Post-application & outreach toolkit  *(planned; builds on the Phase 10 shell)*
Features named during Phase 10 UI design. The Next.js shell is built forward-compatibly for them —
reserved nav group (`PREPARE`), a `ConsentDialog` + per-send confirm pattern, a `Settings` home for
consents, and the reusable `StreamingTranscript` component — see
[PHASE10_UI_MOCKUP.md §9](PHASE10_UI_MOCKUP.md). Each ships as its own additive-MINOR
`CONTRACT_VERSION` bump; none blocks Phase 10.

- **11.A — Outreach / emailer suite.** Agent-drafted recruiter follow-ups + thank-you notes. Requires
  **consent pages** (one-time connected-account grant, send-only scope) **plus** mandatory
  draft-review + **per-message send confirmation**; durable, `user_id`-scoped consent records + a send
  log (recipient/subject/timestamp, not body). Reuses the Phase-10 `ConsentDialog` + `Settings →
  Connected accounts & consents`. Privacy/HITL posture mirrors the grill checkpoint ethos.
- **11.B — Interview prep.** Mock interviews with feedback, reusing the grill machinery
  (`StreamingTranscript` + turn controller) + portfolio + web research — folds in the former
  Future/Backlog interview-preparedness item ([ARCHITECTURE.md §13](ARCHITECTURE.md)). Its turn logic
  differs from the grill (prompt → recorded answer), so it supplies its own controller over the shared
  streaming surface.
- **11.C — Salary negotiator.** Offer / comp inputs → scripted (streamed) negotiation guidance +
  scenario-compare cards.
- **11.D — Profile location & work-model preference.** Structured **base location** + **remote scope**
  (`On-site` · `Hybrid` · `Remote within {region}` · `Remote anywhere`) setting in the Profile area
  (e.g. "GTA, Canada" · "Remote within Canada"), which the **Jobs rubric inherits** (shown read-only
  in Jobs preferences). Not a job-search preference today; additive-MINOR contract bump when built.

### Phase N — opportunistic value-adds (wanted; NOT v1-blocking; build when feasible)
- **Outcome learning (positive-reinforcement)** ([ARCHITECTURE.md §8.1](ARCHITECTURE.md)): async-learn,
  per user + per job type, which résumé format/wording correlated with **reaching interview** — positive
  signal only (never penalize rejections). Transparent to the user; private unless they opt in to
  contribute anonymized patterns to a global "what works per job type" DB. Reuses §8 async infra → cheap
  once Phase 2 ships; nothing depends on it.

### Future / Backlog — post-v1 (NOT in scope)
- **Interview preparedness** ([ARCHITECTURE.md §13](ARCHITECTURE.md)): **promoted into Phase 11.B**
  above — on "interview scheduled," research the company+role's typical interview shape (coding /
  system design / behavioral) and run agent-driven **mock interviews** with feedback, reusing the
  grilling machinery + portfolio + web search.

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
