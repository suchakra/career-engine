# CareerEngine — System Architecture

> Status: **active** (design truth for shipped + upcoming work).
> Last reviewed: 2026-07-06.
> Build status is **not** canonical here — see [PROGRESS.md](PROGRESS.md). For orientation, Phase 0 +
> Phase 1 + Phase 1.5 (§12) + Phase 2 (web/infra/async) + Phase 4 (Portfolio Workbench, §14) are built &
> deployed; **Phase 6 two-agent A2A discovery (§15) merged (v2.5.0)**; **Phase 5 COMPLETE + pre-GA
> security-reviewed** (5A real ATS résumé, 5B save-as-application, persist-Contact v2.6.0, 5C one renderer +
> master download, 4E pin-for-tailoring v2.7.0). **Phase 7 COMPLETE** — Job Discovery is now a web product
> feature (Jobs view: preferences → live loop → ranked matches → tailor-to-job), **latest contract v2.8.0**;
> see §15.6.
> Decisions captured in [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md).

CareerEngine converts raw, multi-decade career histories into quantified, STAR-formatted
portfolios and ATS-compliant tailored resumes, using a conversational "Grill Me" agent that
extracts real metrics instead of fabricating them.

---

## 1. Design tenets (and how this doc honors them)

| Tenet | Implementation |
|-------|----------------|
| **Quality without compromise** | Deep conversational probing (the "Grill Me" graph node) refuses vague answers and loops until numeric/structural metrics are extracted. Human-in-the-loop checkpoint every 5 turns validates the delta before it is committed. |
| **Extreme cost efficiency** | Tiered model registry. Cheap/free **Flash & Flash-Lite** do parsing, scraping cleanup, tailoring, and UI rendering. The expensive **deep-reasoning tier** is reserved strictly for metric extraction and is *opt-in*. |
| **Device-agnostic flow** | One ADK workflow core. Two thin frontends (CLI, Streamlit) share a single cloud state layer. The core has zero UI imports. |
| **Privacy-first, BYOK** | Real identity (Firebase Auth) → stable `user_id`. Users bring their own Gemini key; the key lives encrypted in Secret Manager, never in Firestore. Inference is billed to the user's key. |

