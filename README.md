# CareerEngine

[![CI](https://github.com/suchakra/career-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/suchakra/career-engine/actions/workflows/ci.yml)

Turn a stale, vague career history into **quantified, ATS-ready STAR résumés**
through an agentic "grill" loop on **Google ADK 2.0** — privacy-first (bring your
own key), cost-efficient (capability-routed models, no hardcoded model IDs), and
reproducible (strict contracts, deterministic tests).

> **Status & roadmap** live in [`docs/`](docs/), not here. Start at
> [`docs/HANDOFF.md`](docs/HANDOFF.md) (resume point) and
> [`docs/PROGRESS.md`](docs/PROGRESS.md) (delivery ledger). Design truth is
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); the demo walkthrough is
> [`docs/CAPSTONE_RUNBOOK.md`](docs/CAPSTONE_RUNBOOK.md).

---

## What it does

A turn-based, human-in-the-loop discovery graph: **ingest → grill → checkpoint →
discovery turn → finalize → tailor**. The grill loop refuses vague answers and
demands a concrete metric before committing a STAR story; a checkpoint every 5
turns lets you verify progress; the result renders to a PDF résumé and can be
tailored to a specific job description.

## Requirements

- **Python 3.12+**, `pip`, `make`.
- **Terraform ≥ 1.5** (only for infrastructure work).
- A **Gemini API key** (only for live model calls; everything else — including the
  full test suite — runs offline).

## Setup

```bash
make venv                     # create .venv and install the project + dev extras
source .venv/bin/activate
make check                    # ruff + mypy --strict + pytest  → all green
```

`make venv` is a convenience around `python -m venv .venv && pip install -e ".[dev]"`.
Configuration is read from environment variables / a local `.env` (see
[Configuration](#configuration)); `.env` is git-ignored and must never be committed.

## Run locally

CareerEngine has a CLI and a Streamlit web workspace that share the same runtime.

### CLI — "Grill Me" discovery → PDF

```bash
# Set a key + the local dev identity (bypasses Identity Platform for local use):
export GEMINI_API_KEY=...          # your Gemini key
export DEV_USER_ID=me              # local-only escape hatch (never used in prod)

# Start a session from a history file (frees stdin so you can answer interactively):
python -m main grill --history-file my_history.txt --output-pdf resume.pdf

# …or vision-ingest an existing résumé (PDF/PNG/JPG/WEBP):
python -m main grill --resume-file my_resume.pdf --output-pdf resume.pdf

# Tailor a completed session to a job description (URL or raw text):
python -m main tailor <session-id> "https://example.com/jobs/42" -o tailored.pdf
```

The agent asks probing questions, demands a concrete metric, checkpoints every 5
turns, and renders `resume.pdf`.

> **Free-tier note:** the Gemini free tier caps at **5 requests/minute**; a full
> session makes ~5–6 calls and may hit HTTP 429 before finishing. Use a
> paid/raised-quota key for uninterrupted live runs. (The deterministic
> end-to-end test renders a real PDF without any key.)

### Web dashboard

```bash
python -m main web                 # → streamlit run web/streamlit_app.py
```

The dashboard shows the discovery progress meter, pending follow-up actions, and
never-gated grill/tailor entry points. It renders a sign-in prompt until an
Identity Platform ID token is supplied.

## Configuration

All settings come from environment variables (or `.env`); nothing is hardcoded.

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Platform Gemini key (Free mode). |
| `DEV_USER_ID` | Local dev escape hatch — bypasses Identity Platform. **CLI only; never honored on the web path.** |
| `DEV_GEMINI_KEY` | Local dev key (treated as BYOK). |
| `GCP_PROJECT_ID`, `GCP_REGION`, `FIREBASE_PROJECT_ID` | Cloud project wiring. |
| `ACCESS_MODE` | `FREE` (managed key) or `BYOK` (user key from Secret Manager). |
| `MODEL_TIMEOUT_SECONDS` | Per-request model timeout (default 60) so a network stall fails fast. |
| `CE_LOG_LEVEL` | Log level for the `career_engine` logger (default INFO). |

BYOK keys are stored **only** in Google Secret Manager (`ce-key-{user_id}`),
never in Firestore and never logged. See [`docs/SECURITY.md`](docs/SECURITY.md).

## Quality gates

```bash
make check        # ruff + mypy --strict + pytest (offline, deterministic)
make tf-check     # terraform fmt -check + validate, both env roots (no GCP creds)
```

Both gates run in CI on every push and pull request — see below.

## Deploy to Google Cloud

Infrastructure is Terraform-first (details in
[`infrastructure/README.md`](infrastructure/README.md)). The stack is Cloud Run +
Firestore (Native) + Artifact Registry + Secret Manager (runtime SA gets **only**
`roles/secretmanager.secretAccessor`) + Cloud Scheduler (the 14-day follow-up sweep).

```bash
# 1. Build & push a container image to Artifact Registry, then reference it in tfvars.
#    (A Dockerfile / Cloud Build config is an operator-provided step — tracked follow-up.)

# 2. Configure the target project and deploy dev:
cp infrastructure/envs/dev/terraform.tfvars.example infrastructure/envs/dev/terraform.tfvars
# edit terraform.tfvars → set project_id and image
gcloud auth application-default login
make deploy       # terraform -chdir=infrastructure/envs/dev apply
make destroy      # tear the dev stack back down
```

Prod uses a remote GCS backend (uncomment the `backend "gcs"` block in
`infrastructure/envs/prod/main.tf`) and `ABANDON`s Firestore on destroy.

### Networking / DNS (Cloudflare in front of Cloud Run)

The recommended edge topology puts **Cloudflare** in front of the Cloud Run
service (DNS is managed there):

- Point a proxied (orange-cloud) DNS record at the Cloud Run URL (via a custom
  domain mapping or as an origin), so Cloudflare terminates TLS at the edge and
  provides **caching, WAF, and DDoS protection** in front of Google.
- Prefer restricting Cloud Run **ingress** and only accepting traffic through the
  Cloudflare edge (e.g. validate a Cloudflare origin secret / IP allowlist) so the
  raw `*.run.app` origin can't be hit directly and bypass the proxy.
- Cloud Run already provides managed TLS on its own URL; Cloudflare adds the edge
  layer, not a replacement.

## CI/CD (GitHub Actions)

Two workflows live in [`.github/workflows/`](.github/workflows/):

- **`ci.yml` — continuous integration.** On every push to `master` and every pull
  request it runs the same gates you run locally, in two parallel jobs:
  `make check` (ruff + mypy `--strict` + pytest; installs the WeasyPrint system
  libraries so the end-to-end PDF test runs) and `make tf-check` (terraform
  `fmt` + `validate` for both env roots). Neither job needs cloud credentials, so
  CI is fully gateable on a fork. The badge at the top of this file reflects the
  latest `master` run.
- **`deploy.yml` — continuous delivery (manual, opt-in).** A `workflow_dispatch`
  job that authenticates to Google Cloud via **Workload Identity Federation** (no
  long-lived JSON keys) and runs `terraform apply` for the chosen environment. It
  never runs automatically — so a repo without cloud secrets never sees a red
  deploy — and it reads its project/image/WIF settings from repository
  secrets/variables documented at the top of the file. Add required reviewers to
  the `prod` GitHub Environment for a human approval gate.

The review discipline for changes: work on a branch → `make check` green →
independent review → PR (CI must pass) → squash-merge. See
[`docs/HANDOFF.md`](docs/HANDOFF.md).

## Repository layout

```
main.py             CLI entrypoint (Click)
config.py           settings + CONTRACT_VERSION + client factories
schema.py           strict Pydantic v2 contracts (every boundary payload)
models/             capability-first model registry (no hardcoded model IDs)
workflows/          discovery graph, nodes, prompts, observability
tools/              résumé parser (vision), JD scraper (SSRF-guarded), PDF renderer
auth/               CLI + Firebase/Identity-Platform auth, Secret Manager key vault
database/           Firestore session + workspace stores
web/                Streamlit dashboard (pure view-model + injectable renderer)
jobs/               14-day pending-action sweep + OIDC-verified HTTP handler
integration/        model client adapter
evaluation/         adversarial vague-applicant simulator (Pro-escalation metric)
infrastructure/     Terraform (Cloud Run, Firestore, Secret Manager, Scheduler)
docs/               source of truth: HANDOFF, PROGRESS, ARCHITECTURE, SECURITY, …
```

## License

**Source-available, proprietary — not open source.** Copyright © 2026 Sumanta
Chakraborty, all rights reserved. You may view, clone, and run this code for
personal, non-commercial evaluation; any other use (production, commercial,
redistribution, derivative works) requires prior written permission. See
[`LICENSE`](LICENSE) for the full terms.
