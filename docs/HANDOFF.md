# CareerEngine — Session Handoff / Resume Point

## 👉 YOU ARE HERE (updated 2026-07-12 — **PARITY COMPLETE & DEPLOYED; now fixing bugs found in live qa use**)
> ▶ **ACTIVE WORK: qa hardening.** Sumanta is using the qa deploy for real and finding bugs.
> Status of each is canonical in [PROGRESS.md](PROGRESS.md) ("qa hardening" row). Shipped so far:
> profile/preferences read+hydrate (#84), grill resume + master-résumé bullets + parse feedback +
> dark-mode file input + add-a-bullet (#85), and the #85 follow-up review fixes (#86).
>
> 🔴 **NEXT, IN ORDER.** NOTE: grooming (2026-07-12) found that **CQ-1 bullet identity** is a prerequisite
> for items 1 and 2 below — see item 3. Sequence is: CQ-1 → merge/dedup → delete → copywriter.
> 1. **Résumé merge/dedup.** A second résumé upload CLOBBERS the first: `POST /api/grill/resume`
>    calls `session.create` → `cli.session.create_session`, which is **last-write-wins**, so the
>    whole `CareerEngineState` (every entry, every STAR story, every hour of grilling) is destroyed.
>    **Decision taken (Sumanta, 2026-07-12): MERGE + DEDUP** — match entries on (title, org,
>    date-range), keep the existing entry (preserving its `entry_id`, stories and GRILLED status),
>    append genuinely-new entries as ungrilled, union the bullets on matched entries. Never destroy.
> 2. **Delete a bullet / delete an entry** — the store can replace and append a bullet but not
>    remove one; edit-only is half a tool, and it matters more once a merge can bring in a role the
>    user doesn't want.
> 3. **Copy quality — GROOMED 2026-07-12.** Root cause found: a bullet is `story.result` verbatim; there
>    is **no copywriting stage at all**, and we discard S/T/A at render time keeping only R. It is a missing
>    **stage** — a prompt + node, NOT an agent, and NOT fixable by editing the tailor prompt (that call emits
>    no bullet text). Design: [ARCHITECTURE §18](ARCHITECTURE.md) (AD-18.1..18.5). Tickets:
>    [GROOMING §Copy quality](GROOMING.md) — **CQ-1 bullet identity (contract v2.9.0) comes FIRST**, because
>    merge/dedup, delete, and the copywriter loop all need a stable `bullet_id` + `supersedes`.
>    Then CQ-2 (= the merge/dedup item above), CQ-3 delete, CQ-4 copywriter-in-the-grill (human-validated,
>    so export needs no model call), CQ-5 grill coverage, CQ-6 post-tailor/pre-render editing with a
>    persist choice. `demo_output/joy-resumeskill.md` is REFERENCE ONLY — do not adopt its one-shot chat shape.
>
> ⚠️ **MERGE RULE (Sumanta, 2026-07-12):** you may merge + deploy qa bugfix PRs without asking,
> **on the condition that Copilot has reviewed the PR first**. If you push more commits after
> Copilot's review, request a RE-review and wait — a stale review does not count. This rule exists
> because it was broken once: #85's last two commits were merged on green CI alone, and a follow-up
> review then found the grill bug was not actually fixed (stale question re-asked; a session with no
> pending question still stranded the user; a failed status read offered a *destructive* start card).
> Green CI is not a substitute for review.
>
> `dev` still requires an explicit go-ahead + `-f confirm_dev_cutover=true` (Kaggle-visible).

> ✅ **All parity slices are on `master` and LIVE on qa** (deploy run 29194226615, green). Verified on qa:
> `/api/health` ok; `/api/master-resume`, `/api/jobs/dismiss`, `/api/experience/{id}/bullet|grill|highlight`,
> `/api/story/{id}`, `/api/key`, `/api/jobs/discover`, `/api/grill/resume` all present in the served OpenAPI
> and still 401 without a bearer.
>
> ▶ **NEXT: walk the app end-to-end on qa** — sign in → set your Gemini key → upload a résumé → grill →
> Portfolio (grill-this / pin / edit bullet / delete story / **Build master résumé** → export) → Jobs
> (Find jobs → **Not interested**) → Tailor (JD → preview → export → track as application).
> URL: https://career-engine-qa-app-ontyg6kaja-uc.a.run.app · redeploy: `gh workflow run deploy.yml --ref master -f environment=qa`.
> After that: **promote to dev** (needs `-f confirm_dev_cutover=true`; dev is Kaggle-visible) and groom Phase 11.
>
> ⚠️ **Stacked-PR gotcha (cost us two PRs — don't repeat):** squash-merging a base PR **with
> `--delete-branch` auto-CLOSES the PRs stacked on it** (GitHub does NOT retarget; a closed PR whose base
> branch is gone cannot be reopened or re-based). #81 died this way and had to be re-filed as #83. If you
> stack, merge the base **without** `--delete-branch`, then `git rebase --onto origin/master <old-base-tip>`
> the child and `gh pr edit <n> --base master` before merging it.
>
> **Parity slices as shipped** (each: backend endpoint + frontend + tests → PR → Copilot review → merge):
> - ✅ **P1 BYOK key management** (PR #76) — `GET/POST/DELETE /api/key` + Settings key entry.
> - ✅ **P2 Jobs "Find jobs"** (PR #77) — `POST /api/jobs/discover` (live two-agent discovery) + run button.
> - ✅ **P3 Résumé upload** (PR #78) — `POST /api/grill/resume` (multipart → vision parse → seeds the grill).
> - ✅ **P4a** (PR #79) — Dashboard first-run key card + Tailor "track as application".
> - ✅ **P4b** (PR #80) — Portfolio entry actions: "Grill me about this" (`set_grill_frontier`),
>   pin/highlight (`set_entry_highlight`), delete STAR story (`delete_star_story`).
> - ✅ **P4c** (PR **#83**, ex-#81) — Master résumé: `POST /api/master-resume` (deterministic
>   `master_structured_resume` — **no model call ⇒ no BYOK key**, so it must NOT depend on
>   `get_discovery_session`; a test proves it by exploding that dep if resolved) + Portfolio
>   build/preview/export card. Export path shared with Tailor via `lib/tailor/resumeExport.ts`.
> - ✅ **P5 (LAST SLICE)** (PR #82) — **Jobs "Not interested"**
>   (`POST /api/jobs/dismiss` → `discovery.store.add_rejected_company`; dismissal is by COMPANY, which is
>   what the ledger records — the read side already subtracted it, only the write was missing) and
>   **STAR bullet edit** (`PATCH /api/experience/{entry_id}/bullet` → `portfolio_store.update_entry_bullet`,
>   inline edit on the Portfolio entry card).
>
> **The Next.js UI now does everything the old Streamlit app did.** Gate at merge: 774 backend tests,
> 23 frontend tests, mypy --strict / ruff / tsc / eslint / next build all clean. No contract change (v2.8.0) —
> every slice is transport over an existing `web/` · `discovery/` · `auth/` seam.

**`master` clean (10.7 + qa-env merged; PR #72/#73/#74). contract v2.8.0 · no contract change. `qa` DEPLOYED & healthy → https://career-engine-qa-app-ontyg6kaja-uc.a.run.app (same-project 2nd Cloud Run service, scale-to-zero; dev untouched). Deploy again anytime: `gh workflow run deploy.yml --ref master -f environment=qa`. Promote to dev only once validated (needs `-f confirm_dev_cutover=true`; dev is Kaggle-visible).**
**Phases 1–7 + 8A–8G + all of Phase 9 + BUG-1 + BUG-2 + ALL of Phase 10 COMPLETE. Streamlit is GONE — the product runs on Next.js (App Router) + FastAPI, deployed as ONE container (static export served by FastAPI, AD-16.10). Open-core seam (ARCHITECTURE §17) in place. Nothing deployed yet.**

**Just merged — Phase 10.6b (Tailor, PR #69 API + PR #70 UI, Copilot reviews addressed):** `POST /api/tailor`
→ `StructuredResume` (BYOK model call, `_tailor_isolated` saves/restores the global model-client factory)
+ `POST /api/resume/{fmt}` → PDF/DOCX/MD bytes; frontend `useTailor` + `ResumePreview` + Tailor page (JD →
preview → export). **Export is a stateless POST-render RPC, not a cached GET** — the domain has no
server-side tailored-résumé store (`tailored_resume_json` persists only when saved as an application).
Deferred follow-ups: `?kind=master` export, "track as application" from Tailor, JD-by-URL scraping.

**Earlier this session — 10.6a grill streaming (PR #68); 10.5 Next.js App Router shell (PR #67):**
- Scaffolded `frontend/` (Next.js 14 App Router): routes `dashboard/portfolio/grill/jobs/tailor/settings/login`;
  the foundational component inventory ([PHASE10_UI_MOCKUP.md §2](PHASE10_UI_MOCKUP.md)); the **AD-16.8 TanStack Query
  data layer** (read hooks + optimistic write→rollback→invalidate over the 10.2/10.3 APIs); **Firebase-bearer auth**
  wiring through the 10.1 boundary (AD-16.4) + `RequireAuth`/`RedirectIfAuthed` guards; light/dark/system theme.
- **Test stack (AD-16.9):** Vitest + RTL + jsdom + **MSW** (7 unit/integration tests, all pass) + **Playwright** login
  e2e (2 specs pass; own lane, self-booting production server + fake Firebase config). `scripts/check-bundle-size.mjs`
  First-Load-JS budget (all routes 85–122 kB gzip, budget 250 kB). `frontend/README.md`.
- **Gate wiring:** `make frontend-check` (npm ci + lint + typecheck + Vitest + build + bundle budget) + a separate
  **`frontend` CI lane** in `.github/workflows/ci.yml` (Node 20). Kept separate from the Python `make check`.
- **Picked up mid-flight** (prior sub-agent interrupted): fixed 2 Vitest failures (ProfileForm collapsible closed by
  default → `defaultOpen`; test QueryClient `gcTime:0` GC'd optimistic cache → `gcTime:Infinity`) and a `next build`
  blocker (named `DashboardContent` export illegal in `page.tsx` → extracted to its own module).
- **Remaining for 10.5:** Gemini 2.5 Pro review + Copilot review → address → squash-merge. **Do NOT deploy** (per operator).

**Just merged:**
- **PR #66** — Phase 10.4 (streaming grill API, presentation only, no contract change): the
  interactive grill over HTTP reusing `cli.app.DiscoverySession` + `workflows.nodes` (no graph
  changes). **`POST /api/grill`** RECORDS the caller's input into the durable canonical session
  (`web-{user_id}`) without running the graph (`start`→create from `history`, `answer`→patch
  `pending_user_answer`, `confirm`→patch `checkpoint_verified`); the answer travels in the request
  BODY (grill PII never lands in access logs); blank history/answer → 422, bad action → 422.
  **`GET /api/grill/stream`** runs the pending turn sequence over **SSE** (`text/event-stream`),
  looping `DiscoverySession.advance()` — one `event: turn` per completed turn + terminal
  `event: done`; the auto-advance loop mirrors `web/grill_ui._submit_answer` exactly; a mid-stream
  `ModelAPIError` ends the stream with `event: error` (never a 500). Additive, behavior-preserving
  refactor of `DiscoverySession` (`create`/`record_answer`/`record_checkpoint_confirmation`); the
  pure frontier-label helpers extracted verbatim to `web/grill_labels.py` (streamlit-free) so the
  API + Streamlit share ONE impl (BUG-2). `api.deps.get_discovery_session` builds a BYOK session
  (vault `fetch_key` via `run_in_threadpool` → 409 if no key). +8 tests (`tests/test_api_grill.py`,
  network-free). Design in ARCHITECTURE AD-16.5 "Transport shape (build 10.4)".
- **PR #65** — Phase 10.3 (write APIs, presentation only, no contract change): four protected
  async write endpoints — `POST /api/profile`, `POST /api/experience`, `POST /api/applications`,
  `PUT /api/preferences` — binding `schema.py` domain models directly (AD-16.3 wire contract) and
  reusing the existing store write-seams (`web.profile_store`/`web.preferences_store`/
  `web.application_store` sync via `run_in_threadpool`; `web.portfolio_store.aadd_manual_entry`
  awaited natively — one additive async wrapper over the private core). Malformed body = 422,
  required-field omission = 422; two strict api-local DTOs (`ApplicationWriteRequest`,
  `ExperienceWriteResponse`) in `api/schemas.py`. +13 tests (`tests/test_api_write.py`).
  GET endpoints — `GET /api/dashboard`, `/api/portfolio`, `/api/jobs` — wrapping the existing read
  paths (`web.dashboard`/`web.portfolio`/`web.jobs` pure view builders + discovery session/ledger
  reads). Async endpoints await a new additive `web.session_loader.atry_load_latest_discovery_state`;
  sync store calls run in `run_in_threadpool`; response models are a strict api-local presentation
  contract (`api/schemas.py`); all reads degrade to a typed empty payload (never 500) except a
  workspace `ContractVersionError` which propagates. +13 tests (`tests/test_api_read.py`).
- **PR #63** — Phase 10.1: `api/` FastAPI skeleton + single Firebase-bearer auth boundary
  (`GET /api/health` + `GET /api/me`, opaque 401, no token/claims logging). +4 tests.
- **PR #60** — Phase 10 design docs: resolves the 10.1 auth shape (Firebase bearer, AD-16.4),
  adds [PHASE10_UI_MOCKUP.md](PHASE10_UI_MOCKUP.md) (bitcrafty-branded Next.js mockup, reviewed),
  Phase 11 roadmap.
- **PR #61** — context-management strategy: new
  [CONTEXT_STRATEGY.md](CONTEXT_STRATEGY.md) + [skills/build-slice](../skills/build-slice/SKILL.md);
  GROOMING trimmed to current-phase (2,281→~144 lines) with history in
  [history/GROOMING_ARCHIVE.md](history/GROOMING_ARCHIVE.md); role-scoped reads wired into the
  instruction files.

**▶ NEXT — stand up the `qa` env (deploy + SEE the UI), then groom Phase 11**

**Phase 10 is COMPLETE** — Streamlit gone; Next.js + FastAPI in one container. Standing context:
- **A new private repo `git@github.com:suchakra/career-vault.git` is the go-forward home** for a future
  *private premium layer* — but wiring it up (CI/WIF/2-repo devcontainer) is deferred. The `vault` remote
  was **removed** for now (avoid stray pushes); re-add + wire later. `docs/personal.md` is gitignored
  (private operator notes / the unwritten premium idea — **never commit it, never describe it in the repo**).
- **Open-core seam MERGED (PR #71):** the core now carries a one-way
  extension seam so a private layer can compose in production without the core depending on it —
  backend plugin registry (`api/plugins.py`, `careerengine.plugins` entry points, `CE_DISABLED_PLUGINS`
  denylist) + frontend feature flags (`frontend/src/lib/flags.ts`, `NEXT_PUBLIC_FEATURES`) + a flagged
  `PREPARE` nav group (hidden in the OSS build). Zero plugins/flags on. Design: [ARCHITECTURE §17](ARCHITECTURE.md)
  (AD-17.1..4). Build the actual split (private package + dual CI) only when a premium feature is real.
- **Env strategy (clarified 2026-07-10): dev is NOT frozen — it just must not run *broken* features** (small
  chance Kaggle tests the product at their end-of-month completion review). The workflow: **a new pre-dev
  test env → validate → promote the same image to dev when stable.**
- **`qa` = that pre-dev test env, a NEW GCP project.** Rationale: the repo's pattern is one project per env
  (prod ≠ dev project), and the app targets the `(default)` Firestore DB (no db-id config) so a same-project
  qa would share dev's data. Provisioning is operator-gated (create project + billing, Google OAuth client
  [no TF resource], secret values out-of-band).

**The deploy artifact exists (10.7a merged):** one container — Next.js **static export served by FastAPI**
(`api/frontend.py`, AD-16.10), same-origin, no CORS, multi-stage Dockerfile (node build → `uvicorn
api.main:app`). `NEXT_PUBLIC_*` are baked in at build time via Docker **build args** (API base empty =
same-origin; **Firebase config must be passed per-env** or Google sign-in won't init).

**▶ Immediate next (in order):**
0. **SEE THE UI — repeatable `qa` deploy is BUILT** (same project as dev, per operator: scale-to-zero, ~free
   idle; NOT a new project). Terraform [`infrastructure/envs/qa`](../infrastructure/envs/qa) (2nd Cloud Run
   service `career-engine-qa-app`, Firebase env, min_instances=0, concurrency=1; reuses the project's
   `(default)` Firestore + dev's AR repo + WIF/deployer SA; no Streamlit secrets) + `deploy.yml environment=qa`
   (**default target**, Firebase `--build-arg`s, **hard `confirm_dev_cutover` guard so dev can't deploy by
   accident**). `make tf-check` green (dev/qa/prod).
   **Operator bootstrap needed before I can run it ([docs/QA_DEPLOY_RUNBOOK.md](QA_DEPLOY_RUNBOOK.md)):**
   (A) add Firebase to the project + web app + enable Google sign-in; (B) set 3 repo Variables
   `NEXT_PUBLIC_FIREBASE_API_KEY/_AUTH_DOMAIN/_PROJECT_ID`. Then **I run** `gh workflow run deploy.yml --ref
   master -f environment=qa` (repeatable) → URL in the run summary → (C) add the run.app host to Firebase
   Authorized domains → sign in. **Known risk:** if sign-in 401s, swap the `tokeninfo` verifier in
   `auth/firebase_auth.py` for `firebase-admin`'s `verify_id_token` (~15 lines).
2. **Local-dev workflow (operator wants this — [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md) Phase 11.H):**
   a documented, one-command way to run the full stack on a laptop (FastAPI `uvicorn --reload` + Next.js
   `npm run dev` with a `.env.local`, or `docker run` the image) so changes are testable before deploy.
3. **Groom Phase 11** into build tickets (it isn't yet), then the rest: custom domain, isolation/security
   decision (11.C), MCP job-source plugins, copywriter-agent spike, résumé-presentation UI, beta test.

Work **inline** unless parallelizing ([CONTEXT_STRATEGY.md](CONTEXT_STRATEGY.md)). **Deploy to `qa` first;
promote to dev only once validated** (don't ship broken features to the Kaggle-visible dev).

**What shipped this session (5-PR cycle: 2 bug fixes + Phase 9 completion + Phase 10 groom):**

- **PR5 — Phase 10 groom (PR #59, docs-only):** recorded the web-platform migration decision in
  ARCHITECTURE §16 (the tech recommendation writeup), added Phase 10 to the plan roadmap, and rebuilt
  GROOMING §Phase 10 into ✅ Ready API-first build tickets 10.1–10.7. Copilot review: clean (no
  comments). No code / contract change.
- **9F (PR #58):** Jobs — preference-form guidance + `derive_initial_roles` portfolio-seeded defaults.
- **9A (PR #57):** Portfolio — delete STAR stories + edit résumé bullets (empty edit = no-op).
- **BUG-2 (PR #56):** Grill "currently grilling" banner missing on first question after resume.
- **BUG-1 (PR #55):** Workspace saves failing with "event loop is closed" + auth redirect-URI hotfix.

- **BUG-1 (PR #55):** Workspace saves failed with "Event loop is closed" (profile save +
  track-application). `FirestoreWorkspaceStore` reused one `AsyncClient` across two `asyncio.run()`
  calls; the gRPC channel bound to the first (closed) loop. Fixed via per-call `_acquire()`
  `@asynccontextmanager` creating a fresh client per async op (injected client never closed; factory
  client closed in `finally`, awaiting `close()` if awaitable). Ctor enforces client/client_factory
  mutual exclusivity. Also pinned `CE_AUTH_REDIRECT_URI` to `/oauth2callback` in deploy.yml + main.tf.
- **BUG-2 (PR #56):** Grill "📌 Currently grilling" banner missing on the **first question after
  resume**. On resume, `_migrate_education_on_resume` blanks `grill_frontier` when the pinned entry
  is no longer grillable; `_try_resume` derived the label straight from `grill_frontier` → empty
  banner until the next turn re-pinned. Fixed with `_effective_frontier_label(state)` = frontier
  label, else the label of the entry the grill node will pick next (`workflows.nodes._get_frontier_entry`,
  imported function-locally). Extracted `_entry_label` helper; 6 tests. No contract change.
  Note: the original groomed diagnosis (jump/advance clears the frontier) was refuted by reproduction
  and re-groomed in GROOMING.md.

**What shipped earlier (Phase 9 batch 2):**

- **9I (PR #48):** Tailor — optional Specific instructions textarea. Instructions placed in **user prompt** (not system) to prevent prompt injection. `_instructions` kwarg on `tailor_node` + `tailor_structured_resume`; threaded through `build_discovery_workflow`/`build_runner`. Help text says "not persisted to your profile".
- **9G (PR #51):** Track application — auto-extract title + company from JD via `web/jd_utils.py`. Null-safe with `_safe_str()`, markdown-fence stripping, `ModelAPIError` propagates, `UpgradeRequired.user_message` surfaced, form stays visible after API error.
- **9C (PR #52):** Portfolio — editable Profile section. `ProfileView` + `build_profile_view()` + `render_profile_section()` (expander, 2-col, links CRUD, Save). Load failure disables save (data-loss prevention). `ContractVersionError` re-raised in both load and save paths.
- **9E (PR #53):** Jobs — sort for-review and accepted lists by `ai_rationale` length descending (both fresh-result and prior/initial-entry paths). Lists wrapped in `st.container(height=420)`.
- **9D (PR #54):** Professional résumé template — `templates/classic_resume.html` rewritten with Inter/system-ui, A4 @page, Experience bullets, Skills pills, Education section. PDF test exercises the template directly via WeasyPrint.

**What shipped earlier (batch 1):**
- **9J (PR #47):** Checkpoint info copy in Grill view.
- **9B (PR #49):** Add-experience CTA moved before entry list.
- **9K (PR #50):** Per-entry STAR story progress indicator.

**Remaining Phase 9 tickets:** none — Phase 9 complete.

---
*Historical session notes follow (most recent first):*

**Latest this session:**
- **DURABLE WEB SESSIONS (data-loss root cause fixed):** the web grill was on `InMemorySessionService`
  (RAM only) AND `FirestoreSessionService` never persisted per-turn `append_event` deltas → grilling was
  never durable. Fixed: `append_event` override persists each turn; grill now uses `FirestoreSessionService`
  under a stable per-user id (`web_session_id`) with resume-on-load; portfolio seam shares that canonical
  id. No contract change (469 tests; regression test proves the persist). Older in-memory data is
  unrecoverable (was never written); new grilling persists + resumes. (PR pending — see below.)
- **Live bugs fixed & deployed (PR #14):** async Firestore client (`get_firestore_async_client`) →
  fixes "Couldn't reach your saved workspace"; reverted Cloud Run `concurrency=1` → fixes "Rate
  exceeded"/"Failed to fetch module".
- **Phase 4 "Portfolio Workbench" SHIPPED & deployed (PRs #15/#16/#17, 467 tests, no contract change):**
  - **4A** sidebar nav (`web/navigation.py`) — the empty left panel is now Dashboard/Portfolio/Grill/

---
*Historical session notes follow (most recent first):*

**Latest this session:**
- **DURABLE WEB SESSIONS (data-loss root cause fixed):** the web grill was on `InMemorySessionService`
  (RAM only) AND `FirestoreSessionService` never persisted per-turn `append_event` deltas → grilling was
  never durable. Fixed: `append_event` override persists each turn; grill now uses `FirestoreSessionService`
  under a stable per-user id (`web_session_id`) with resume-on-load; portfolio seam shares that canonical
  id. No contract change (469 tests; regression test proves the persist). Older in-memory data is
  unrecoverable (was never written); new grilling persists + resumes. (PR pending — see below.)
- **Live bugs fixed & deployed (PR #14):** async Firestore client (`get_firestore_async_client`) →
  fixes "Couldn't reach your saved workspace"; reverted Cloud Run `concurrency=1` → fixes "Rate
  exceeded"/"Failed to fetch module".
- **Phase 4 "Portfolio Workbench" SHIPPED & deployed (PRs #15/#16/#17, 467 tests, no contract change):**
  - **4A** sidebar nav (`web/navigation.py`) — the empty left panel is now Dashboard/Portfolio/Grill/
    Tailor nav + a compact applications list.
  - **4B** Portfolio view (`web/portfolio.py`) — read what's recorded per experience: the experience
    tree + each entry's STAR stories (`stories_by_entry`), status, and bullets.
  - **4C+4D** portfolio-mutation seam (`web/portfolio_store.py`) — **add a remembered experience/project**
    (`add_manual_entry`, the long-tenure breadth fix) and **"Grill me about this"** to steer the grill onto
    a chosen entry (`set_grill_frontier`; jumpable frontier honored by the router).
  - Spec [ARCHITECTURE.md §14](ARCHITECTURE.md); grooming [GROOMING.md](GROOMING.md) Phase 4; D10.

**▶ NEXT ACTION:** await user re-test of the grill on a FRESH session (Restart) — the checkpoint loop
could not be reproduced in isolation (regression test PR #25 proves confirm resolves over Firestore);
likely was redeploy-churn wedging + the empty-question issue, both fixed. Then continue the **multi-format
résumé exporter**: Markdown ships with Tailor (PR #26); **PDF** (make the renderer consume the tailored
JSON, not just stories) and **DOCX** (`python-docx`) are next; plus **JD-by-URL** (scraper) and
**save-as-tracked-application** for the Tailor flow. Other candidates: **4E** highlight/pin (needs an
additive-minor contract bump); pre-GA **/security-review**; custom domain.

**Web app now covers:** login → Grill (durable, Pro on BYOK, Skip, resume) → Portfolio (view/add/steer) →
**Tailor** (paste JD **or job-posting URL** → tailored résumé → **PDF / Word / Markdown / JSON** export) →
dashboard/meter. Ship changes with the [`ship-change`](../skills/ship-change/SKILL.md) skill.

**Phase 5 in progress.** **5A DONE & deployed** (PR #29): the tailored output is now a **real ATS-safe
résumé** — contact header · JD-aligned skills · **experience grouped by role** (via `StarStory.entry_id`
→ `Entry`) · education, downloadable as PDF/DOCX/MD, with the internal "why it fits" removed. Built in
`web/resume_builder.py` (deterministic assembly + one model call for selection/summary/skills) +
`web/resume_render.py`; the flat `web/tailor.py`/`web/exporter.py` were removed.
**▶ ACTIVE (branch `feat/discovery-a2a`) — CAPSTONE DELIVERABLE, due 2026-07-06 11:59pm PT.**
Pivot to a **two-agent (A2A) job-discovery** feature for the Kaggle capstone (concepts: Multi-agent · MCP ·
Agent skills · Security/HITL · Deployability · Antigravity). Design = the definitive spec (this session's
long "Multi-Agent Async Architecture Spec" message), **marrying Gemini's eval concepts with best-practice
SaaS** (my judgment is the guide; structured contracts over prose; reuse existing models).
**Deliverable cut (today; rest = roadmap):** stateful **Primary** (Groomer/Tailor, Pro) ⇄ stateless
**Scout** (Fetcher, Flash) **in-process** with the typed `EvaluationDiff` contract; real **MCP server**
(separate process, live no-key source e.g. Remotive/HN-Algolia) exposing `search_jobs`+`fetch_jd`;
**bounded loop MAX_ITERATIONS=3**; deterministic ledger HARD_REJECT + agentic eval → `match_status`+
`ai_rationale`; commit ACCEPTED/SOFT_REJECT to Firestore (idempotent `job_id`); **CLI `career-engine
discover`** demo; **on-demand Tailor reuses the deployed tailor**. Roadmap: async worker+spin-down, network
A2A, Podman sandbox, full HITL dashboard (TTL/override), multi-user.
**DONE this session:** contract **v2.5.0** ontology committed on the branch — `JobOpportunity`,
`EvaluationDiff`, `ScoutDirective`, `SessionPreferences`, `InteractionLedger`, enums, `make_job_id()` +
tests (`tests/test_discovery_schema.py`), 509 green.
**EVAL CRITERIA (user's real prefs — use as default `SessionPreferences` + Primary test fixture; later a UI
form per customer):** target_roles = Fractional Technology Leadership / consulting / highly-autonomous
Principal-level eng (e.g. via BitCrafty Inc.). nice_to_haves (soft) = AWS infra (SAP-C02-level), multi-agent
AI orchestration (ADK/LangGraph/MCP), containerized sandboxing (Podman/Linux), agile-startup / autonomous-
pipeline teams. dealbreakers (HARD_REJECT) = traditional W2 middle-management; deeply bureaucratic
enterprise; rigid 100% on-site; pure maintenance-only roles. (Plus already-applied from the ledger.)
**Package naming decision:** the whole two-agent feature lives under **one package `discovery/`** (not the
literal `mcp/` + `agents/` paths sketched earlier) — a top-level `mcp/` dir would **shadow the installed
`mcp` SDK** on `sys.path`. So: `discovery/job_source.py`, `discovery/mcp_server.py`, `discovery/scout.py`,
`discovery/primary.py`.
**NEXT build order:**
- ✅ **(1) MCP server DONE** — `discovery/mcp_server.py` (real FastMCP, stdio, `python -m discovery.mcp_server`)
  exposes `search_jobs` + `fetch_jd`; logic in `discovery/job_source.py` (pure/injectable, **live key-free
  Remotive source**, SSRF-guarded via the scraper's `_assert_safe_url`, normalises → `JobOpportunity` with
  `make_job_id`). Tests `tests/test_job_source.py` + `tests/test_mcp_server.py`; `mcp==1.28.1` pinned;
  `discovery/` added to Makefile gates. **523 green**, live smoke fetched real jobs. (branch, uncommitted→commit next)
- ✅ **(2) Scout DONE** — `discovery/scout.py`: stateless Fetcher; accesses data **only** through the MCP
  tool surface (`JobToolClient`), never importing `job_source`. `InProcessMcpClient` dispatches through the
  real FastMCP machinery (`mcp.call_tool`) — a genuine MCP client interaction, key-free + subprocess-free for
  tests/demo (stdio subprocess transport = roadmap). Tests `tests/test_scout.py`.
- ✅ **(3) Primary + bounded loop DONE** — `discovery/primary.py`: stateful Evaluator/Orchestrator.
  Deterministic `hard_reject_reason` gate (ledger already-applied / rejected company / dealbreaker keyword →
  drop, no model). Injectable `BatchEvaluator`: key-free `HeuristicEvaluator` (default, demoable) vs agentic
  `ModelEvaluator` (REASONING_HIGH→Pro on BYOK, one batch call, JSON-parsed, **falls back to heuristic on any
  parse/API error**). Pure `evaluate_batch(...) → EvaluationDiff` (stamps `match_status`+`ai_rationale`,
  computes `next_directive`). `PrimaryAgent.discover()` = MAX_ITERATIONS=3 loop, dedupes by `job_id`,
  refines directive (excludes missed companies), stops at `desired_total` or the cap. Tests
  `tests/test_primary.py`. **551 green.**
- ✅ **(4) CLI `discover` DONE** — `career-engine discover [--count N --max-iterations M --firestore]`
  (`main.py` thin cmd → `discovery/cli.py`). `run_discover` (testable, offline) runs a pre-wired Primary,
  prints ACCEPTED/FOR-REVIEW with rationale, persists accepted via a `LedgerStore`; `discover_command`
  (IO seam) resolves auth, hydrates the ledger, wires Scout+ModelEvaluator. `discovery/store.py`:
  `InMemoryLedgerStore` (default) + sync `FirestoreLedgerStore` (`discovered_jobs/{uid}/jobs/{job_id}`,
  idempotent, no secrets). `discovery/preferences.py`: `default_session_preferences()` = the operator's
  real EVAL CRITERIA. Tests `tests/test_ledger_store.py` + `tests/test_discovery_loop_cli.py`. **557 green;
  LIVE end-to-end run against real Remotive succeeded** (3 iters, ranked output, idempotent persist).
- ✅ **(5) Tailor reuse DONE** — `discover --tailor-session <SID> [-o pdf]` closes the loop: the top ACCEPTED
  job's cleaned `raw_description` is fed straight into the existing/deployed `run_tailor_command` (no new
  résumé code). `select_top_match(result)` picks the first strong match; without the flag, discover prints a
  ready-to-run `career-engine tailor …` hint. Tests added. **559 green.**

**▶ ALL 5 BUILD STEPS DONE.** The demoable slice is complete: `career-engine discover` runs the live
two-agent A2A loop (Scout ⇄ MCP ⇄ Primary) → ranked matches + rationale → idempotent persist → optional
Tailor. Safety-net floor (deployed grill→tailor) untouched.

**▶▶ MERGED (2026-07-05): PR #30 squash-merged to `master`, tagged `contract-v2.5.0`, branch deleted.**
Both review gates cleared — **Sonnet PASS** (independently re-ran `make check`; 0 must-fix) + **Copilot**
(3 comments; fixed the real id-collision bug + doc timestamp, deferred Firestore `get_all()` batching with
rationale). Fixes folded in: skip id-less postings, catch `ScraperError` in `discover`, simplify
`APPROVE_BATCH`. **master is green (560 tests), tree CLEAN.** The two-agent A2A discovery feature is DONE.

**RESUME NEXT SESSION — remaining before submission (due 2026-07-06 11:59pm PT):**
1. **PACKAGING** (user-owned): video + writeup + README + architecture diagram. User is running NotebookLM
   on the docs to draft script/diagram/writeup/README — **review those drafts against the code so nothing
   overclaims.** Best NotebookLM source set: `docs/ARCHITECTURE.md` §15, `docs/DISCOVERY_DEMO.md` (verified
   demo commands to record), this file, and the merged PR #30.
2. **Record the demo** from `docs/DISCOVERY_DEMO.md` (CLI, terminal capture — no deploy needed). For
   real-reasoning rationales, export a BYOK `DEV_GEMINI_KEY` in the shell (never in code/chat).
3. Optional: a README "Job Discovery" section (20-pt docs score).
**Deploy is NOT required** (discover is a CLI demo; the deployed web grill→tailor floor is unaffected).
**Deferred roadmap (not blocking):** network/stdio A2A, Podman sandbox, async worker + spin-down, full HITL
dashboard (TTL/override), multi-user session isolation, Firestore `get_all()` batching. (See ARCHITECTURE §15.5.)
**PACKAGING (protected, own session Mon eve):** 5-min video, writeup, README + architecture diagram (~40+
pts; can be drafted in parallel by a designer/communicator). **Rule: nothing risky Monday; capture demo
footage EOD Sunday.**
**Deferred (pre-capstone Phase 5):** persist Contact (+minor); 5B save-as-application; 5C one renderer;
4E highlight; pre-GA /security-review; grill re-test (checkpoint loop unreproducible, PR #25).

- **Live dev URL:** https://career-engine-dev-app-ontyg6kaja-uc.a.run.app. Project `gen-lang-client-0513394764`, region us-central1.
- **CI/CD (works):** `gh workflow run deploy.yml --ref master -f environment=dev` → keyless WIF → docker build+push → `terraform apply`. State in GCS bucket `gen-lang-client-0513394764-tfstate` (prefix `envs/dev`). Repo *variables* drive it (GCP_PROJECT_ID/WIF_PROVIDER/DEPLOY_SA/TF_STATE_BUCKET/AR_LOCATION/CE_AUTH_*).
- **What shipped (PR #11 + follow-ups):** Streamlit OIDC login (`st.login`); `web/grill_ui.py` interactive grill (start→Q&A→checkpoint→finalize→PDF); BYOK key set-once in Secret Manager (revoke/replace); Terraform auth wiring + scoped `ce-key-*` IAM + `datastore.user`; single-user isolation (`max_instances=1`, concurrency=1); `docker-entrypoint.sh` writes secrets.toml (json-escaped) from env.
- **Bootstrap done out-of-band (one-time, NOT in main state):** billing link, OAuth client (Console), `cloudresourcemanager` + `serviceusage` + others enabled, WIF pool/provider `github-pool`/`github-provider` (repo-conditioned), deployer SA `career-engine-deployer`, GCS state bucket. Secret VALUES (`ce-auth-client-secret`, `ce-auth-cookie-secret`, `ce-key-*`) set out-of-band, never in state.
- **REQUIRED before GA:** a `/security-review` of web login + paid-key storage + broad deployer-SA roles (see [SECURITY.md](SECURITY.md) "Required next review").
- **Remaining follow-ups:** (a) web PDF upload (`st.file_uploader`→`parse_resume`) — the résumé starting point; (b) custom domain `career-engine.bitcrafty.cloud` (hyphenated) via Cloudflare + update OAuth redirect + `CE_AUTH_REDIRECT_URI`; (c) sweep endpoint HTTP adapter (deferred; scheduler 404s until then); (d) curate deployer-SA roles down.
- **Deadline:** Kaggle × Google submission **2026-07-06**.
- **Grill hardening (feat/grill-hardening, contract v2.4.0):** from the user's real run — (A) graceful `ModelAPIError` handling so a `429`/quota shows a friendly resumable message, not a crash; (B) `grill_answers` per-entry memory (accumulated extraction + no re-asking); (C) frontier ranks current/substantive roles first (`end_date` present-first + experience-type weight). See ARCHITECTURE §6.3.1.
- **Deadline:** Kaggle × Google submission **2026-07-06** — product + writeup + video.
- **Known live-run constraint:** the Gemini **free tier is 5 req/min + 20/day**; a full live session needs a paid/raised-quota key (deterministic tests prove the pipeline without one).
- **Workflow (Copilot budget reset):** each chunk = **new branch → build → `make check` green → Sonnet
  review (subagent) + fix → push → `gh pr create` → request Copilot (`gh api --method POST
  repos/{owner}/{repo}/pulls/N/requested_reviewers -f 'reviewers[]=copilot-pull-request-reviewer[bot]'`,
  reviewer surfaces as login `Copilot`) → wait via `skills/wait-for-pr-review` → read comments
  (`gh api repos/{owner}/{repo}/pulls/N/comments`) → address → squash-merge (`gh pr merge N --squash
  --delete-branch`)**. `gh` authed as `suchakra`; jq + terraform + gh all present.
- **ORDERED QUEUE (one PR each, in order):**
  1. **Security review** ✅ DONE — merged via **PR #2** (squash, 398 tests). Fixed HIGH auth
     `aud`/`iss` gap + MED–HIGH scraper SSRF; added [SECURITY.md](SECURITY.md). Sonnet PASS +
     Copilot addressed.
  2. **Monitoring/logging** for graph hangs ✅ DONE — merged via **PR #3** (405 tests):
     `workflows/observability.py` + monitored model client + per-request model timeout
     (`settings.model_timeout_seconds`) + `graph.turn` span.
  3. **CoT tuning** ✅ DONE — merged via **PR #4** (409 tests, **contract v2.3.0**, tag
     `contract-v2.3.0`): Free-Mode Pro-escalation gate in `execute_grill_turn_node` (per-entry
     `grill_attempts`, escalates after 6 failed attempts, above the checkpoint boundary) + CoT tuning.
  4. **Phase 2 deferred wiring** ✅ DONE — merged via **PR #5** (423 tests): `web/session_loader.py`
     (meter discovery-state load, wired into `streamlit_app`); `jobs/sweep_endpoint.py` (OIDC
     aud/iss-verified sweep handler); `terraform` in `.devcontainer` (rebuild to take effect).
  5. **Capstone dry-run** ✅ DONE — merged via **PR #6** (424 tests). Executed end-to-end; the live
     run found + fixed a real null-STAR-field crash; free-tier 5-req/min ceiling documented (live PDF
     needs a paid key). Evidence captured in [CAPSTONE_RUNBOOK.md](CAPSTONE_RUNBOOK.md).
- **Infra/repo hygiene DONE (PR #7):** root [README.md](../README.md); CI (`.github/workflows/ci.yml`
  — `make check` + `make tf-check` on push/PR, credential-free, green on GitHub) + manual WIF deploy
  (`.github/workflows/deploy.yml`); proprietary [LICENSE](../LICENSE). Fixed a build portability bug
  the local env masked (bogus setuptools backend → `setuptools.build_meta` + explicit packages).
  `.env`/`*.tfvars` git-ignored — safe to make the repo public.
- **Deploy image DONE (PR #8):** `Dockerfile` (Streamlit on `$PORT`, non-root, WeasyPrint libs),
  `.dockerignore` (no secrets), `cloudbuild.yaml`, `make build`/`make cloud-build`; CI builds +
  smoke-tests the image. Deploy path is now complete end-to-end except live GCP creds.
- **What's next (queue exhausted):** no scheduled work remains. Candidate follow-ups (unscheduled) —
  **GCP live setup** (create the WIF pool/provider + repo secrets, `gcloud builds submit` an image,
  `make deploy`, run the `deploy.yml` dispatch); the outermost Phase-2 glue (mount
  `jobs/sweep_endpoint.py` in a served app + Identity Platform *frontend* token exchange); a
  **dev-only web view** so the Streamlit dashboard is demoable locally without an IdP token; a live
  PDF pass with a paid/raised-quota key. Await direction before starting.
- **State:** tags `contract-v1.0.0…v2.2.0`; gates `make check` (389) + `make tf-check`. Phase 2 deferred
  thin wiring (item 4 above) is logic-built+tested, only outer glue remains.
Phase 1.7 DONE (tagged `contract-v2.1.0`, pushed). Phase 2 increment built this session, Opus-direct
(unpushed):
  - **2C** Terraform infra (`infrastructure/` modules + dev/prod + README + Makefile `tf-check`/`deploy`/`destroy`).
    `fmt`+`validate` green BOTH envs; `plan`/`apply` need GCP creds (operator step).
  - **contract v2.2.0** (additive): `UserWorkspace` (per-user portfolio doc) + `Application`/`ApplicationStatus`
    + `PendingAction`. Decided: a NEW UserWorkspace model (not fields on CareerEngineState).
  - **2D** `jobs/pending_action_sweep.py` — pure+idempotent 14-day sweep + `WorkspaceStore` orchestration.
  - **2A** `web/` Streamlit dashboard — pure view-model + injectable renderer (testable sans Streamlit);
    `career-engine web` launches it. Tailoring never gated.
- **terraform was installed ad-hoc in the devcontainer — see memory: add it as a devcontainer dependency.**
- **NEXT:** Copilot-gate the Phase-2 diff (`4f240ac..HEAD`) → tag `contract-v2.2.0` → push. Then:
  **2B** (web auth/Identity Platform), the **Firestore `UserWorkspace` repository** (real `WorkspaceStore`
  backing 2D + 2A; + streamlit auth/session load), **2E** (capstone runbook + evidence, `skills/cloud_ops/SKILL.md`).
- **Deferred wiring (not yet built):** `UserWorkspace` Firestore load/save; streamlit auth + state load
  (currently renders empty workspace). Both are thin adapters over tested logic.
Phase 0 + Phase 1 + Phase 1.3 + Phase 1.5 + **all of Phase 1.7** are built (**339 tests**; `make check`
green). Sonnet review verdict **PASS** (0 must-fix; 4 nits applied incl. a discovery-turn empty-question
fallback). Phase 1.7 closed the deferred Phase-1/1.5 integration seams, all Opus-built this session +
Sonnet-reviewed (Copilot gate planned):
  - **1.7-A** resume-file upload wired into `grill` (`--resume-file`).
  - **1.7-B** true session resume (`get_session_state_if_exists`, load-before-create).
  - **1.7-C** `discovery_turn_node` wired into the main graph + router branch — contract bumped
    **v2.0.0 → v2.1.0** (additive `coverage_confirmed`; user-approved).
  - **1.7-D** FakeFirestore doubles moved to `tests/fakes.py`.
- **Pushed:** the full 1.7 series + reviews + tag `contract-v2.1.0` are on origin/master. Tree clean.
- **NEXT:** **Phase 2** (web/infra/async) per [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md).
- **Carried into Phase 2 polish** (non-blocking): the scripted end-to-end capstone runbook (resume-file →
  discovery → resume → tailor), plus Copilot's 3 optional 1.7 nits in [REVIEW.md](REVIEW.md) —
  (1) friendlier message for extensionless resume files, (2) a `coverage_through` schema docstring note
  that only `ingest_node` writes it, (3) make the resume-CLI test resilient to a `resolve_auth_and_client` rename.
- **To IDEATE:** read this file, then [ARCHITECTURE.md](ARCHITECTURE.md) + [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md); capture new ideas back into the docs (don't mutate a spec that's mid-build — version-gate instead).

---

> Purpose: pick up cleanly after a session reset. Written 2026-06-29.
> Companion to [PROGRESS.md](PROGRESS.md) (live status), [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)
> (roadmap), [AGENT_EXECUTION_PROMPT.md](AGENT_EXECUTION_PROMPT.md) (builder/reviewer prompts).

## Where we are
- **Branch `master`** — origin behind by the Phase-1.7 series + docs, awaiting Copilot review + push.
- **Contract: v2.1.0** (tags `contract-v1.0.0`, `contract-v1.1.0`, `contract-v2.0.0`; **`contract-v2.1.0`
  to be tagged after review**). v2.1.0 adds `coverage_confirmed` (additive, backward-compatible).
  Changing `schema.py`/`config.py`/public interfaces requires a `CONTRACT_VERSION` bump.
- **Phase 0:** ✅ frozen. **Phase 1 (WS-A/B/C/D + integration):** ✅ COMPLETE. **Phase 1.3:** ✅ done.
  **Phase 1.5:** ✅ COMPLETE (all 5 pieces). `make check` = ruff clean, mypy --strict clean,
  **317 tests pass (~6s)**. CLI discovery loop runs end-to-end (turn-based HITL) → PDF; entry-based grill
  loop; vision resume parser + multimodal adapter; progressive-discovery nudge/meter/return-loop.
- All Phase-0/Phase-1/Phase-1.5-CORE worktrees pruned. Phase 1.3 and Phase 1.5 INGEST+DISCOVERY were done
  in-place on `master`.

## NEXT: Phase 1.7 then Phase 2 (web / infra / async)
Phase 1.5 is done. Phase 1.7 closes the deferred integration seams listed in the "YOU ARE HERE"
banner above. After that, Phase 2 proceeds per
[REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md):
- **Phase 2:** Streamlit web workspace (reuse the `cli/` runtime seam), `infrastructure/` Terraform
  (Cloud Run, Firestore, Artifact Registry, Secret Manager + SA `secretAccessor`, Cloud Scheduler;
  envs dev/prod), `jobs/pending_action_sweep.py` (14-day), `skills/cloud_ops/SKILL.md`.
- **Phase 3:** `evaluation/user_simulator.py` + `test_config.json`, monitoring/logging, security review.
- Launch as Sonnet builders in worktrees, fan-out where files are disjoint.

## Process (how we work — keep doing this)
**Use the [`ship-change`](../skills/ship-change/SKILL.md) skill for every code change** — it encodes
this whole loop (branch → gate → dual review → merge → deploy → verify) so it runs the same way each
time, and its `scripts/deploy_and_verify.sh` automates the merge+deploy+verify tail. Use the sibling
[`wait-for-pr-review`](../skills/wait-for-pr-review/SKILL.md) skill to block for Copilot's review instead
of hand-rolling a poll loop.

**The standard per-change loop (every code change goes through this) — updated 2026-07-06:**
1. **Subagent builds** the change on a fresh branch (`fix/…`, `feat/…`). Subagents are Sonnet
   by default; worktree-isolated for large changes (`isolation: "worktree"`).
2. **`make check` green** (ruff + mypy --strict + pytest) — plus `make tf-check` for infra changes.
   Subagent must not declare done unless gates pass.
3. **Gemini 2.5 Pro reviews** the diff as an independent gate — launched as a separate review subagent
   (`model: "Gemini 2.5 Pro (Google)"`). Reviewer re-runs gates, reads the diff, returns
   PASS / CHANGES REQUESTED with a reason list. Address CHANGES REQUESTED and re-review before pushing.
   *(Replaces the old Sonnet/Opus review step — Claude subscription ended.)*
4. **PR created** (`gh pr create`), then **Copilot review requested**
   (`gh api --method POST repos/{owner}/{repo}/pulls/N/requested_reviewers -f
   'reviewers[]=copilot-pull-request-reviewer[bot]'`; surfaces as login `Copilot`).
5. **Address Copilot comments** (fix + reply), CI green.
6. **Squash-merge** (`gh pr merge N --squash --delete-branch`).
7. **Deploy** (`gh workflow run deploy.yml --ref master -f environment=dev`) + verify HTTP 200 live.
8. **Reconcile docs** in the same session (PROGRESS/HANDOFF/etc.).

So: **Subagent builds → Gemini 2.5 Pro reviews → PR → Copilot reviews → address → merge → deploy.**
Two independent review gates (Gemini + Copilot) plus CI.
- **For large, file-disjoint work:** launch parallel Sonnet subagents in worktrees; Gemini 2.5 Pro
  reviews each branch independently before its PR.
- No agent self-declares done; only a review PASS ticks `docs/PROGRESS.md`. The reviewer independently
  re-runs gates and reads the diff.
- **master must stay green after every commit** (`make check`; `make tf-check` for infra). Contract
  changes require a `CONTRACT_VERSION` bump + tag after review PASS.

## Known gotchas
- **Shared-env mypy coupling:** gates depend on installed packages; `make check` on master is the source
  of truth. (`config.py` already uses `import google.cloud.firestore as firestore` to avoid the namespace quirk.)
- **Two model-client interfaces** (nodes vs scraper) — integration adapter bridges both.
- **WS-C:** `create_session` is last-write-wins (vs ADK raise-on-duplicate); ADK event log not durably
  persisted (CareerEngineState is). `FakeFirestoreClient` lives in the prod module — candidate to move to `tests/`.
- **v1.1.0 conversational fields:** CLI sets `pending_user_answer` + `checkpoint_verified`; reads
  `current_question` + `checkpoint_delta_summary`. finalize→`professional_summary`+`master_resume_json`;
  tailor reads `jd_text`+`master_resume_json`, writes `tailored_resume_json`.