> **Changed from the original prompt:** the original used `tenant_id = SHA-256(api_key)` and the
> label "zero-knowledge." That is replaced by real auth + per-user Secret Manager storage (see
> [§5](#5-identity-secrets--privacy)). The "zero-knowledge" claim is dropped as inaccurate — data
> is stored isolated-per-user but readable by the platform; it is **privacy-first**, not zero-knowledge.

---

## 2. Layered architecture & separation of concerns

The cardinal rule (from the plan's anti-God-Object constraint): **every workflow node is an atomic
function `(CareerEngineState) -> CareerEngineState`.** UI, persistence, identity, and model access
are all injected, never imported, into the workflow layer.

```
┌──────────────────────────────────────────────────────────────────┐
│  PRESENTATION (swappable)                                          │
│   main.py (CLI)            main.py (Streamlit web workspace)       │
└───────────────┬───────────────────────────┬──────────────────────┘
                │   calls Runner only        │
┌───────────────▼───────────────────────────▼──────────────────────┐
│  ORCHESTRATION — Google ADK 2.0 Workflow Runtime                  │
│   workflows/discovery_graph.py   (graph: nodes, edges, router)    │
│   workflows/nodes.py             (atomic state->state nodes)      │
│        ingest → grill → checkpoint(HITL) → finalize               │
└──────┬───────────────┬───────────────┬───────────────┬───────────┘
       │ injected       │ injected      │ injected      │ injected
┌──────▼─────┐  ┌───────▼──────┐ ┌──────▼──────┐ ┌──────▼─────────┐
│ models/    │  │ auth/        │ │ database/   │ │ tools/         │
│ registry   │  │ AuthProvider │ │ Firestore   │ │ pdf_renderer   │
│ (tiers)    │  │ KeyVault     │ │ SessionSvc  │ │ web_scraper    │
└──────┬─────┘  └───────┬──────┘ └──────┬──────┘ └──────┬─────────┘
       │                │               │               │
┌──────▼────────────────▼───────────────▼───────────────▼──────────┐
│  GOOGLE CLOUD                                                      │
│   Gemini API · Firebase Auth · Firestore · Secret Manager ·       │
│   Cloud Run · Artifact Registry · Cloud Scheduler · Cloud Logging │
└───────────────────────────────────────────────────────────────────┘
```

**Dependency direction is strictly downward.** `workflows/` may import `schema`, `models`, and the
*interfaces* in `auth`/`database`/`tools` — never Streamlit, never a concrete Firestore call inline.

---

## 3. Directory structure (revised)

Changes vs. the original prompt are marked `← NEW` / `← CHANGED`.

```text
career-engine/
├── .env.example
├── Makefile                      # build-test-deploy lifecycle
├── pyproject.toml                # pinned deps (pip+venv)        ← CHANGED (was implicit)
├── main.py                       # CLI + Streamlit entry points
├── config.py                     # settings, client factories
├── schema.py                     # Pydantic state (the contract)
├── auth/                         #                                ← NEW (replaces key-hash tenancy)
│   ├── provider.py               #   AuthProvider interface -> user_id
│   ├── firebase_auth.py          #   web identity
│   ├── cli_auth.py               #   device/loopback OAuth for terminal
│   └── key_vault.py              #   store/fetch BYOK Gemini key in Secret Manager
├── models/                       #                                ← NEW
│   └── registry.py               #   ModelTier -> model id; capability detection
├── database/
│   └── firestore_session.py      #   custom ADK SessionService adapter
├── workflows/
│   ├── discovery_graph.py        #   ADK 2.0 Workflow graph + router
│   └── nodes.py                  #   atomic BaseNode execution logic
├── tools/
│   ├── pdf_renderer.py           #   Jinja2 -> HTML -> PDF
│   └── web_scraper.py            #   two-step JD scrape (fetch + Flash clean)
├── jobs/                         #                                ← NEW
│   └── pending_action_sweep.py   #   14-day async "applied" sweep (Cloud Scheduler job)
├── skills/
│   └── cloud_ops/
│       ├── SKILL.md
│       └── reference/
├── templates/
│   └── classic_resume.html
├── infrastructure/
│   ├── modules/                  #   reusable terraform modules
│   ├── envs/{dev,prod}/          #   per-environment roots       ← CHANGED (explicit envs)
│   └── README.md
└── evaluation/
    ├── test_config.json
    └── user_simulator.py
```

---

## 4. The ADK 2.0 workflow core

ADK Python **2.0 GA** ships a graph-based **Workflow Runtime** with routing, fan-out/fan-in, loops,
retry, state management, **human-in-the-loop**, and nested workflows — which is exactly the shape of
the discovery loop. (Verify exact import paths against the pinned `google-adk` version at install
time; treat the snippets below as structural, not copy-paste-final.)

### 4.1 State (the contract — `schema.py`)
`CareerEngineState` is the single object threaded through every node. It carries `current_phase`,
`current_pillar`, `target_competencies`, `extracted_star_stories`, `active_gaps`, and
`question_count`. **It contains no secrets and no UI state.** Identity (`user_id`) is passed via the
ADK session/context, not embedded in the resume state.

**Strict typing is non-negotiable.** *Everything* crossing a boundary is a Pydantic model.
Sub-agents (dev-time) and runtime nodes communicate via **serialized JSON validated against these
models** — `Model.model_validate_json(...)` on the way in, `model.model_dump_json()` on the way out.
Free-text hand-offs are forbidden; that discipline is what prevents the schema drift that kills
multi-agent systems.

**Version the contract.** `config.py` exposes `CONTRACT_VERSION` (semver). Every persisted document
and every inter-agent message is stamped with it. A consumer that sees an unknown major version
refuses rather than mis-parses — so an architecture pivot (e.g. centralized → decentralized monitor)
is detectable, not silently corrupting.

### 4.2 Nodes (atomic, `(state) -> state`)
- `ingest_node` — parse raw history (Flash-Lite/Flash); seed pillars & gaps.
- `execute_grill_turn_node` — **deep tier**; one probing question, validates the answer contains real
  metrics (scale, latency Δ, blast radius, efficiency Δ), updates a `StarStory`, increments
  `question_count`. Tone = senior peer, never names "STAR" to the user.
- `user_checkpoint_node` — the **Hydration Point**. Summarizes the delta of the last 5 turns, asks
  the user to verify, and only on confirmation commits to the master record. This is the HITL gate.
- `finalize_master_resume_node` — assembles validated state → master resume.
- `tailor_node` — given a cleaned JD, produces a targeted resume (Flash).

### 4.3 Router & the 5-turn brake
```python
def discovery_router(state: CareerEngineState) -> str:
    if state.current_phase == "complete" or not state.active_gaps:
        return "finalize_master_resume"
    # Checkpoint brake: every 5 turns, hydrate + verify before continuing
    if state.question_count > 0 and state.question_count % 5 == 0 \
            and state.current_phase != "checkpoint":
        return "user_checkpoint_node"
    return "execute_grill_turn_node"
```
The brake prevents user fatigue *and* runaway LLM looping, and forces periodic human verification.

---

## 5. Identity, secrets & privacy

**Decision: real auth via Google Cloud Identity Platform (the enterprise superset of Firebase Auth),
not key-hash tenancy.** Identity Platform gives stable identities, multiple providers (Google, email,
OIDC/SAML later), and integrates natively with the GCP IAM/Secret Manager stack.

```
User ──login──> Identity Platform ──> stable user_id (the tenant key everywhere)
User ──BYOK──> Gemini API key ──encrypt──> Secret Manager  (id: ce-key-{user_id})
                                              │
Firestore docs keyed by user_id  <───────────┘ (key NEVER stored in Firestore)
```

Why this beats the original `SHA-256(api_key)` approach:
- **Key rotation no longer orphans data** — identity is stable, the key is just a swappable secret.
- **The 14-day async sweep works** — a detached Cloud Scheduler job can resolve `user_id`s and fetch
  each user's key from Secret Manager to act on their behalf. (A pure zero-knowledge / client-encrypted
  design would have made server-side monitoring impossible — that tradeoff is why ZK was rejected.)
- **Least privilege**: Terraform grants the Cloud Run service account
  `roles/secretmanager.secretAccessor` so the app can read keys at runtime, and nothing broader.

**CLI auth nuance:** the terminal can't run a browser redirect easily, so `auth/cli_auth.py` uses a
device-code / loopback OAuth flow, caching a short-lived token locally. A documented power-user escape
hatch allows a local `user_id` + direct key for fully-offline dev.

**Privacy posture (honest):** per-user isolation, key encrypted at rest, inference billed to the user,
no cross-tenant data sharing. This is **privacy-first**, explicitly **not** zero-knowledge.

---

## 6. Model-agnostic Capability Registry

**No feature ever names a model.** Features declare the *capabilities* they need; the registry resolves
capabilities → the best available model for the current access mode. This is what keeps us alive as
Google churns the lineup (1.5 retired; 2.0 Flash shut down 2026-06-01; 3.x shipping).

### 6.1 Capabilities, not models
```python
class Capability(str, Enum):
    REASONING_HIGH = "reasoning_high"   # multi-step extraction, validation
    SPEED_FAST     = "speed_fast"       # summaries, tailoring, UI
    BULK_CHEAP     = "bulk_cheap"       # scrape cleanup, parsing
```
Feature → capability map:

| Feature / node | Required capability |
|----------------|---------------------|
| `execute_grill_turn_node` (Grilling) | `REASONING_HIGH` |
| checkpoint summary, tailoring, ingestion | `SPEED_FAST` |
| JD scrape cleanup, bulk parse | `BULK_CHEAP` |

### 6.2 Two access modes
- **Free Mode (managed keys):** the platform's own keys, routed to the **highest available free-tier
  model (Flash / Flash-Lite)**. Fully functional out of the box.
- **BYOK Mode:** the user's key (Secret Manager). Unlocks paid models when their key has billing.

### 6.3 Graceful escalation (the upgrade prompt)
When a `REASONING_HIGH` task in Free Mode cannot succeed, the node returns a typed
`UpgradeRequired` signal (never a crash, never silent degradation) and the UI shows:

> *"This task requires advanced reasoning. Please provide your API key or upgrade to continue."*

Two concrete triggers in `execute_grill_turn_node`:
1. **Resolver shortfall** — the registry has no sufficiently-capable free model for `REASONING_HIGH`.
2. **Pro-escalation gate** (v2.3.0) — a single entry accumulates `_MAX_FLASH_GRILL_ATTEMPTS`
   (=6) failed metric-extraction attempts. Per-entry failures are tracked in
   `CareerEngineState.grill_attempts` and reset when the entry yields a validated metric. The
   threshold sits **above** the 5-turn checkpoint boundary, so the checkpoint brake (pause +
   summarize) always fires first; escalation is the considered next step for a user who stays
   vague on the same entry *past* a checkpoint. BYOK mode never trips this gate — `REASONING_HIGH`
   already resolves to Pro, so there is nothing to escalate to. The eval harness measures how
   often it fires as the **Pro-escalation rate** (`evaluation/user_simulator.py`); CoT-prompt
   tuning aims to keep it low by helping users produce a metric before the threshold.

### 6.3.1 Grill loop quality (v2.4.0, from live-run feedback)
Three behaviours were hardened after a real résumé run:
- **Frontier prioritization** — `_frontier_sort_key` ranks entries-needing-work by
  `(recency, substance, start-year)`: a **current role** (empty `end_date` → "present")
  outranks any dated one, and experience-type weight (`full_time`/`leadership` >
  `internship`/`education`/`other`) breaks recency ties. This is robust to the messy
  dates a résumé parser emits and stops the loop from grilling a recent trivial entry
  (e.g. a one-day volunteer gig) before your current senior roles.
- **Grill memory** — `CareerEngineState.grill_answers` accumulates the user's answers
  per entry; metric extraction sees **all** of them (so a number given across turns
  assembles) and the follow-up question is told not to re-ask for anything already
  provided. Cleared for an entry on a validated metric.
- **Graceful model errors** — `integration.model_client` wraps provider failures in a
  typed `ModelAPIError` (with `is_rate_limited` + `retry_after_seconds`); the CLI turns
  a quota/`429` into a friendly, resumable message instead of a crash.

### 6.4 The Flash-Lite pivot (prompt engineering > model size)
Baseline is **Flash-Lite**. We close the gap to "Pro" with **Chain-of-Thought system prompts**, not
bigger models: force the reasoning steps (decompose the claim → demand a metric → check plausibility →
restate as STAR) into the prompt. A highly-tuned Flash node with explicit CoT delivers most of what
people reach for Pro to do. Pro/`REASONING_HIGH-paid` is the *exception*, invoked only when CoT-on-Flash
demonstrably can't validate the extraction. Prompts live in versioned files, treated as code.

---

## 7. Tools

- **`web_scraper.py` — two-step scrape.** (1) Fetch raw JD HTML. (2) Use **Flash-Lite/Flash** to
  strip nav/sidebars/culture fluff down to functional requirements + hard skills. Prevents
  "context pollution" where the agent fixates on a mission statement instead of required skills.
- **`pdf_renderer.py` — Jinja2 → HTML → PDF.** Maps the *validated* state JSON into a Jinja2 context
  for `classic_resume.html`, then renders via headless Chrome. Guards against raw LLM markdown
  breaking layout (sanitize/escape before injection; never trust model output as HTML).

---

## 8. Async "Pending Action" sweep (Option A)

`jobs/pending_action_sweep.py`, triggered by **Cloud Scheduler** → a Cloud Run job:
1. Query Firestore for applications in `applied` status with `applied_at` > 14 days.
2. Flag each as a `pending_action` on that user's workspace document.
3. (Optional) draft a follow-up suggestion using the user's key from Secret Manager.
Surfaced on the Streamlit dashboard as a "Pending Action" item. Enabled cleanly *because* identity is
server-resolvable (see §5).

### 8.1 Outcome learning — positive-reinforcement only (Phase N — deferred value-add, NOT a v1 blocker)
> Wanted but not on the critical path. Reuses §8's async-job + application-tracking infra, so it's cheap
> to add *once Phase 2 exists*; nothing else depends on it. Build when feasible.
When a tailored application **reaches the interview stage**, that's a (weak) positive signal about the
résumé's format + wording for that **job type**. An async job learns from these wins — **per user, per job
type** — and shows the user what it found.

**Signal & ethics — POSITIVE ONLY (core constraint):**
- Learn **only** from positive outcomes (reached interview). **Never penalize** a format/wording that
  didn't get an interview — rejection is confounded (comp, timing, volume, internal candidates, bias) and
  is *not* a negative label. We accumulate evidence *for* patterns, never *against*.
- Outcome is **user-reported** ("I got an interview") — reliable and honest; don't auto-detect.
- Learnings are **observations/suggestions, not rules** ("résumés that got you interviews for backend
  roles tended to lead with scale metrics") — correlation ≠ causation, and samples are small.

**Mechanics:**
- Application record gains an outcome transition `applied → interview` (positive). Reuses §8's tracking +
  async-job infra (Cloud Scheduler → Cloud Run).
- `jobs/outcome_learner.py`: for each interview-reaching application, extract features of the tailored
  résumé used (format choices, phrasing/keyword patterns, which achievements were emphasized) and
  reinforce them in the user's per-job-type learning profile (evidence counts FOR).
- Per-user store: Firestore under `user_id`, `learnings/{job_type}` — **private by default** (privacy-first §5).
- Feed-forward: the tailor node may use these learnings to inform future tailoring for that job type
  (closes the loop).

**Transparency & sharing:**
- Show each user, per job type, exactly what was learned **from their own data**.
- **Private unless opted in.** A user may contribute to a **global DB** of what works per job type.
  Contributions are **anonymized + aggregated — patterns/features only, never raw résumés or PII** (strip
  names, companies, identifying text); a sanitization step gates every contribution.
- Opt-in global learnings can inform tailoring suggestions for everyone, per job type.

**Honest caveats (the design must reflect these):**
- **Positive-only → selection/survivorship bias:** surfaces "what was present when it worked," not proven
  cause. Frame as suggestions, never guarantees.
- **Cold-start / low volume:** global per-job-type learnings need enough contributors — gate display on a
  minimum sample size and label confidence.
- **Bias-amplification risk:** if ATS/HR preferences encode bias, reinforcing them could entrench it;
  transparency + "suggestion not rule" mitigates — revisit if patterns look discriminatory.

---

## 9. Infrastructure (Terraform, IaC-first)

`infrastructure/` defines, not scripts, the environment — `envs/dev` and `envs/prod` so the whole
platform can be stood up or torn down with one command.

| Layer | Component | Purpose |
|-------|-----------|---------|
| Compute | Cloud Run | Serverless, auto-scaling, event-driven agent host |
| Persistence | Firestore (Native) | Agent state + resume metadata, isolated by `user_id` |
| Secrets | Secret Manager | Per-user BYOK keys; SA granted `secretAccessor` via TF |
| Registry | Artifact Registry | Container images |
| Identity | Firebase Auth | Stable user identity |
| Scheduling | Cloud Scheduler | Triggers the 14-day sweep |
| Networking | (optional) Global LB + IAP | Only if a security perimeter is enabled |
| Observability | Cloud Logging/Monitoring | Debug agent "hangs" in the graph |

A root **`Makefile`** wraps `lint / test / build / deploy / destroy`.

---

## 10. Testing & evaluation

- **`evaluation/user_simulator.py`** drives the ADK 2.0 `UserSimulator` to role-play an applicant who
  gives *vague* answers, asserting the grill node pushes back and ultimately extracts numbers.
- **`test_config.json`** holds eval params (scenarios, pass thresholds).
- Unit tests per node (pure functions → trivially testable). Integration test wires Runner +
  in-memory/fake session. Adversarial review pass before merge (see parallelization strategy).

---

## 11. Two meanings of "agents" — don't conflate them

1. **Runtime agents** = the *product*: ADK LlmAgents/Workflow nodes that talk to the user.
2. **Dev-time sub-agents** = how we *build* it: parallel Claude Code agents writing code.

The parallelization strategy in [REFINED_PROJECT_PLAN.md §Parallelization](REFINED_PROJECT_PLAN.md)
is about (2).

---

## 12. Resume-aware ingestion & progressive discovery (Phase 1.5 / contract v2.0.0)

> Status: **spec, not yet built.** Lands as Phase 1.5; requires a backward-compatible contract bump to
> v2.0.0. Replaces the pillar-based `active_gaps` with a role-based `work_timeline`.

### 12.1 Premise
Most users start from an **existing (often stale) resume**, not a blank page. The platform should (a)
ingest that resume, (b) quantify what's already there, and (c) **recover the undocumented present** —
everything done between the resume's last refresh and `reference_date` (now). The freshest, most
promotable wins usually live in that gap.

### 12.2 Vision-first ingestion (not pdf→text)
The resume enters as a **document/image**, fed directly to a multimodal Gemini model (`SPEED_FAST` →
`gemini-2.5-flash`, natively multimodal, free-tier OK). The model reads layout — multi-column designs,
table/grid hacks, even a **photo of a printed resume** — and returns a structured timeline. This beats
`pdf→text` extraction, which flattens columns and drops tables. Rationale: don't build a brittle
layout-reconstruction pipeline; let the vision model do what it's good at.
- Pipeline: `file/photo → (rasterize pages if needed) → multimodal Flash → work_timeline JSON`.
- Adds a **multimodal entry point** to the model-client adapter (today text-only `.generate(...)`).
- DOCX (no native image) is the awkward case → convert-to-PDF later; support PDF + images first.
- **Privacy:** the image is PII; sent on the user's key (BYOK) or platform key (FREE); we persist only
  the **structured timeline**, discarding the raw image after parsing.
- Vision can misread a date / "Present" → **confirmed conversationally** (see 12.3), not trusted blindly.

### 12.3 The gap is just more roles (unified model)
No special "gap sub-flow." The unit of grilling becomes the **role/engagement** (not an abstract
pillar). Flow:
1. Vision ingest → `work_timeline` of roles with dates + existing bullets.
2. **Discovery turn** — seeded by the latest parsed end-date, confirmed by asking: *"Your resume runs
   through Acme (2022). When did you last refresh it, and what have you done since?"* → newly named
   roles are **appended to the same `work_timeline`**.
3. **Uniform role-by-role grilling** — every role (old or newly discovered) runs the same STAR +
   metric extraction. Already-quantified bullets are marked validated and **not re-asked** (anti-fatigue).
4. Tone stays a supportive peer on gaps (sabbatical/caregiving/layoff) — *"what were you focused on,"*
   never *"why the gap."*

> Terminology: **role/engagement** = past work (grilled). **job description** = a target posting we
> tailor against. Keep them distinct.

### 12.4 Progressive discovery (the return loop)
- **Discovery completeness — a NUDGE, never a hard gate.** Applying and tailoring are **never blocked.**
  If someone needs to manage applications right now with a half-filled portfolio, they can — autonomy
  first. `discovery_completeness(state, reference_date)` is a derived signal: how much of the trailing
  5-year window `[now − 5y, now]` is documented (the 5 years is a **lookback window, not an amount to
  accumulate**). It drives a **persistent, consent-respecting nudge**: each apply/tailor action while the
  window is incomplete reminds the user — *"tailored resumes come out noticeably stronger once the rest of
  your recent history is filled in — do it now / remind me later."* Shown every time, snooze-able, never enforced.
  - 18 months in → that *is* "complete" for them; the nudge quiets. 25-yr veteran → only the last 5 yrs
    count toward the meter; older is optional backlog. Zero jobs → projects/education entries count (12.6).
  The same signal serves everyone 0–25+ yrs; it informs the nudge + progress meter — it does **not** gate.
- **Backward-chronological continuation:** a **grill frontier** pointer tracks how far back we've
  grilled. Each return session offers the next ungrilled role *older than the frontier*. Default is
  backward (recent matters most, freshest memory) but a role is **jumpable** on request.
- **Soft horizon:** deep-grill ~last 10–15 years; older roles default to "summarize-only" (diminishing
  return). Signal it rather than marching to 1998.
- **Login nudge:** "work on your resume" — a sibling of the §8 Pending Action sweep, surfaced on the
  same dashboard; **consent-respecting** (snooze / "don't remind for N days"). Engine logic lives in
  Phase 1.5; the surface is Phase 2 (CLI can also prompt on launch).
- **Progress meter:** "last 5 years: 80% covered" / "portfolio depth: 12 yrs" — derived from the
  timeline; the dopamine that drives the return loop.

### 12.5 Contract delta (v2.0.0 — additive, replaces pillar machinery)
`CareerEngineState` (sketch):
- **add** `work_timeline: list[Entry]` where `Entry = {entry_id, type, title, org, start_date,
  end_date|"present", source: resume|discovered, bullets: list[str],
  status: documented|needs_quantifying|grilled|summarized|skipped}`. `type ∈ {full_time, internship,
  project, research, open_source, leadership, part_time, education, other}` — an **experience entry** is
  the grillable unit, not just a job, so internships/projects/research/leadership all count (see 12.6).
- **add** `coverage_through` (freshness boundary), `reference_date` (**injected clock** — nodes never
  call `datetime.now()`; the CLI/entry layer stamps it for determinism + testability).
- **add** `role_id` to `StarStory` (link story→role; keep `pillar` as a competency tag).
- **replace** pillar fields (`target_competencies`, `active_gaps`, `current_pillar`) with role-based
  equivalents; `grill_frontier`/`current_role_id` replaces `current_pillar`.
- `is_apply_ready` and the progress meter are **derived** (pure functions), not stored.
This reworks WS-A's grill loop + router and the ingest prompt; it's the deliberate v2.0.0 amendment.

### 12.6 Early-career (0–5 years) — no "must have 5 years" trap
Early-career users (0–5 years, including zero jobs) are first-class. Two things make this work, and
neither special-cases them — they're the general rules:
- Discovery is a **nudge, not a gate** (12.4): nobody is blocked from applying, and nobody is ever told
  "come back when you have 5 years." The trailing-5-year window is just what the completeness signal /
  nudge measures.
- "Role" is generalized to **experience entry** (12.5), so people with little/no formal work still have
  grillable material.

What that looks like in practice:
- **Ingest** extracts education, internships, capstone/side **projects**, research, open-source,
  leadership (clubs/TA), competitions — not just employment. A grad's resume is education-heavy; the
  vision prompt must capture these entry types.
- **Discovery turn** is reframed for them: not "what jobs since 2022?" but *"beyond coursework, what
  did you build, lead, or contribute to?"* — surfacing projects/hackathons/TA/research they didn't
  think to list.
- **Apply-readiness is not "5 years of jobs."** Generalize: ready = **≥ N validated experience entries
  of any type, OR all available entries grilled** (whichever comes first). So a grad becomes apply-ready
  by quantifying a few internships/projects. The "last 5 years" window still applies to those with a job
  history; for grads the relevant window is school + internships and the gate falls back to entry-count.
- **Metrics look different** and the validator must accept them: users/downloads/stars, team size,
  competition rank, dataset/scale, GPA where relevant, research citations — extend
  `nodes._contains_real_metric` patterns beyond the latency/% / $ set it ships with.
- **Value framing differs:** for grads the win isn't "recover the gap," it's "turn thin project bullets
  into quantified, recruiter-legible achievements + surface forgotten work." Same griller, different emphasis.

---

## 13. Future / v2.0 backlog (NOT in scope for v1)

Captured so the vision is recorded; explicitly **deferred** — do not build in v1.

- **Interview preparedness.** When a tracked application reaches "interview scheduled" at company X for
  role Y, research (web search) the typical interview shape for that company+role — coding round, system
  design, behavioral — and run **mock interviews**: the agent asks representative questions, the user
  answers, the agent gives feedback. Reuses the conversational/grilling machinery + the user's portfolio
  (for behavioral/STAR answers), the web-search tool, and the existing application tracking / Pending
  Action surface (§8). Uses the user's key; same privacy posture. **Distant future, not v1.**

---

## 14. Portfolio Workbench (Phase 4) — visible, navigable, user-steerable career data

> Status: **active** design for upcoming work. Motivated by live web use (2026-07-04):
> the left panel is mostly empty; reverse-chronological discovery under-captures depth at long
> tenures; and the user cannot see what the system has recorded about them. Grooming/build specs
> live in [GROOMING.md](GROOMING.md) Phase 4; status in [PROGRESS.md](PROGRESS.md).

### 14.1 The problem (from real use)
- **Wasted navigation space.** The Streamlit sidebar holds only "signed in / sign out"; the main view
  is a single scrolling column. There is no way to move between the workspace, the recorded portfolio,
  a grill, and the tailor except via buttons that reset the view.
- **Long-tenure blindness.** Discovery walks `work_timeline` newest-first and grills entry-by-entry. A
  person who spent seven years at one org appears as **one** entry — a handful of bullets that cannot
  represent the plethora of distinct projects done there. The user remembers more, but there is no way
  to add a project and steer the grill onto it.
- **No portfolio mirror.** Everything the grill extracts (`StarStory` per `entry_id`) is persisted but
  never shown back. The user cannot review, trust, or correct what has been recorded.

### 14.2 Key insight — the model already supports this
The persisted discovery session (`CareerEngineState`, read via `web/session_loader.py`) is already the
**portfolio of record**. No new storage or contract change is needed for the read/steer features:
- `work_timeline: list[Entry]` **is** the experience tree. A long tenure is represented by additional
  `Entry` rows (e.g. one `FULL_TIME` + several `PROJECT` entries sharing an `org`), each independently
  grillable.
- `Entry.source == "manual"` already models a user-added project — the schema anticipated this.
- `StarStory.entry_id` links every recorded achievement to its `Entry` → grouping stories by entry is a
  pure helper, no persistence change.
- `grill_frontier` is documented **jumpable**: "setting it explicitly targets that entry next." Steering
  the grill onto a chosen experience is a frontier write the router already honors — no new routing.

### 14.3 Design decisions
- **AD-14.1 — Session state is the portfolio of record.** The web app reads `work_timeline` +
  `extracted_star_stories` directly from the persisted `CareerEngineState` for all navigation and
  per-entry views. We do **not** duplicate portfolio content into `UserWorkspace` (which stays scoped to
  applications + pending actions). Single source of truth; no sync problem.
- **AD-14.2 — All manual portfolio edits go through a thin, tested mutation seam.** Adding/editing an
  `Entry` and setting `grill_frontier` are **read-modify-write** operations on the persisted session
  state, mirroring the async-bridge pattern in `session_loader`/`workspace_store` (sync façade over an
  async client, stamped with `CONTRACT_VERSION`, no secrets). The UI **never** writes session state ad
  hoc — it calls the seam. Keeps identity/contract discipline and keeps the write path unit-testable
  without Streamlit.
- **AD-14.3 — `grill_frontier` is the steering mechanism.** "Grill me about this experience" sets the
  frontier to the chosen `entry_id` before the next grill turn; the existing router advances from there.
  No new graph edges.
- **AD-14.4 — Contract impact.** The sidebar (4A), portfolio view (4B), steerable grill (4C), and manual
  add (4D) require **no contract change** — they surface and steer existing fields. Only the deferred
  "highlight/pin an experience for tailoring priority" (4E) adds a field (`Entry.highlighted`), an
  **additive minor** bump gated behind a `CONTRACT_VERSION` change when it is actually built.

### 14.4 Concurrency caveat (demo posture)
The mutation seam and a concurrent grill turn both write session state → last-write-wins. Acceptable on
the single-user demo (`max_instances=1`, one pinned Streamlit session; see [SECURITY.md](SECURITY.md)).
Multi-user correctness needs the same session-isolation work already tracked for the global model-client
factory — do not treat the workbench as the thing that introduces the race.

---

## 15. Two-agent (A2A) job discovery — decoupled Scout ⇄ Primary over MCP (contract v2.5.0)

> Status: **built** (Phase 6, branch `feat/discovery-a2a`; see [PROGRESS.md](PROGRESS.md) for state).
> The `discovery/` package; runtime is separate from the grill/tailor graph and reuses the shared contract.

### 15.1 Why this is inevitable (not rubric-driven)
The multi-user vision — *N* signed-in users, each with a stateful agent, all negotiating a shared live job
market — makes a **stateless data-fetch tier** unavoidable. You cannot fan a stateful per-user reasoning
loop directly at a rate-limited external source and stay correct or affordable. So the design **decouples**:

- **Primary agent** (stateful, per-user): owns `SessionPreferences` + `InteractionLedger`, evaluates, and
  orchestrates. Routed to the expensive **REASONING_HIGH** capability (Pro on BYOK).
- **Scout agent** (stateless Fetcher): given a self-contained `ScoutDirective`, returns a batch. Keeps **no**
  memory, so one Scout fleet can serve many Primaries and scale/replace freely.

This is the same "two meanings of agents" discipline as §11: the **workflow** is the deterministic loop; the
**model** is invoked only where judgement is needed (the Primary's evaluation).

### 15.2 The MCP server is the security boundary (not just a tool bus)
The Scout reaches job data **only** through a real, separate-process **MCP server** (`discovery/mcp_server.py`,
FastMCP, stdio) exposing `search_jobs` + `fetch_jd`. The untrusted network fetch lives *inside* that server —
never in the agent's reasoning process. Today that boundary is enforced by reusing the scraper's **SSRF
guard** (`_assert_safe_url`: scheme allow-list + resolve-and-reject private/loopback/metadata addresses) on
the caller-controlled `fetch_jd` path, and by hitting only a **fixed source host** for search (query is
URL-encoded, host is never attacker-controlled). Roadmap: Podman/zero-trust sandbox around the server process.
The source is a **live, key-free** public board (Remotive) so the demo carries **no secrets** — aligned with
the Kaggle "no API keys in code" mandate. The tool logic (`discovery/job_source.py`) is pure + injectable, so
the whole data layer is unit-tested offline; `InProcessMcpClient` dispatches through the genuine FastMCP tool
machinery (validation + serialisation) for a key-free, subprocess-free demo/test path.

### 15.3 The typed A2A contract + the bounded adversarial loop
Inter-agent messages are **validated Pydantic models, never prose** (contract v2.5.0): `ScoutDirective` in,
`JobOpportunity` batch out, `EvaluationDiff` back. The Primary evaluates each batch in two tiers:

1. **Deterministic HARD_REJECT gate** (`hard_reject_reason`) — ledger already-applied / dismissed-company /
   absolute-dealbreaker keyword. Cheap, idempotent, runs before any inference (never wastes a model call on
   known noise).
2. **Agentic evaluation** of survivors → `ACCEPTED` / `SOFT_REJECT` + one-line `ai_rationale`. Injectable
   `BatchEvaluator`: the key-free `HeuristicEvaluator` (default; keeps the pipeline demoable and CI-green) or
   the `ModelEvaluator` (one REASONING_HIGH call for the whole batch — cost-bounded — that **falls back to
   the heuristic on any parse/API error**, so a flaky model never crashes discovery).

`evaluate_batch` (pure) stamps `match_status`+`ai_rationale`, sets the `ScoutBatchStatus`, and computes the
refined `next_directive` (folding missed companies into the exclusion set). `PrimaryAgent.discover()` runs the
loop with **MAX_ITERATIONS=3** (bounds cost + guarantees progress), dedupes by `job_id`, and stops at
`desired_total` or the cap. `next_directive is None` is the A2A "loop satisfied" signal.

### 15.4 Idempotency + closing the loop
Every posting carries a stable content-hash `job_id` (`make_job_id(source, external_id)`), so the ledger
never dupes across worker restarts. Accepted jobs persist via a `LedgerStore` (`InMemoryLedgerStore` default;
sync `FirestoreLedgerStore` at `discovered_jobs/{uid}/jobs/{job_id}`, no secrets); stored ids hydrate the next
run's ledger so re-runs hard-reject already-seen jobs. The discovered `JobOpportunity.raw_description` is
exactly the `jd_source` the existing/deployed **Tailor** consumes, so `discover --tailor-session` closes
**discover → tailor** with no new résumé code.

### 15.6 Web surface — Job Discovery is a product feature (Phase 7)
Discovery began as a CLI demo (`career-engine discover`); Phase 7 brought it into the web app as a **Jobs
view** with **no change to the engine** (`discovery/scout.py`/`primary.py`/`job_source.py`/`mcp_server.py`
are untouched). The web surface adds only: a persisted rubric (`UserWorkspace.discovery_preferences`, v2.8.0,
`web/preferences_store.py`); a **Jobs** nav view (`web/jobs.py` pure view-model + renderer, `web/streamlit_app.py`
`_render_jobs`) that runs the live loop on the user's **BYOK key** via the persistent `run_async` loop
(`web/jobs_runner.py`), renders **✅ Strong / 🟡 For review** with the AI rationale, and persists accepted jobs
(idempotent, `LedgerStore.list_accepted` for display on entry); and a per-job **"Tailor résumé to this"** that
hands the posting's JD to the existing Tailor (`job_tailor_index` → the keyed JD input). So discovery is now
**grill → jobs → tailor** in the UI, not a terminal-only demo.

**HITL steering (post-Phase-7):** each job also has a **"Not interested"** action that dismisses the company —
it disappears from the current view immediately (session hide-set) and is persisted to the ledger
(`LedgerStore.add_rejected_company`, first writer to `InteractionLedger.rejected_companies`; Firestore uses an
atomic `ArrayUnion`). The Primary's deterministic hard-reject gate already consumes that set, so **future**
runs (CLI and web) never re-surface a dismissed company. Symmetrically, a **"Keep this"** action on a
for-review (soft) match promotes it into Strong matches immediately (session kept-set) and persists it as
ACCEPTED (`record_accepted`) so it survives + shows on the next visit — a human override of the Primary's
soft-reject. Together these are the accept/reject slice of the discovery HITL controls (a full override/TTL
dashboard remains roadmap).

### 15.5 Deliberate deviations (deadline-safe cut; roadmap noted)
- **Package named `discovery/`**, not the literal `mcp/`+`agents/` paths first sketched — a top-level `mcp/`
  dir would shadow the installed `mcp` SDK on `sys.path`. One feature, one package.
- **Two MCP transports, both real:** `InProcessMcpClient` (default — real FastMCP dispatch, no subprocess)
  and `StdioMcpClient` (spawns `python -m discovery.mcp_server` as a **separate process** over MCP stdio —
  genuine out-of-process A2A, live-verified; both transports raise identically on a tool error via
  `_unwrap_tool_result`). `StdioMcpClient` opens a fresh session **per call** (a cold subprocess start each
  time) — fine for a demo, but a **persistent session** is the pre-at-scale optimisation. **Remote/network
  A2A** (server on its own host) and the
  **Podman sandbox** around that process remain roadmap. Async background worker + spin-down, full HITL
  dashboard (TTL/override), and multi-user session isolation are also roadmap. The deployed
  grill→jobs→tailor path is the untouched safety-net floor.

---

## 16. Web platform migration (Phase 10) — Streamlit → Next.js + FastAPI

> Status: **accepted decision, not yet built.** Last reviewed 2026-07-07. This section is the
> canonical rationale + decision record ("the short tech recommendation writeup") for replacing the
> Streamlit web surface. Build slices and acceptance criteria live in [GROOMING.md](GROOMING.md)
> Phase 10; sequencing in [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md) Phase 10; status is
> canonical in [PROGRESS.md](PROGRESS.md). No Phase-10 build ticket may be marked ✅ Ready until it
> traces to a decision recorded here.

### 16.1 The problem (why Streamlit is now the constraint)
Streamlit was the right *device-agnostic-for-agents* choice for the demo, but live use this cycle
showed it caps the product:
- **Auth fragility.** Native OIDC (`st.login`) hard-codes the `/oauth2callback` path and hides the
  callback exchange. A wrong redirect path silently returns the app shell (HTTP 200) and hangs — the
  exact custom-domain outage this cycle (BUG-1 sibling; see the deploy-config hotfix). We get no
  control over the session/cookie flow or the redirect-URI set.
- **Rerun model.** Every interaction reruns the whole script top-to-bottom. That forces the
  `web/async_runner.py` persistent-background-loop hack (root of BUG-1's "event loop is closed"
  class) and makes streaming, partial updates, and multi-step forms awkward — each submit is a full
  rerun of the page.
- **Layout / UX ceiling.** No real routing, limited component composition, no drag-and-drop, and
  weak inline-edit UX. This directly blocks the roadmap's interactive résumé editing (9H) and visual
  section editor (9M).
- **Implicit trust boundary.** UI state lives in `st.session_state`; the `st.user → user_id`
  identity edge is implicit, and durable state needs bespoke Firestore bridging.

### 16.2 Decision
**AD-16.1 — Adopt a Next.js (React, App Router) frontend over a FastAPI JSON API; retire the
Streamlit surface.** The Python **domain does not change** — only presentation and transport. This
was chosen over (a) staying on Streamlit and (b) FastAPI + server-rendered HTMX/Jinja. HTMX is
lighter and viable, but the roadmap's interactive résumé editor (9H) and drag-and-drop section
editor (9M) are React-shaped; a rich client earns its keep given that committed scope.

### 16.3 Design decisions
- **AD-16.2 — FastAPI is a thin HTTP layer over the already-built domain.** The discovery graph,
  portfolio/workspace stores, tailor, and résumé renderers are reused unchanged. FastAPI is natively
  async, so per-request handlers `await` the existing async stores directly — **removing the
  `asyncio.run`/background-loop bridge and the whole BUG-1 class of defect.** No business logic moves
  into the transport layer.
- **AD-16.3 — `schema.py` stays the single shared contract across the wire.** FastAPI request/response
  models are the existing Pydantic types (or thin DTOs derived from them), so `CONTRACT_VERSION`
  continues to gate compatibility end-to-end. The frontend consumes typed JSON (types generated from
  the OpenAPI schema); no hand-maintained parallel type set.
- **AD-16.4 — Auth moves to the API boundary with an explicit, controlled flow.** Two acceptable
  shapes were considered: (a) OIDC at FastAPI (Authlib / Google Identity) issuing an **httpOnly +
  Secure + SameSite** session cookie, or (b) **Firebase Auth** on the Next.js side passing a verified
  **ID-token bearer** to FastAPI. **Resolved for slice 10.1 → option (b), Firebase ID-token
  bearer verified at FastAPI** (decision finalized; the 10.1 build is not yet implemented). Rationale: `auth/firebase_auth.py::FirebaseAuthProvider` already
  implements exactly this trust boundary (verified token → `sub` → `user_id`) with a fully injectable
  verifier for network-free tests, and it mirrors today's `st.user["sub"] → user_id` edge — so it
  reuses proven code with no new cookie/callback/session machinery to build and audit. FastAPI reads
  the `Authorization: Bearer <id_token>` header, verifies via `FirebaseAuthProvider`, and resolves
  `user_id` at a single dependency. Option (a) was rejected for 10.1 as strictly more surface (a full
  server-side OIDC callback + cookie-session store) for no reuse. Either shape gives full control of
  callback + redirect URIs (fixing the class of bug that hung the custom domain); BYOK-key handling
  stays in `auth/key_vault.py` behind that boundary.
- **AD-16.5 — The grill turn streams over SSE (WebSocket only if bidirectional need appears).** The
  interactive grill is the one flow that benefits from token/step streaming; FastAPI serves it as
  Server-Sent Events over the existing `DiscoverySession`, preserving current grill semantics
  (frontier steering, checkpoints) with no graph changes.
  - **Transport shape (build 10.4).** `POST /api/grill` **records** the user's input into the durable
    canonical session (`web-{user_id}`) and does **not** run the graph: `action="start"` creates the
    session from the history, `action="answer"` patches `pending_user_answer`, `action="confirm"` sets
    `checkpoint_verified`. The user's answer therefore travels in the **request body**, never a URL query
    string — so grill answers (PII) never land in access logs. `GET /api/grill/stream` (EventSource-native,
    no body) then **runs** the pending turn sequence by looping `DiscoverySession.advance()` and emits one
    SSE `event: turn` per completed turn, then a terminal `event: done`. Because the grill node returns a
    whole turn (no intra-turn tokens, and no graph changes), the stream carries **per-turn step events**,
    not sub-token deltas. The auto-advance loop mirrors the Streamlit driver exactly (advance only after a
    story is accepted; bounded by `_MAX_AUTO_TURNS`; stop on next-question / checkpoint / complete /
    upgrade). The "currently grilling" label is `_effective_frontier_label` (BUG-2), extracted to a
    Streamlit-free module so both the API and `web/grill_ui.py` share one implementation.
- **AD-16.6 — Deploy topology stays Cloud Run-first.** FastAPI as a Cloud Run service; Next.js as
  static/SSR on Cloud Run (or Vercel). Redirect URIs, `allowedOrigins`, and the single-user demo
  posture (`max_instances=1`) are reconciled at cutover (10.7); multi-user session isolation remains
  the pre-scale item already tracked in §15, not introduced here.
- **AD-16.7 — Contract impact: none intrinsic.** The migration surfaces and steers existing fields;
  any new field (e.g. for 9H/9M editing) is an independent additive-MINOR bump gated behind a
  `CONTRACT_VERSION` change when that feature is built, not by the migration itself.
- **AD-16.8 — Client data/state layer: a server-cache library (TanStack Query), not a global store.**
  The Next.js client caches server data (`/api/me`, `/api/dashboard`, `/api/portfolio`, `/api/jobs`)
  with **TanStack Query (React Query)**; query keys mirror the API resources (`['portfolio', userId]`, …).
  There is **no Redux/Zustand global store for server state** — local UI state (open dialogs, form
  drafts, theme) stays in component state/context, and theme is the client-only localStorage preference.
  - **Optimistic writes are the concrete mechanism** behind the mockup's "optimistic, no full-page
    reloads" principle (AD-16.2): `useMutation` with `onMutate` (snapshot + patch the cache) → `onError`
    rollback → `onSettled` `invalidateQueries` the affected keys — so e.g. *add experience* invalidates
    both `portfolio` and `dashboard`. This buys cross-resource invalidation + rollback without bespoke code.
  - **SSR/hydration:** App Router server components fetch initial data (types generated from the OpenAPI
    schema, AD-16.3) and hydrate the client cache via `HydrationBoundary`, so first paint is data, not a
    spinner. The verified bearer token (AD-16.4) is attached by one shared fetch wrapper; a central `401`
    handler triggers a Firebase token refresh.
  - **Streaming stays outside the cache:** the grill SSE (AD-16.5) is a dedicated `EventSource` hook
    inside `StreamingTranscript`; the finished turn is written back into the query cache.
  - **Alternative considered — SWR** (smaller, ~4KB): viable, rejected as the default because this app is
    **write-heavy** (profile / experience / application / preferences / tailor) and React Query's
    first-class mutation + cross-key invalidation + rollback + devtools fit that shape better.
    **Tripwire:** if the 10.5 bundle-size spike ([PHASE10_UI_MOCKUP.md §8](PHASE10_UI_MOCKUP.md)) shows
    the data layer materially over budget, fall back to SWR with the *same* optimistic/rollback rules;
    the component API is written to not care which library backs it.
- **AD-16.9 — Frontend toolchain lives in `frontend/`; the devcontainer pins only Node (Playwright system deps come at 10.5).**
  The Next.js app and **all** its JS tooling (TanStack Query, test runners, linters) are project
  dependencies in `frontend/package.json`, scaffolded at 10.5 — not global installs. TanStack Query is
  `npm i @tanstack/react-query`; it needs nothing at the devcontainer level.
  - **Test stack:** **Vitest + React Testing Library + jsdom** (unit/component), **MSW (Mock Service
    Worker)** to mock the FastAPI endpoints (the "mocked API" the 10.5/10.6 acceptance tests
    reference), and **Playwright** (E2E). React Query is tested via a `QueryClientProvider` wrapper +
    MSW, asserting the optimistic update **and** the rollback path (AD-16.8).
  - **Devcontainer** provides only what npm can't per-project: a **pinned Node major** (the current
    LTS line — `22` in `.devcontainer/devcontainer.json`; the feature still resolves the latest
    minor/patch) and, at 10.5, **Playwright's system browser libraries** via
    `npx playwright install --with-deps`, run from a `frontend/` setup step — **not** baked into the
    Python base image before the app exists (keeps the image lean).
  - **`make check`** gains a `frontend` lane (lint + typecheck + Vitest; Playwright E2E as a separate
    job) when 10.5 lands; until then the Python gate is unchanged.

### 16.4 API contract sketch (to be finalised in build 10.1–10.4)
Thin, resource-oriented, all typed from `schema.py`:
- `GET /api/me` — session identity (verified token → `user_id`).
- `GET /api/dashboard`, `GET /api/portfolio`, `GET /api/jobs` — read views wrapping existing stores.
- `POST /api/profile`, `POST /api/experience`, `POST /api/applications`,
  `PUT /api/preferences` — writes over the (BUG-1-fixed) stores; transactional note per §8.
- `POST /api/grill` + `GET /api/grill/stream` (SSE) — interactive turn over `DiscoverySession`.
- `POST /api/tailor`, `GET /api/resume/{fmt}` — tailor + export (PDF/DOCX/MD) via existing renderers.

### 16.5 Migration principle & sequencing
Presentation + transport change; the domain does not. Slices are ordered API-first so the backend is
provable before the React shell exists: **10.1** auth boundary → **10.2** read APIs → **10.3** write
APIs → **10.4** streaming grill API → **10.5** Next.js shell/routing/auth → **10.6** Next.js grill +
tailor UI → **10.7** cutover (deploy artifact + remove Streamlit, infra + docs reconcile). Build
specs and acceptance criteria: [GROOMING.md](GROOMING.md) Phase 10.

### 16.6 Deploy topology (build 10.7) — single container, static export served by FastAPI (AD-16.10)
The Next.js frontend is **effectively an SPA** — every page is a client component with client-side auth
guards + client data fetching; there are no server components doing data fetching, no route handlers, no
SSR data needs. So `next build` runs with `output: 'export'` (+ `trailingSlash`) to emit static HTML/JS to
`frontend/out/`, and **FastAPI serves that at `/`** (`api/frontend.py::mount_frontend`, mounted AFTER the
`/api/*` routers + plugins). One Cloud Run service, **same origin → no CORS**, one deploy artifact.
- **Chosen over two services** (separate Next.js + FastAPI) for simplicity at this stage: no CORS, one
  image, one deploy. If a *private* frontend later needs its own service (open-core, §17), that is an
  additive service — it doesn't force the core to split.
- The image is **multi-stage** (`Dockerfile`): a `node` stage builds the export; a `python` stage runs
  `uvicorn api.main:app` and serves both the API and the bundled `frontend/out`. Streamlit's
  `docker-entrypoint.sh`/CMD are replaced.
- **`CE_DELIVERY` / promotion:** the same image is deployed to a **pre-dev test env first** (a new GCP
  project), validated, then promoted to dev. `web/` Streamlit *source* removal is a follow-up (10.7b) —
  the API reuses most of `web/` (view builders + stores + the shared `web/async_runner`), so only the two
  Streamlit UI modules (`streamlit_app.py`, `grill_ui.py`) + their deps/tests are removed, not the package.

---

## 17. Extensibility — open-core seam for a private premium layer

> **Status:** `active` · added 2026-07-10. Records how a **private, commercial feature layer** composes
> with this **core** in production without the core ever depending on it. This section documents only the
> *mechanism* (the extension points); the specific premium features live in a separate private repository
> and are deliberately **not described here**.

### 17.1 The problem
The core (this repo) is the durable product surface. Future differentiating features are built privately
and must **layer on top of the core in production** — the commercial deploy = core + private layer; the
open/demo deploy = core alone. This must not fork the codebase or leak private concerns into the core.

### 17.2 Decision — open-core with a one-way dependency (AD-17.1)
**The private layer depends on the core; the core never imports the private layer.** The core is fully
functional standalone. The private layer is packaged separately, pins a core version, and *extends* it
through stable seams. This one-way rule is the whole architecture — everything below serves it.

### 17.3 Backend seam — a plugin registry (AD-17.2)
The FastAPI app discovers and mounts routers contributed by **installed plugin packages** via the
`careerengine.plugins` entry-point group (`api/plugins.py::load_plugins(app)`, called after the core
routers in `api/main.py`). Each entry point resolves to a `register(app) -> None` callable that adds its
own routers/dependencies. Rules:
- The **core ships zero plugins**; a private package registers one under the entry-point group.
- A plugin that raises during registration is **skipped, not fatal** — a broken add-on can never take
  down the core.
- `CE_DISABLED_PLUGINS` (comma-separated env) is a denylist, so the **same image** can run with a plugin
  installed but switched off (feature-flag parity between OSS and commercial deploys).
- This **generalizes the Phase-11.D MCP job-source plugin design** — the same extension discipline, one
  level up (whole routers, not just job-source adapters).

### 17.4 Frontend seam — feature flags + a shared design system (AD-17.3)
- **Feature flags** (`frontend/src/lib/flags.ts`, `NEXT_PUBLIC_FEATURES` comma-separated) gate nav
  entries + routes. The OSS core enables none; a commercial build sets the env. `SidebarNav` renders a
  flagged group only when its feature is on (the reserved `PREPARE` group is the first consumer — hidden
  by default, per [PHASE10_UI_MOCKUP.md §3](PHASE10_UI_MOCKUP.md)).
- **Composition** of the private routes themselves is a deploy-topology choice tied to **10.7**: either a
  separate Next.js service reusing a published design-system + data-layer package, or a build-time overlay
  of a private route group. The design system (the §2 component inventory) is the shared contract either
  way. Pick the 10.7 topology (single container vs two services) with this in mind — **two services keeps
  the private frontend the cleanest**.

### 17.5 What to build now vs later (AD-17.4)
**Design the seam now, build the split later.** The seams above are cheap and stable; standing up the full
open-core machinery (private package/registry, dual CI, version pinning) before a private feature exists is
YAGNI cost. So: the core carries the plugin registry + flag seam (zero plugins, zero flags on); the private
repo and its packaging land when the first premium feature is real. Env mapping: the OSS/demo deploy runs
core-only; the commercial deploy (a future `qa`/prod GCP project) runs core + the private layer.

---

## 18. Résumé copy quality — bullet identity + copywriting inside the grill (contract v2.9.0)

> **Status:** `active` (design accepted, not yet built) · added 2026-07-12 · owner decision: Sumanta.
> Build tickets: [GROOMING.md](GROOMING.md) §Copy quality. Delivery status: [PROGRESS.md](PROGRESS.md).

### 18.1 The problem — nobody writes the bullets
A résumé bullet is `story.result`, verbatim (`web/resume_builder._bullet_for`). `story.result` is an
artifact of the **grill**, whose job is metric extraction and validation — not résumé prose. The single
model call in the résumé path (`STRUCTURED_TAILOR_SYSTEM_PROMPT`) says so explicitly: *"your job is
selection, a summary, and skills."* It returns `selected_achievement_ids`; the assembler then stamps
bullets out of the chosen stories deterministically.

So the pipeline **has no copywriting stage at all**. Two consequences:
- Bullets read flat, because they are extraction output shipped as final copy.
- We capture full **S/T/A/R** during the grill and then discard S, T and A at render time, keeping only R
  — three quarters of the material we already paid to collect, thrown away one line before the PDF.

This cannot be fixed by editing the tailor prompt: that call emits no bullet text, so there is nowhere to
put the instruction. **The missing thing is a stage, not an agent and not a better system prompt.**

### 18.2 Decision — AD-18.1: the copywriter is a PROMPT + node, never an "agent"
The job is one deterministic transform: (STAR story + role context) → a résumé bullet. No tools, no
memory, no autonomous loop, no peer-to-peer messaging. Modelling it as an A2A/ADK agent (as with the Scout
⇄ Primary discovery pair, §15) would be unjustified machinery. It is a workflow **node** with a system
prompt.

Reference: a chat-based résumé-tailoring *skill* a user's contact swears by (`demo_output/joy-resumeskill.md`)
is likewise a pure prompt — no agent — and its content rules (lead with impact, reframe honestly, promote
must-have hits, trim irrelevant bullets, **never fabricate**) are good source material for our prompt. We
do **not** adopt its shape: it is a one-shot chat skill that holds the whole résumé in context and emits a
`.docx`. Our architecture is durable evidence + a deterministic assembler + BYOK cost discipline; adopting
its shape would mean discarding the grill.

### 18.3 Decision — AD-18.2: copywriting happens IN the grill, human-validated, and PERSISTS
The polished bullet is proposed **during grilling** and the user accepts / edits / rejects it. It is then
**persisted state**, not something regenerated at export. Rationale, in order of importance:

1. **No unreviewed prose can reach a PDF.** A copywriter pass at export could invent a verb or imply a
   scope and land it in a document nobody proofread. If the user signed off on the sentence, the résumé
   cannot contain a claim they never saw.
2. **Export stays deterministic and free.** Because the approved bullet is durable state, assembly needs
   **no model call** — no per-export burn on the user's own BYOK quota, and no cache/staleness machinery
   (an earlier proposal to cache a copywritten résumé in `master_resume_json` is thereby **rejected** as
   unnecessary).
3. **It forces grill coverage to be honest** (AD-18.5 below).

Batching is a hard requirement: propose rewordings for **all of an entry's bullets in one turn**. One turn
per bullet would make the grill interminable and is the obvious failure mode of this design.

### 18.4 Decision — AD-18.5: coverage is the product, not a side effect
The grill currently selects a frontier entry and drills it for a metric. It will happily interrogate a
"favourite project" while a dozen strong bullets from the user's uploaded résumé are never touched. When a
user hands us rich source material, **covering it is the job**.

Every supplied bullet must reach one of three terminal states: **quantified** (a metric was extracted),
**strengthened** (reworded and accepted), or **explicitly skipped** (the user said it doesn't matter). The
grill may not declare an entry done while any of its bullets is in none of them, and the user must be able
to *see* the remaining coverage rather than guess at it.

### 18.5 Decision — AD-18.4: an edit at render time has THREE destinations, and the user picks
A tailored résumé is a **rendering** of the portfolio, not a copy of it. The place people actually notice
bad wording is post-tailor / pre-render — the JD is in front of them. So an edit made there must be
disambiguated rather than silently applied:

1. **This résumé only** — a JD-specific rewording that must NOT pollute the master (echoing one company's
   vocabulary). Lives in the exported document, nowhere else. Export already POSTs the résumé body, so this
   costs no persistence at all. It is also the only meaningful destination for the model-written **summary**
   and **skills**, which have no portfolio object behind them.
2. **Overwrite the original** — the old line was simply worse.
3. ~~**Persist as a new variant**~~ — **deferred to CQ-7; see the amendment below.**

Without bullet identity (AD-18.3) only option 1 is even expressible — which is precisely why today's UI can
edit a bullet but cannot tell the user what became of it. (Identity alone was not enough either: the
*assembler* threw it away one line before the DTO. See AD-18.6.)

> **AMENDED 2026-07-13, after adversarial pre-execution review — this decision was wrong twice.**
>
> **(a) "Overwrite" must be an IN-PLACE update, not `supersedes`.** A `supersedes` overwrite mints a *new*
> `Bullet(source="user")`, which `web/coverage.py` reads as UNCOVERED — no story names it. That flows
> straight through `entry_still_needs_grilling` → `_has_pending_work`, so the router **re-opens a finished
> entry and marches the user back to put a number on the line they just polished.** That is the CQ-5b
> failure, prescribed by the architecture. An in-place update keeps `bullet_id` stable, so
> `answers_bullet_id`, coverage, and the ID-dedup all keep pointing at the right thing. (Worse: the
> `accept_bullets` seam *permanently deletes* the superseded original — destructive, not merely hidden.)
>
> **(b) "Persist as a new variant" is underspecified and is NOT built.** A variant is an *alternate phrasing
> of a line that already exists*, and there is no model for alternates — so as written it is a button that
> makes the master résumé list one achievement twice (the exact bug AD-18.6 fixes) and re-opens the entry in
> the grill. Coherent variants need a variant-group model: **which phrasing the master shows** (a product
> call, not a code call), how the tailor chooses among alternates for a given JD, and how coverage inherits
> through the link. Tracked as **CQ-7**, blocked on an operator decision. The UI **omits** the option rather
> than disabling it — a greyed-out button is a promise we did not ship.

### 18.6 Decision — AD-18.3: bullets need IDENTITY (contract v2.9.0, the prerequisite)
> **SHIPPED** in CQ-1 (PR #87). The problem statement below is kept in the past tense as the rationale
> for the decision; the current shape is `Entry.bullets: list[Bullet]`.

`Entry.bullets` **was** a `list[str]`, and everything above was blocked on that:
- Edits **were** addressed by **array index**, which shifts under any concurrent insert/delete — so a slow
  client could edit the wrong line. (`PATCH /api/experience/{id}/bullet` now takes a `bullet_id`.)
- There **was** no way to say *"this reworded line supersedes that original one"*, so the user could not be
  offered the overwrite-vs-keep-both choice — and "keep both" would silently reproduce the duplicate-content
  bug fixed in `_merge_entry_bullets` (PR #86).
- The résumé **merge/dedup** work (a second upload still clobbers the first — see HANDOFF, CQ-2) must union
  bullets on a matched entry, and had nothing stable to dedup *by*.

**Shape as shipped:** `Bullet(bullet_id: UUID, text: str, source: parsed|user|grilled, supersedes: UUID|None)`.
The migration is **read-time** — a `field_validator(mode="before")` coerces a legacy `list[str]`, so existing
sessions load transparently and re-persist in the new shape on their next write. No batch rewrite.

So `list[str]` → `list[Bullet]` with a stable `bullet_id`, `text`, `source` (`parsed` | `user` | `grilled`)
and `supersedes`. This is a **breaking shape change to persisted state**: version-gate to **contract
v2.9.0** with a migration for existing sessions (per the contract-version convention — do not mutate a
spec in place).

**Bullet identity is the shared prerequisite** for merge/dedup, for delete-a-bullet, and for the
copywriter loop. It is therefore sequenced first (see GROOMING).

### 18.7 Decision — AD-18.6: a résumé LINE is an object with identity, not a string (contract v2.12.0)

`RoleBlock.bullets` was `list[str]`. The assembler took bullets that had identity (AD-18.3) and stories that
had ids, rendered them to bare text, and **threw the identity away one line before the DTO**. That single
fact was the ceiling on three shipped bugs, each reproduced against the real code:

- The **master résumé listed one achievement three times** — the raw `story.result`, the original parsed
  line, and the copywriter rewrite the user had approved. An accepted story-derived proposal recorded
  nothing about the story it was written for, so nothing could tell they were the same achievement. **Text
  dedup cannot fix this in principle: the better the copywriter does its job, the less the rewrite resembles
  the line it replaced.**
- **Tailor ignored the user's uploaded résumé.** Its catalog was validated STAR stories only, so a user who
  uploaded a strong CV and tailored it before grilling got an EMPTY document — the same failure already
  fixed for the master résumé and never fixed here.
- **Tailor shipped raw grill text** even when the user had approved better prose, making AD-18.2's promise
  ("no unreviewed prose can ever reach a PDF") **false for the tailored résumé — the actual product.**

**The decision.** A rendered line is `ResumeLine(text, bullet_id, story_id)`: it knows what it came from.
`Bullet.derived_from_story_id` (additive, v2.12.0) is the missing link — *this bullet **is** that story's
résumé line* — so the assembler renders the approved bullet **instead of** `story.result`. Note the
direction: this is the opposite of `StarStory.answers_bullet_id` (v2.11.0), which records which bullet a
grill *question* was about. A story can be *about* one bullet while its résumé line is a different, newly
written one; conflating the two loses that.

**The tailor's catalog is DEFINED as "the lines the master would render."** Not a second query that happens
to agree — literally the same function. The model can only select something that will actually render, and
anything renderable can be selected. Two things that must agree cannot drift if there is only one of them.

**Dedup is by ID — with ONE scoped exception, and it is load-bearing.** `_covers()` (text containment)
survives *only* for stories whose `answers_bullet_id` is empty. Every story written before v2.11.0 has an
empty link, **and that is all of the data in the live database**; the link cannot be backfilled, because
which line a story answered is not recoverable and guessing it is what this design exists to end. Deleting
the shim — which an earlier draft of this decision did — would double-list every grilled bullet of every
returning user on day one. It carries its deletion condition in its docstring: *when no `metrics_validated`
story with an empty `answers_bullet_id` remains in live data.*

**Coverage must learn the new link, and the ORDER of the checks is part of the decision.**
`derived_from_story_id` → QUANTIFIED is tested **before** `source is GRILLED` → STRENGTHENED. Every bullet
the copywriter writes is GRILLED, so testing GRILLED first makes the linked branch unreachable in
production — it would only fire for a `source=USER` bullet, which no write path creates. (Adversarial review
caught exactly that, over a green suite whose tests hand-built a bullet in a shape the app cannot produce.
This codebase has now shipped that failure three times; the order is not incidental.)

**Consequences that must not be re-litigated by a future change:**
- A rewrite that supersedes a story-derived bullet **inherits** its `derived_from_story_id`. The superseded
  original is deleted by the accept seam, so a replacement that does not inherit the link orphans the story
  — which then renders its raw grill text again, next to the rewrite. "Polish a line, then polish it again"
  is the most ordinary flow there is, and it silently reintroduces the bug this decision removes.
- The copywriter does not re-offer a story that already has an approved line; it offers the **bullet**.
  Otherwise the user is asked to re-approve work they already approved, and accepting mints a second bullet
  claiming the same story — a loop that never converges.
- `derived_from_story_id` is set **at creation only**. An edit that could set it would let any bullet be
  pointed at any validated story and be marked covered without ever having been grilled: a **false
  QUANTIFIED**, which AD-18.5 identifies as the worst error coverage can make.
- Deleting a STAR story **clears** the link on bullets that spoke for it (the user keeps their words; the
  dangling claim goes) — and patches `work_timeline` **only when a link was actually cleared**, because a
  `state_delta` is applied by `dict.update()`: writing the timeline unconditionally lets a story deletion
  silently erase a bullet a concurrent request just added to an unrelated entry.
