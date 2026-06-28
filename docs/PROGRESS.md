# CareerEngine — Progress Tracker

> Single source of truth for **what's done vs. pending**. Update this at the end of every work
> session / sub-agent run. Keep entries terse. Legend: ✅ done · 🟡 in progress · ⬜ not started · 🚫 blocked.

Last updated: **2026-06-28** — *Planning complete; no code written yet.*

---

## Milestone status
| Phase | State | Notes |
|-------|-------|-------|
| Planning & architecture | ✅ | ARCHITECTURE.md, REFINED_PROJECT_PLAN.md, this file, AGENT_EXECUTION_PROMPT.md |
| Phase 0 — Contract Freeze | ⬜ | **Next.** Single agent, blocking. |
| Phase 1 — Core loop (CLI) | ⬜ | Fan-out after freeze |
| Phase 2 — Web / Infra / Async | ⬜ | |
| Phase 3 — Hardening / Eval | ⬜ | |

---

## Phase 0 — Contract Freeze  *(blocking; do before any fan-out)*
- ⬜ `pyproject.toml` — pinned deps, venv; **verify real `google-adk` 2.0 import paths**
- ⬜ `.env.example`
- ⬜ `config.py` — settings, `CONTRACT_VERSION`, client factories, access-mode flag
- ⬜ `schema.py` — `CareerEngineState`, `StarStory`, `Capability`, message envelopes, `UpgradeRequired`
- ⬜ `models/registry.py` — capability→model resolver iface + Free/BYOK routing (stubs)
- ⬜ `auth/provider.py` — `AuthProvider` + `KeyVault` interfaces (stubs)
- ⬜ `database/` `tools/` Runner — typed stub signatures
- ⬜ `Makefile` real `lint` (ruff) + `typecheck` (mypy strict) + `test` (pytest), build/deploy/destroy stubs; `make lint typecheck test` green
- ⬜ Golden type test (serialize↔deserialize every model) wired into `make test`
- ⬜ **FREEZE**: tag contract; signatures changeable only via `CONTRACT_VERSION` bump

## Phase 1 — Core agent loop (CLI-first MVP)
- ⬜ WS-A `workflows/discovery_graph.py` — graph, edges, `discovery_router`, 5-turn brake
- ⬜ WS-A `workflows/nodes.py` — ingest / grill / checkpoint(HITL) / finalize / tailor + CoT prompts
- ⬜ WS-C `database/firestore_session.py` — ADK SessionService adapter
- ⬜ WS-B `tools/web_scraper.py` — two-step fetch + Flash clean
- ⬜ WS-B `tools/pdf_renderer.py` + `templates/classic_resume.html`
- ⬜ WS-* `models/registry.py` — real resolver + capability detection + escalation signal
- ⬜ WS-D `auth/cli_auth.py` + `auth/key_vault.py` (local + Secret Manager)
- ⬜ `main.py` — CLI entrypoint wiring Runner
- ⬜ Exit demo: vague answer → quantified STAR → checkpoint@5 → PDF

## Phase 2 — Web, Infra, Async
- ⬜ `main.py` Streamlit path — dashboard + pending-action surface
- ⬜ `auth/firebase_auth.py` — Identity Platform (web)
- ⬜ `infrastructure/modules/*` — Cloud Run, Firestore, Artifact Registry, Secret Manager
- ⬜ Terraform SA grant `roles/secretmanager.secretAccessor`
- ⬜ `infrastructure/envs/{dev,prod}` + `infrastructure/README.md`
- ⬜ `jobs/pending_action_sweep.py` + Cloud Scheduler wiring (14-day)
- ⬜ `skills/cloud_ops/SKILL.md`
- ⬜ Exit: `make deploy` to dev; web+CLI share state; sweep flags stale apps

## Phase 3 — Hardening & Eval
- ⬜ `evaluation/user_simulator.py` + `test_config.json` (vague-applicant scenarios)
- ⬜ Monitoring/logging for graph hangs
- ⬜ Security review (key handling, IAM least-privilege, scraper/PDF injection)
- ⬜ CoT tuning; measure & reduce Pro-escalation rate

---

## Decisions log (append-only)
- 2026-06-28 — D1–D7 locked (see [REFINED_PROJECT_PLAN.md §1](REFINED_PROJECT_PLAN.md)).
- 2026-06-28 — Dropped Gemini 1.5 (legacy) and `tenant_id = SHA-256(key)`; adopted Identity Platform + Capability Registry.
- 2026-06-28 — Build process: **Sonnet builds + tests, Opus reviews + gates**. No self-declared "done"; only an Opus PASS ticks this file. Builders run in `isolation: "worktree"`.

## Blockers / open questions
- ⬜ Confirm exact `google-adk` 2.0 module/import names against the installed package (Phase 0).
- ⬜ Decide Free-Mode managed-key quota policy (per-user RPD cap to control platform cost).
