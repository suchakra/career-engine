# CareerEngine — Capstone Demo Runbook & Evidence

> Status: **active**. Last reviewed 2026-07-02. Audience: a fresh reviewer/judge
> (Google × Kaggle 5-day intensive). Goal: reproduce the end-to-end story in
> **bounded time** with **deterministic evidence** — concrete commands and file
> outputs, not prose claims. See decision D9 in
> [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md).

CareerEngine turns a stale/vague career history into **quantified, ATS-ready
STAR résumés** through an agentic "grill" loop on Google ADK 2.0 — privacy-first
(BYOK), cost-efficient (capability-routed models), and reproducible.

---

## 0. Prerequisites

- Python 3.12+, `pip`, `make`.
- (Infra only) Terraform ≥ 1.5. (Live model calls only) a Gemini API key.

## 1. Setup (≈2 min, no cloud, no keys)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make check           # ruff + mypy --strict + pytest
```

**Expected:** `424 passed` (deterministic; no network, no GCP, no `input()`).
This single command is the backbone of the evidence set — every capability below
is asserted by a named test.

## 2. The core loop — vague answer → quantified STAR → PDF

The end-to-end flow is proven deterministically by the integration test that
drives the **real ADK Runner** to a rendered PDF:

```bash
python -m pytest tests/test_integration.py -k full_end_to_end_turn_sequence -q
```

**Expected:** passes — a vague answer ("we got faster") is **rejected**, a
specific answer ("cut p99 from 800ms to 120ms across 40 services") yields a
validated `StarStory`, the 5-turn checkpoint fires, and `render_pdf` emits a
file starting with `%PDF`.

**Live demo (needs a Gemini key):**
```bash
export GEMINI_API_KEY=...            # or DEV_GEMINI_KEY
echo "10 years as a backend engineer at Acme; led migrations." \
  | python -m main grill --output-pdf resume.pdf
