# CareerEngine — frontend (Next.js app shell)

The **Phase 10.5 Next.js App Router shell** for CareerEngine — a bitcrafty-branded,
presentation-only re-housing of the existing Streamlit feature set over the FastAPI
backend (slices 10.1–10.4). Design truth: [`docs/PHASE10_UI_MOCKUP.md`](../docs/PHASE10_UI_MOCKUP.md);
architecture: [`docs/ARCHITECTURE.md` §16](../docs/ARCHITECTURE.md) (AD-16.x).

> No new domain concepts and **no `CONTRACT_VERSION` change** — this is presentation +
> transport only (AD-16.2 / AD-16.7). The wire contract is `schema.py`, surfaced to the
> client as generated types (see [Codegen](#openapi-type-codegen)).

## Stack

| Concern | Choice | Notes |
|---------|--------|-------|
| Framework | **Next.js 14 (App Router)** | Routes = URLs; deep links + back-button work. |
| Styling | **Tailwind + shadcn/ui (Radix)** | One token set, two theme maps (light/dark). |
| Data layer | **TanStack Query** (AD-16.8) | Optimistic writes → rollback → invalidate. |
| Auth | **Firebase Web SDK** (Google sign-in) | ID token → the 10.1 bearer boundary (AD-16.4). |
| Unit / integration tests | **Vitest + RTL + jsdom + MSW** (AD-16.9) | Fast gate; MSW mocks the API. |
| E2E | **Playwright** | Own lane; not in the fast gate (needs a browser). |

## Prerequisites

- **Node 20+** and npm.
- `npm ci` to install dependencies (a clean, lockfile-exact install).

## Environment

Public client config only — copy [`.env.example`](.env.example) to `.env.local` and fill it.
Every `NEXT_PUBLIC_*` value ships in the browser bundle and is **not a secret** (the Firebase
"API key" is a public project identifier). Never put a BYOK Gemini key or service-account key here.

```bash
cp .env.example .env.local   # then fill NEXT_PUBLIC_FIREBASE_* + NEXT_PUBLIC_API_BASE_URL
```

## Common commands

```bash
npm run dev          # dev server on http://localhost:3000
npm run build        # production build
npm run start        # serve the production build
npm run lint         # eslint (next lint)
npm run typecheck    # tsc --noEmit
npm test             # Vitest (unit + integration, MSW-mocked)
npm run check:bundle # First Load JS budget gate (after a build)
npm run e2e          # Playwright e2e (boots its own server; see below)
npm run gen:openapi  # regenerate typed API models from the backend OpenAPI
```

## The gate (`make frontend-check`)

The repo-level gate for the frontend lives in the root [`Makefile`](../Makefile) and runs the
same checks CI does — from `frontend/`:

```bash
make frontend-check   # npm ci → lint → typecheck → test → build → check:bundle
```

Run it before pushing. It is a **separate CI lane** from the Python `make check` (they need
different toolchains); both must be green.

## E2E (Playwright) — its own lane

E2E is **not** part of `make frontend-check` (it needs a real browser + system libraries, too
heavy for the fast gate). Run it explicitly:

```bash
npx playwright install --with-deps chromium   # one-time: browser + OS deps
npm run e2e
```

`playwright.config.ts` boots a **production server** for the run with a well-formed-but-fake
Firebase config (the SDK initializes and resolves a signed-out session locally — no live project,
no real Google popup). Point at an already-running server instead with
`PLAYWRIGHT_BASE_URL=http://localhost:3000 npm run e2e`.

## OpenAPI type codegen

Client API types are generated from the backend's OpenAPI schema so the wire contract stays
single-sourced in `schema.py` (never hand-maintained on the client):

```bash
npm run gen:openapi   # writes src/lib/api/types.gen.ts from openapi.json
```

`src/lib/api/models.ts` re-exports the friendly names the app imports; `openapi.json` is the
committed snapshot the codegen reads.

## Layout

```
src/
  app/            App Router routes (dashboard, portfolio, grill, jobs, tailor, settings, login)
  components/     Foundational component inventory (§2): AppShell, StatusBadge, ActionCard, …
    forms/        Progressive-disclosure forms (Profile, Preferences)
  lib/
    api/          Typed fetch client + generated models
    auth/         Firebase auth context + route guards (RequireAuth / RedirectIfAuthed)
    query/        TanStack Query provider, keys, and read/write hooks
    theme.ts      Light · Dark · System (persisted, no-flash)
  test/           Vitest setup, render helpers, MSW handlers
e2e/              Playwright specs (own lane)
scripts/          gen-openapi.sh, check-bundle-size.mjs
```

## Scope note

Phase 10.5 ships the shell + the read/write data layer against slices 10.1–10.4. The streaming
Grill surface (`StreamingTranscript` over SSE) and the Tailor export/preview wiring land in **10.6**;
CORS / deploy wiring lands in **10.7**. Feature-flagged nav rows (`/outreach`, `/interview`,
`/salary`) stay hidden until live.
