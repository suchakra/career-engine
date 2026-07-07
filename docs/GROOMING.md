# CareerEngine — Grooming Tracker

> Turns roadmap items ([REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)) into sonnet-launchable
> build specs, and tracks how far each is groomed so we can resume mid-stream.
> A workstream is Ready when it has: scope (files), acceptance criteria (named tests), and points at
> the durable builder invariants in [skills/build-slice](../skills/build-slice/SKILL.md) and the one
> relevant [ARCHITECTURE.md](ARCHITECTURE.md) section. Builders run on Sonnet with worktree isolation;
> Opus reviews + merges (no self-declared done). master stays green per merge. A builder gets a
> self-contained ticket + the skill — not the big docs (see [CONTEXT_STRATEGY.md](CONTEXT_STRATEGY.md)).
>
> Grooming legend: ✅ Ready (launchable) · ◐ Draft (outline, needs detail) · ⬜ To groom.

## Delivery lens (architecture + business)

Every groomed item below is constrained by the four standing goals:
1. Quality without compromise (quantified outcomes, no fake confidence).
2. Extreme cost efficiency (capability-first model routing, no hardcoded model IDs).
3. Privacy-first BYOK architecture (secrets in Secret Manager only).
4. Capstone demoability (Google X Kaggle 5-day intensive): reproducible end-to-end story, fast setup,
   and clear evidence artifacts for judges.

## Current launch order

Live grooming is **current phase only**. Completed phases (1.5, 1.7, 2, 4, 7, 8, 9) are retired to
[history/GROOMING_ARCHIVE.md](history/GROOMING_ARCHIVE.md) — grep it for provenance, don't load it whole.
Canonical status for every phase is in [PROGRESS.md](PROGRESS.md).

1. ✅ Phases 1.5 → 9 — SHIPPED (see [history/GROOMING_ARCHIVE.md](history/GROOMING_ARCHIVE.md)).
2. ▶ **Phase 10 — Replace Streamlit with Next.js + FastAPI** — groomed below; building API-first, one
   slice per PR (10.1 → 10.7).

> **Retire ritual:** when a phase's tickets are all ✅ and merged, move them to
> `history/GROOMING_ARCHIVE.md` in the same session (see
> [CONTEXT_STRATEGY.md](CONTEXT_STRATEGY.md)). GROOMING.md stays small so it never bloats what an
> agent loads.

---

## Phase 10 — Replace Streamlit with Next.js + FastAPI (build tickets)

> **Status: 10.0 done (architecture decision recorded); 10.1–10.7 are ✅ Ready build specs — no
> code shipped yet.** The accepted decision, rationale, auth model, streaming choice, deploy
> topology, and API contract sketch are **canonical in [ARCHITECTURE.md §16](ARCHITECTURE.md)** — do
> not restate them here. Sequencing is in [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md) Phase 10;
> status is canonical in [PROGRESS.md](PROGRESS.md). Build **API-first, one slice per PR**, in order —
> each slice must be green (`make check` + any new frontend checks) before the next starts.

### Decision anchor (one line)
Retire the Streamlit surface for a **Next.js (App Router) frontend over a FastAPI JSON API**; the
Python domain is unchanged; `schema.py` stays the wire contract; auth + streaming move to the API
boundary. Full rationale + design decisions (AD-16.1..7): [ARCHITECTURE.md §16](ARCHITECTURE.md).

### Standing build rules for every 10.x ticket

- **Do not change domain behaviour.** FastAPI handlers `await` the existing async stores / graph /
  tailor / renderers directly. No business logic moves into the transport layer.
- **`schema.py` is the wire contract.** Response/request models are the existing Pydantic types (or
  thin DTOs over them); frontend types are generated from the OpenAPI schema, never hand-kept.
  Anything requiring a new field is a separate additive-MINOR `CONTRACT_VERSION` bump, not folded in.
- **Sub-agent instruction:** if a ticket's assumptions don't match the actual code (store signatures,
  auth interfaces, session shape), **PAUSE and ask — do not assume.** Confirm the auth shape (10.1)
  before wiring any protected route.
- Each ticket ships with tests; do not report `DONE`, report `READY FOR REVIEW`.

### ✅ 10.0 — Architecture decision record  *(DONE — grooming)*
Decision + rationale recorded in [ARCHITECTURE.md §16](ARCHITECTURE.md); sequencing in
[REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md) Phase 10. Unblocks 10.1–10.7.

### ✅ 10.1 — FastAPI skeleton + auth boundary  *(M · Backend)*
Stand up the FastAPI app and the single identity edge. **PAUSE point resolved:** the auth shape is
**AD-16.4 option (b) — Firebase ID-token bearer verified at FastAPI**, reusing the existing
`auth/firebase_auth.py::FirebaseAuthProvider` (verified token → `sub` → `user_id`, injectable
verifier for network-free tests). Rationale recorded in [ARCHITECTURE.md §16 AD-16.4](ARCHITECTURE.md).
Do **not** build a cookie/OIDC-callback session store.
- **Files:** new `api/` package (`api/main.py`, `api/deps.py`, `api/auth.py`); reuse `auth/`.
- **Auth mechanics:** FastAPI reads `Authorization: Bearer <id_token>`; an injectable
  `get_current_user_id` dependency verifies the token via `FirebaseAuthProvider` and returns the
  stable `user_id`. Missing/invalid/expired token → HTTP 401 (typed JSON, no stack leak, no token
  logged). The provider/verifier must be injectable so tests never touch the network.
- **Endpoints:** `GET /api/health` (unauthenticated liveness), `GET /api/me` (protected; returns the
  verified `user_id` + safe display info from token claims, e.g. email — never the raw token).
