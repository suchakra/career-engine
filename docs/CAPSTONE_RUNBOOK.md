# CareerEngine — Capstone Demo Runbook & Evidence

> Status: **active**. Last reviewed 2026-07-01. Audience: a fresh reviewer/judge
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

**Expected:** `381 passed` (deterministic; no network, no GCP, no `input()`).
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

- [ ] `make check` → `381 passed`
- [ ] `make tf-check` → `Success!` (dev + prod)
- [ ] core-loop e2e test → pass (`%PDF` asserted)
- [ ] sweep test → pass (idempotent, per-user isolation)
- [ ] `grep -rn "gemini-"` over source → empty (capability routing)
- [ ] `resume.pdf` artifact from the live demo (screenshot / `file resume.pdf`)
- [ ] web dashboard screenshot (`python -m main web`)

## Honest tradeoffs & deferred scope (state these plainly)

- **Privacy-first, NOT zero-knowledge:** per-user isolation + encrypted-at-rest
  keys + inference billed to the user; server can resolve `user_id` (required
  for the async sweep). ZK was deliberately rejected (§5).
- **Firestore fallback is loud, not a hard stop** (in-memory fallback warns on
  stderr); a hosted hard-stop policy is a Phase-2+ decision.
- **Deferred wiring:** the Streamlit path loads the workspace per authenticated
  user but not yet the discovery-session state for the meter; the sweep's Cloud
  Run HTTP endpoint + Identity Platform frontend token exchange are thin
  follow-ups. Logic is built and tested; only the outermost wiring remains.
- **`terraform plan/apply`** need GCP credentials; only `fmt`+`validate` run in
  CI. `terraform` is not yet a devcontainer dependency (tracked follow-up).