# or start from an existing résumé (vision ingest):
python -m main grill --resume-file my_resume.pdf --output-pdf resume.pdf
```
The agent asks probing questions, demands a concrete metric, checkpoints every 5
turns, and renders `resume.pdf`.

## 3. Progressive discovery, resume, and the web workspace

- **Resume a session** (backward continuation): `python -m main grill --session-id <id> --firestore`
- **Web dashboard:** `python -m main web` → Streamlit workspace (progress meter,
  pending actions, never-gated tailor/grill entry points). Renders a sign-in
  prompt until an Identity Platform token is supplied.

## 4. Async pending-action sweep (14-day follow-ups)

Deterministic proof (injected clock, in-memory store):
```bash
python -m pytest tests/test_pending_action_sweep.py -q
```
**Expected:** passes — applications in `applied` status older than 14 days get a
`follow_up` marker exactly once (idempotent); per-user failures are isolated.

## 5. Infrastructure (reproducible without cloud credentials)

```bash
make tf-check        # terraform fmt -check + validate (dev AND prod)
```
**Expected:** `Success! The configuration is valid.` for both env roots. Deploy
is `make deploy` (needs GCP creds). The Cloud Run runtime SA is granted **only**
`roles/secretmanager.secretAccessor` (least privilege).

---

## Judging proof-points → evidence map

Every claim maps to a command whose output is the proof.

| Standing goal | How CareerEngine delivers it | Reproduce (command → expected) |
|---|---|---|
| **Quality without compromise** | The grill loop refuses vague claims and demands a real metric before committing a STAR story; metrics validator spans eng + early-career patterns. | `pytest -k "vague or metric" -q` → vague rejected, specific validated. `pytest tests/test_nodes.py -k contains_real_metric -q`. |
| **Extreme cost efficiency** | Capability-first model routing (no hardcoded model IDs); Free mode serves grilling on Flash + CoT; Pro only on BYOK shortfall. | `grep -rn "gemini-" config.py schema.py workflows/ tools/ cli/ web/ jobs/ integration/` → empty. `pytest tests/test_registry.py -q`. |
| **Privacy-first (BYOK)** | Keys live in Secret Manager (`ce-key-{user_id}`), **never** Firestore; state/workspace docs carry no secrets; TF grants least privilege. | `pytest tests/test_key_vault.py tests/test_firestore_session.py tests/test_workspace_store.py -q` (assert no secret written). TF: `roles/secretmanager.secretAccessor` only. |
| **Agentic workflow (ADK 2.0)** | Turn-based HITL discovery graph: ingest → grill → checkpoint brake → discovery turn → finalize → tailor, one node per `run_async`. | `pytest tests/test_workflow.py tests/test_integration.py -q` → router branches, brake, discovery-turn-in-graph, Runner→PDF. |

## Evidence capture checklist (paste outputs, don't paraphrase)

- [ ] `make check` → `424 passed`
- [ ] `make tf-check` → `Success!` (dev + prod)
- [ ] core-loop e2e test → pass (`%PDF` asserted)
- [ ] sweep test → pass (idempotent, per-user isolation)
- [ ] `grep -rn "gemini-"` over source → empty (capability routing)
- [ ] `resume.pdf` artifact from the live demo (screenshot / `file resume.pdf`)
- [ ] web dashboard screenshot (`python -m main web`)

## Dry-run results (2026-07-02, executed)

Deterministic evidence — **all green**, captured from this repo at `contract-v2.3.0`:

| Check | Command | Result |
|---|---|---|
| Full gate | `make check` | **424 passed** |
| Core-loop e2e (real Runner → `%PDF`) | `pytest tests/test_integration.py -k full_end_to_end_turn_sequence` | **1 passed** |
| Async sweep (idempotent) | `pytest tests/test_pending_action_sweep.py` | **11 passed** |
| Infra | `make tf-check` | **Success!** (dev + prod) |
| Capability routing (no hardcoded model IDs) | `grep -rn "gemini-" config.py schema.py workflows/ tools/ cli/ web/ jobs/ integration/` | **empty** |

Live path (real Gemini, `DEV_USER_ID` dev-hatch + platform key, FREE mode):
- **Validated:** authentication, model resolution, and live `generate_content` calls
  all work — ingest, the opening grill question, and metric extraction executed
  against `gemini-2.5-flash` and returned real responses.
- **Bug found & fixed:** the live model returned JSON `null` for `situation`/`task`
  while `metrics_found=true`; `execute_grill_turn_node` used `dict.get(k, "")`,
  which yields `None` on a present-but-null key and crashed `StarStory`
  construction. Fixed by coercing null/absent → `""` (`get(k) or ""`) across all
  STAR string fields, with a regression test
  (`tests/test_nodes.py::TestGrillNullStarFields`). The deterministic suite missed
  this because its scripted client always returns full strings — a live dry-run
  earned its keep.
- **Known limitation:** a *complete* session makes ~5–6 model calls (ingest →
  question → extraction → discovery-turn → finalize); the Gemini **free tier caps
  at 5 requests/min**, so a full live session cannot render a PDF in a single burst
  (HTTP 429). This is an external quota ceiling, not a code defect. For a live PDF,
  use a paid/raised-quota key; the reproducible PDF proof for CI/judging is the
  deterministic `full_end_to_end_turn_sequence` test above (real Runner → `%PDF`).

## Honest tradeoffs & deferred scope (state these plainly)

- **Privacy-first, NOT zero-knowledge:** per-user isolation + encrypted-at-rest
  keys + inference billed to the user; server can resolve `user_id` (required
  for the async sweep). ZK was deliberately rejected (§5).
- **Firestore fallback is loud, not a hard stop** (in-memory fallback warns on
  stderr); a hosted hard-stop policy is a Phase-2+ decision.
- **Deferred wiring (mostly closed in PR #5):** the Streamlit path now loads both
  the per-user workspace AND the latest discovery-session state for the meter
  (`web/session_loader.py`), and the sweep has an OIDC-verified HTTP handler
  (`jobs/sweep_endpoint.py`, aud/iss pinned). The only remaining thin follow-ups
  are the outermost glue: mounting that handler in a served app, and the Identity
  Platform *frontend* (browser SDK) token exchange that supplies the `id_token`.
- **`terraform plan/apply`** need GCP credentials; only `fmt`+`validate` run in
  CI. `terraform` is now a devcontainer feature (`.devcontainer/devcontainer.json`;
  effective after a rebuild).