- **Acceptance:** an unauthenticated call to a protected route returns 401; a valid token resolves
  `user_id` via the same trust boundary the CLI/web use today; **no `asyncio.run` bridge** anywhere.
- **Tests:** `test_api_auth_rejects_missing_token`, `test_api_me_resolves_user_id` (injected fake
  verifier / store double, no network), plus `test_api_health_ok` and an invalid-token → 401 case.

### ✅ 10.2 — Read APIs  *(M · Backend)*
Typed GET endpoints wrapping existing read paths — **no behaviour change**.
- **Endpoints:** `GET /api/dashboard`, `GET /api/portfolio`, `GET /api/jobs`.
- **Reuse:** `web/session_loader.py`, portfolio view builders, `discovery` ledger reads.
- **Acceptance:** each returns the existing view model serialized from `schema.py`; load failure
  degrades to an empty typed payload (mirrors `try_load_latest_discovery_state`), never 500 on a
  missing session.
- **Tests:** one per endpoint asserting the typed shape from a seeded fake store; empty-state case.

### ✅ 10.3 — Write APIs  *(M · Backend)*
POST/PUT over the **BUG-1-fixed** stores; per-request async client, transactional note per
ARCHITECTURE §8.
- **Endpoints:** `POST /api/profile`, `POST /api/experience`, `POST /api/applications`,
  `PUT /api/preferences`.
- **Reuse:** `web/profile_store.py`, `web/portfolio_store.py`, `web/preferences_store.py`,
  workspace store.
- **Acceptance:** each round-trips through the store and re-reads the persisted value; validation
  errors return 422 with the Pydantic error; empty/no-op edits behave exactly as the store already
  does (e.g. blank bullet = no-op, per 9A).
- **Tests:** round-trip per endpoint; validation-error case; empty-edit no-op case.

### ✅ 10.4 — Grill API with SSE streaming  *(L · Backend — the interactive core)*
Serve the grill turn over Server-Sent Events (WebSocket only if a bidirectional need surfaces).
- **Endpoints:** `POST /api/grill` (submit answer / advance), `GET /api/grill/stream` (SSE of the
  turn's steps/tokens) over the existing `DiscoverySession`.
- **Acceptance:** frontier steering, checkpoints, and resume behave identically to the Streamlit
  grill (reuse `workflows.nodes` / `DiscoverySession`; **no graph changes**); the "currently
  grilling" label is derivable server-side (reuse the `_effective_frontier_label` logic from BUG-2).
- **Tests:** a scripted multi-turn session asserting the SSE event sequence against a fake model;
  resume-mid-grill emits the correct frontier label.

### ✅ 10.5 — Next.js app shell + routing + auth wiring  *(L · Frontend)*
The React shell consuming 10.1–10.3.
- **Files:** new `frontend/` (Next.js App Router). Routes: Dashboard / Portfolio / Jobs / Tailor /
  Grill.
- **Build the foundational components first** — the shared inventory in
  [PHASE10_UI_MOCKUP.md §2](PHASE10_UI_MOCKUP.md) (`AppShell`/`SidebarNav`, `StatusBadge`, `ActionCard`,
  `PrimaryButton`/`SplitButton`, `CollapsibleSection`/`Field`, `EmptyState`, `MetricStat`,
  `Toast`/`InlineError`); screens compose these, no screen re-implements a card/badge/form row.
- **Client data layer = AD-16.8** ([ARCHITECTURE.md §16](ARCHITECTURE.md)): TanStack Query; query keys
  mirror the read APIs; writes are optimistic (`onMutate` patch → `onError` rollback → `onSettled`
  invalidate) — that is how "without a full-page reload" is implemented. Include the SSR
  `HydrationBoundary` seam and the shared bearer-token fetch wrapper + central 401→refresh.
- **Acceptance:** login flow round-trips through the 10.1 auth boundary and sets the session; the
  three read views render live data from 10.2; profile/preferences forms submit via 10.3 **without a
  full-page reload** (optimistic update + rollback on error); frontend request/response types are
  generated from the FastAPI OpenAPI schema.
- **Tests:** component/integration tests for auth-guarded routing + one form-submit happy path
  (mocked API via **MSW**; **Vitest + React Testing Library**) **including an optimistic-write rollback
  on a failed mutation**; a bundle-size check gates the shadcn + data-layer choice
  ([PHASE10_UI_MOCKUP.md §8](PHASE10_UI_MOCKUP.md) spike). Frontend toolchain + test stack per
  [ARCHITECTURE.md §16 AD-16.9](ARCHITECTURE.md).

### ✅ 10.6 — Next.js grill (streaming) + tailor + résumé export  *(L · Frontend)*
The interactive surface consuming 10.4; unblocks 9H (inline résumé-edit chat) and 9M (DnD editor).
- **Acceptance:** grill renders streamed turns from the 10.4 SSE endpoint with the currently-grilling
  banner; tailor submits a JD and downloads PDF/DOCX/MD via the existing renderers behind the API.
- **Tests:** grill streaming render against a mocked SSE stream; tailor → export happy path (mocked).

### ✅ 10.7 — Cutover  *(M · Backend + Infra + Docs)*
Make Next.js + FastAPI the deployed product and remove Streamlit.
- **Acceptance:** delete `web/` Streamlit app + `web/async_runner.py`; update Dockerfile / Cloud Run
  service(s) / `allowedOrigins` / redirect URIs; reconcile [ARCHITECTURE.md](ARCHITECTURE.md) (mark
  Streamlit sections `superseded`, update the frontends diagram), [PROGRESS.md](PROGRESS.md),
  [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md), [SECURITY.md](SECURITY.md), and
  [HANDOFF.md](HANDOFF.md). `CONTRACT_VERSION` unchanged by the migration itself.
- **Tests:** the API test suite is green with no import of `web/`; deploy config lints.

---

