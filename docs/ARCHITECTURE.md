# CareerEngine — System Architecture

> Status: **Design baseline (pre-implementation)**. Nothing is built yet.
> Last reviewed: 2026-06-28. Decisions captured in [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md).

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
When a `REASONING_HIGH` task in Free Mode fails its validation gate or the resolver has no
sufficiently-capable free model, the node returns a typed `UpgradeRequired` signal and the UI shows:

> *"This task requires advanced reasoning. Please provide your API key or upgrade to continue."*

No silent quality degradation, no crash — an explicit, typed branch.

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

## 12. Resume-aware ingestion & progressive discovery (Phase 1.5 / contract v1.2.0)

> Status: **spec, not yet built.** Lands as Phase 1.5; requires a backward-compatible contract bump to
> v1.2.0. Replaces the pillar-based `active_gaps` with a role-based `work_timeline`.

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
- **Apply-readiness gate (mandatory minimum):** `is_apply_ready(state, reference_date)` is a pure
  predicate — *every role within the last 5 years has ≥1 validated StarStory or is explicitly
  acknowledged.* New-grad case: "last 5 years **or** all roles, whichever is shorter." Tailoring /
  "apply for jobs" is gated on this.
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

### 12.5 Contract delta (v1.2.0 — additive, replaces pillar machinery)
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
This reworks WS-A's grill loop + router and the ingest prompt; it's the deliberate v1.2.0 amendment.

### 12.6 New graduates / no formal experience
A fresh grad with zero jobs is a first-class user — the same machinery serves them once "role" is
generalized to **experience entry** (12.5). What changes:
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
