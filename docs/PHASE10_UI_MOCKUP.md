# CareerEngine — Phase 10 UI Mockup (Next.js frontend)

> **Status:** `draft` · **Last reviewed:** 2026-07-07 · **Owner job:** proposed visual/UX design for
> the Phase 10 Next.js frontend (slices 10.5 / 10.6).
> This is a **design proposal**, not shipped reality — build status is canonical in
> [PROGRESS.md](PROGRESS.md). The architectural decision this UI sits on top of is
> [ARCHITECTURE.md §16](ARCHITECTURE.md) (Streamlit → Next.js + FastAPI); build slices are in
> [GROOMING.md](GROOMING.md) Phase 10. The screens below are a **1:1 re-housing of the current
> Streamlit feature set** (no new product scope) — every element maps to an existing `web/` view so
the migration is presentation-only, per AD-16.2. Two items are explicitly flagged as **planned
near-term additions** rather than current scope: a **location / work-model preference** in Profile
(§4.2, §9) and the future outreach/interview/salary features (§9); the shell reserves space for both.

> **Independent design review (2026-07-07):** an independent UX reviewer graded this **"Good with
> revisions"** — IA, consent pattern, and visual system sound; must-fixes were a Dashboard pre-flight
> key card, an explicit mobile spec, and clarifying grill-component reuse. Those are now folded in
> (§4.1 key card, §6 mobile, §9 `StreamingTranscript`). Remaining open items are tracked in §8.

---

## 1. Design goals (what "good" means here)

The four standing product goals ([GROOMING.md](GROOMING.md)) translate to UI intent:

1. **Quality without fake confidence.** Show real state — grill progress, "why this job fits"
   rationale, checkpoint confirmations — never a spinner that hides an error.
2. **Cost transparency (BYOK).** The user runs on *their own* Gemini key. The UI must make key
   status, and which actions consume it, obvious and calm — not nagging.
3. **Privacy-first.** Identity is a single verified edge (`user_id`); the key lives in Secret
   Manager. The UI never displays or echoes the raw key or token.
4. **Demoable end-to-end.** A judge/first-time user should get from login → grill → tailored résumé
   in one obvious path, with the "happy path" always visible and discovery treated as a *nudge, never
   a gate*.

**UX principles adopted:**
- **One primary action per screen.** Each view has a single, unmistakable `primary` CTA.
- **Progressive disclosure.** Forms (profile, preferences, contact header, add-experience) live in
  collapsible sections so the default view is calm; power actions are one click away.
- **Optimistic, no full-page reloads.** Every write posts via the API and updates in place (the whole
  reason for leaving Streamlit's rerun model — AD-16.2); the client data layer that implements this
  (optimistic mutation + rollback + cache invalidation) is **AD-16.8** ([ARCHITECTURE.md §16](ARCHITECTURE.md)).
- **Streaming is first-class.** The grill renders token/step-by-step over SSE (AD-16.5), not as a
  frozen page waiting for a turn.
- **Recoverable by default.** Load failures degrade to a typed empty state and disable *save* (never
  silently overwrite), mirroring the current stores.

---

## 2. Visual system

| Token | Choice | Rationale |
|-------|--------|-----------|
| **Brand** | **bitcrafty** wordmark (Inter SemiBold), tagline "Engineering transformation for the AI era." (Inter Regular) | CareerEngine is an open-source project hosted by bitcrafty; the app carries bitcrafty brand cues (footer + auth/landing), so on-screen and exported artifacts feel like one product family. |
| **Type** | Inter / system-ui; Inter SemiBold for wordmark/headings; tabular numerals for metrics | Matches the bitcrafty wordmark and the shipped `templates/classic_resume.html` (Inter) so on-screen and exported résumés feel like one product. |
| **Base palette** | Near-black text on off-white (bitcrafty black `#1F1F1F` on `#FAFAF9`) | High legibility for long transcripts + résumé text; ATS-résumé aesthetic. |
| **Accent** | bitcrafty purple (`#5E3FA6`) for primary actions + active nav | One brand accent keeps "the next action" unambiguous. |
| **Status colors** | green = strong/documented, amber = for-review/needs-quantifying, slate = skipped/neutral | Reused consistently across Jobs tiers *and* Portfolio entry status so the same semantics read the same everywhere. |
| **Radius / density** | 12px cards, generous line-height, roomy tap targets (≥44px) | Comfortable on desktop + usable on tablet; résumé content wants air. |
| **Components** | shadcn/ui (Radix primitives) + Tailwind | Accessible-by-default primitives (focus rings, dialog semantics, `aria`), OpenAPI-typed data, fast to build the 10.5/10.6 shell. |
| **Motion** | Subtle: 150ms ease-out fades; streamed tokens appended in ~16–40ms batches (no per-token reflow); skeletons for reads | Signals liveness without gratuitous animation. |

**Concrete tokens (to lock in 10.5, validated with a contrast + colorblind checker):**

| Token | Light | Dark | Notes |
|-------|-------|------|-------|
| Text / bg | `#1F1F1F` on `#FAFAF9` | `#E6E8EC` on `#161418` | bitcrafty black; AA at body sizes; dark mode re-tested, not a naive invert. |
| Accent (primary) | `#5E3FA6` (bitcrafty purple) | `#9B7FD4` | Lighter purple in dark to keep AA on dark bg. |
| Status · strong/documented | `#047857` (green) | `#34D399` | Paired **always** with a label + glyph (● / ✓), never color alone. |
| Status · for-review/needs-quantifying | `#B45309` (amber) | `#FBBF24` | Green↔amber checked under protanopia/deuteranopia (glyph differs: ● vs ◑). |
| Status · skipped/neutral / invalid key | `#4B5563` (slate) / `#DC2626` (error) | `#9CA3AF` / `#F87171` | Invalid-key state gets the error hue + ✗ glyph. |

- **Type scale:** `h1` 28/34 semibold · `h2` 20/28 semibold · `h3` 16/24 medium · body 15/24 ·
  caption 13/18. Semantic headings (`<h1>`…) drive the screen-reader outline; visual size never
  substitutes for heading level.
- **Focus:** 2px `#5E3FA6` (dark: `#9B7FD4`) `:focus-visible` ring at 2px offset on every interactive
  element, on both themes (verified visible on dark bg). No focus suppression.
- **Dark mode is a validated second theme**, not an inversion — the table above is the source of
  truth; contrast + colorblind checks run in the 10.5 spike before the palette is frozen (§8).
- **Light / dark / system.** The app ships **both a light and a dark theme** driven by CSS variables
  (one token set, two value maps). Default = **follow the OS** (`prefers-color-scheme`); a manual
  **Light · Dark · System** toggle in the identity menu overrides it and the choice is **persisted**
  client-side (localStorage) so it survives reloads on the same browser. This is a pure client
  preference — **no theme field is added to `schema.py` and no server round-trip / contract change**
  is implied. SSR renders with
  no theme flash (inline theme script sets the class before paint). Every mock in this doc is
  theme-agnostic — both themes use the same layout, only the token map changes.

**Foundational components (built first in 10.5, before screens).** The visual system above is realized
by a small set of shared, shadcn/ui-backed components; screens **compose** these — no screen
re-implements a card, badge, or form row. Standing this inventory up first is what lets 10.5/10.6
assemble rather than reinvent.

| Component | Realizes / used by | Notes |
|-----------|--------------------|-------|
| `AppShell` + `SidebarNav` | grouped BUILD/APPLY/PREPARE nav, identity + key chips, theme toggle (§3/§9) | Feature-flagged rows stay hidden until live. |
| `StatusBadge` | strong / for-review / skipped status across **Jobs tiers + Portfolio entries** (§2) | Color **plus label + glyph** always (● / ◑ / ✓ / ✗) — never color alone. |
| `ActionCard` | dashboard pending-actions, job tiles, portfolio entries | 12px radius; **one primary CTA** per card. |
| `PrimaryButton` / `SplitButton` | the single primary CTA per screen; **Build résumé → PDF/Word/MD** split | Enforces "one primary action per screen." |
| `StreamingTranscript` | grill (10.6); reused by interview-prep + negotiator (§9) | Transcript + SSE stream + composer; **turn controller injected** (AD-16.5). |
| `ConsentDialog` + `ConfirmSendDialog` | one-time connected-account grant + per-send confirm (§9) | Reused by the later-phase emailer (post-launch, roadmap Phase 13.C); consent recorded to Settings. |
| `CollapsibleSection` + `Field` | progressive-disclosure forms: profile, preferences, contact header, add-experience | Calm default view; power actions one click away. |
| `EmptyState` | typed load-failure / empty read views | Disables **save** (never silent overwrite) — "recoverable by default." |
| `MetricStat` | discovery progress + coverage meters | Tabular numerals (§2). |
| `ResumePreview` | master + tailored résumé preview | Server-rendered WeasyPrint HTML in an iframe vs a lighter React view is the §8 open item; one component either way. |
| `Toast` / `InlineError` | optimistic-write rollback + inline validation surface | Backed by the data layer (AD-16.8). |

All are thin wrappers over shadcn/ui (Radix) primitives (§2) — accessible-by-default, not bespoke.

---

## 3. Global app shell

Persistent left sidebar (collapsible to icons on narrow viewports; bottom tab bar on mobile). Top bar
carries context title + the two "always-true" status chips: **identity** and **key**.

**The sidebar is grouped by journey stage, not flat** — this is a deliberate choice to absorb the
known future features (emailer/outreach with consent pages, interview prep, salary negotiator) without
an IA redesign later (see §9). Ship the **Build** + **Apply** groups now; the greyed rows below are
placeholders showing where committed-roadmap features slot in.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  CareerEngine                          Dashboard        [🔑 Key: saved ✓]  ▐ ● │  ← top bar
│                                                             user@example.com ▾ │     (identity menu)
├───────────────┬──────────────────────────────────────────────────────────────┤
│  ◉ Dashboard  │                                                              │
│               │                                                              │
│  BUILD        │                    « active screen content »                 │
│  ○ Portfolio  │                                                              │
│  ○ Grill      │                                                              │
│               │                                                              │
│  APPLY        │                                                              │
│  ○ Jobs       │                                                              │
│  ○ Tailor     │                                                              │
│  ○ Outreach ⋯ │  ← future: emailer (needs consent) — greyed "Coming soon"    │
│               │                                                              │
│  PREPARE      │  ← future group                                              │
│  ○ Interview ⋯│  ← future: interview prep                                     │
│  ○ Salary   ⋯ │  ← future: salary negotiator                                  │
│  ───────────  │                                                              │
│  Recent apps  │                                                              │
│  • Acme — SWE │                                                              │
│  • Globex —PM │                                                              │
│  ───────────  │                                                              │
│  ⚙ Settings   │  ← key · connected accounts · consents · privacy             │
│  [Sign out]   │                                                              │
└───────────────┴──────────────────────────────────────────────────────────────┘
```

- **Grouped nav** (`BUILD` / `APPLY` / `PREPARE`) scales to ~8–10 destinations without the "flat list
  gets long" problem flagged in the original open questions — and now that we *know* the app grows,
  grouping is the correct call up front. Collapses to grouped icons on narrow viewports.
- **Empty groups are hidden, not shown greyed.** A journey group renders only when it has ≥1 live
  destination; in Phase 10 the whole `PREPARE` group is **hidden** (no live items). Future items ship
  behind a feature flag — when a flag is on but the feature is pre-launch, its row shows a small
  "Soon" badge and is `aria-disabled` (focusable, announces "coming soon", no navigation), never a
  dead click. The diagram above shows the *end-state*; Phase 10 renders only `Dashboard · BUILD ·
  APPLY (Jobs, Tailor) · Settings`.
- **Recent apps** caps at 5 with a **"View all →"** link to Dashboard (the list never grows the
  sidebar unbounded); the block is scroll-free.
- **Back affordance:** top-level destinations have no back button; only *nested/hand-off* contexts do
  (e.g. Grill entered via "Grill me about this" shows "← Dashboard"). On mobile the system/browser
  back + the bottom tab bar cover navigation, so the in-page back is nested-only.
- **Identity menu** (top-right): email + Sign out. The `user_id` (OIDC `sub`) is never shown; email
  is display-only.
- **Theme toggle** lives in the identity menu: **Light · Dark · System** (default System). The choice
  is persisted per user and applied before first paint (no flash-of-wrong-theme). See §2.
- **Key chip:** `saved ✓` (green), `this session only` (amber), or `add a key` (link → Grill key
  panel). One glanceable indicator of BYOK state, everywhere.
- **Settings** (new destination): consolidates BYOK key management, **connected accounts + consents**
  (the home for the emailer consent records), and privacy/data controls. Introducing it now means
  future consent-gated features have an obvious place to live.
- **Recent apps** in the sidebar mirrors the current compact applications list; each links to its
  Dashboard card.
- **Route = URL.** `/dashboard`, `/portfolio`, `/grill`, `/jobs`, `/tailor`, `/settings` (App
  Router); future `/outreach`, `/interview`, `/salary`. Deep links and back-button work — the thing
  Streamlit could not do.
- **Footer / brand (bitcrafty).** A slim persistent footer carries "**Open source project hosted by
  bitcrafty**" (link to the repo) alongside the bitcrafty tagline; the login/landing screen leads
  with the bitcrafty wordmark + tagline. Product name in-app stays "CareerEngine"; bitcrafty is the
  hosting/brand family cue, kept lightweight (footer + landing, not chrome on every screen).

---

## 4. Screens

### 4.0 Login / landing — "one obvious way in" (bitcrafty-branded)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                                │
│                          bitcrafty  (wordmark, Inter SemiBold)                 │
│                    Engineering transformation for the AI era.                  │
│                                                                                │
│                               CareerEngine                                     │
│              Turn your experience into quantified, ATS-ready résumés.          │
│                                                                                │
│                        [  Sign in with Google  ] (primary)                     │
│                                                                                │
│        Privacy-first · bring your own Gemini key · your data stays yours.      │
│                                                                                │
│  ─────────────────────────────────────────────────────────────────────────    │
│           Open source project hosted by bitcrafty · GitHub ↗                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **The single edge into the app** — one primary action (Google sign-in via the 10.1 Firebase auth
  boundary). No pricing wall, no secondary CTAs competing for attention.
- **bitcrafty brand up top** (wordmark + tagline), product identity below; the footer carries the
  "Open source project hosted by bitcrafty" line + repo link (also present app-wide, §3).
- **Privacy one-liner** sets the BYOK/privacy expectation before login.
- Respects the active theme (light/dark) and shows the theme toggle even pre-auth.

### 4.1 Dashboard — "where am I, what's next"

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Welcome back 👋                                                               │
│                                                                                │
│  Portfolio progress  ▓▓▓▓▓▓▓▓░░░░  62%   · 14 stories · 3 checkpoints passed   │
│                                                                                │
│  ┌── Pick up where you left off ─────────────────────────────────────────┐    │
│  │  [ ▸ Continue grilling ]   (primary)                                   │    │
│  │  [  Tailor a résumé  ]     [  Find jobs  ]                             │    │
│  └───────────────────────────────────────────────────────────────────────┘    │
│                                                                                │
│  Pending actions (3)                          Tracked applications (5)         │
│  • Follow up: Acme — SWE (day 9/14)           • Acme — SWE      · applied      │
│  • Add metrics to "Migration project"         • Globex — PM     · applied      │
│  • Confirm checkpoint in Grill                 …                               │
│                                                                                │
│  ⓘ You haven't grilled in 6 days — a 5-min session keeps your portfolio sharp. │  ← dismissible nudge
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Progress meter** = discovery session health (question count / phase / checkpoints). Reads from
  `GET /api/dashboard`.
- **One primary CTA** ("Continue grilling") with two secondary shortcuts — the three current entry
  buttons, re-ranked so the resume-your-work action leads.
- **Nudge** is a dismissible banner, *never* a modal or gate (discovery is a nudge, per current
  behaviour).
- **Pending actions** + **Tracked applications** as two scannable columns (14-day follow-up sweep
  surfaces here).
- **Pre-flight key card (first-run fix, from design review):** when **no key is resolved**, the
  Dashboard's top card becomes an inline key setup — "Set up your Gemini key (≈30s)" with a password
  field + "Save & use this key" + a link to get one. This collapses the first-time path from *login →
  Dashboard → Grill → key panel → fill → start* (5 steps) to *login → Dashboard key card → Start
  grilling* (2 steps) — directly serving the "demoable end-to-end for a judge" goal. Once a key is
  saved the card reverts to the normal "pick up where you left off" block.
- **Day-1 empty copy:** progress reads "Portfolio progress — not started · grill your first
  experience to begin" (no fake 0% bar); the single primary CTA is "Start grilling".

### 4.2 Portfolio — "everything the AI knows about me, editable"

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Portfolio                                   [ + Add experience ]  [ Build master résumé ▾ ] │
│                                                                                │
│  ▾ Profile                                                              (edit) │
│     Jane Doe · jane@example.com · +1 …   · Berlin                              │
│     linkedin.com/in/jane · github.com/jane          [ Save ] (disabled unless dirty) │
│                                                                                │
│  Experience (newest first)                                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ 📌 Senior Engineer — Acme            2022–present · role · ● DOCUMENTED │  │
│  │    • Cut p95 latency 40% by …                                     (edit) │  │
│  │    • Led migration of 12 services …                                      │  │
│  │    ▾ STAR stories (3)                                                     │  │
│  │        “Latency win” — S/T/A/R …                              [ Delete ] │  │
│  │    [ Grill me about this → ]                                              │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │    Data Platform (project)           2021 · project · ◑ NEEDS QUANTIFYING│  │
│  │    Not grilled yet — start a grill to capture achievements here.         │  │
│  │    [ Grill me about this → ]                                              │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Profile** is a collapsible section; **Save disabled until dirty** and **disabled entirely on load
  failure** (data-loss prevention, matches current store behaviour).
- **Location & work-model preference (planned near-term setting — not current scope).** Location is
  *not* a job-search preference today; it will live here in Profile as a structured setting the Jobs
  rubric inherits (§4.4). Shape: a **base location** (e.g. "GTA, Ontario, Canada") plus a **remote
  scope** selector (`On-site` · `Hybrid` · `Remote within {region}` · `Remote anywhere`), e.g.
  "Remote within Canada". Kept structured (not free text) so Jobs can filter/rank on work-model +
  geography consistently. Reserved in the mock now; wired when the setting ships (its own additive
  contract bump, per AD-16.7) — flagged so the 10.5 Profile form leaves room for it.
- **Entry cards** carry pin (📌 highlight → prioritised in Tailor), status dot (green/amber/slate),
  inline-editable bullets, expandable STAR stories with delete, and the **"Grill me about this →"**
  hand-off that pins the frontier and routes to Grill.
- **Add experience** opens a right-side sheet (title, org, type, dates, notes) — sheet instead of an
  inline expander so the timeline doesn't jump.
- **Build master résumé** is a split button → PDF / Word / Markdown, generated on demand (cached).
- **Empty state:** friendly "Nothing recorded yet — start a Grill" with a primary Grill CTA.

### 4.3 Grill — "the interactive core" (streaming)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ← Dashboard          Grill                                        [ ↺ Restart ]│
│  📌 Currently grilling:  Senior Engineer — Acme                                 │
│                                                                                │
│  ┌── transcript (scrolls) ───────────────────────────────────────────────┐    │
│  │  🤖  Tell me about a time you improved performance at Acme.            │    │
│  │  🙂  We had latency issues on checkout…                                 │    │
│  │  🤖  Nice — can you put a number on the improvement?  ▍(streaming…)     │    │
│  └────────────────────────────────────────────────────────────────────────┘    │
│                                                                                │
│  [ Skip this experience → ]                                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  Your answer…                                                    [ ▸ ]  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘

  ── checkpoint state ──                     ── first-run seeding state ──
  ✅ Checkpoint reached — 4 stories saved.    Drop your résumé (PDF/img) ⇪  or paste
     Visible in Portfolio.                    your career history, then:
  [ Looks right — keep going ] (primary)      [ ▸ Start grilling ] (primary)
```

- **Currently-grilling banner** is always correct on resume (server derives it via
  `_effective_frontier_label`, per BUG-2). This is a hard requirement, called out in the mockup so the
  frontend never re-derives it client-side.
- **Streaming transcript:** assistant turns stream token-by-token over the 10.4 SSE endpoint; a
  caret/typing indicator shows liveness; the composer disables mid-turn.
- **Checkpoint** appears inline as a confirm card ("Looks right — keep going", primary) — explicit
  human confirmation, never auto-advanced past a checkpoint.
- **Skip** is the always-available escape hatch.
- **First-run seeding:** résumé drag-drop (vision-parsed) *or* paste history → "Start grilling".
- **Key panel:** if no key is resolved, an inline, dismissible panel: password field →
  "Save & use this key" (persists to Secret Manager) + "this session only" explainer. Key is never
  echoed back. **Key lifecycle (from review):** *saved ✓* = in Secret Manager, reused across
  sessions; *this session only* = held in memory for the tab, with the warning "won't be saved or
  resumable — closing this tab clears it"; an **invalid/expired key** flips the chip to error (`✗
  key invalid`) and drops an inline "Update key" affordance (reuses the same panel) instead of a dead
  spinner.
- **Mid-stream error recovery:** if the SSE stream drops (network/500/rate-limit), streaming stops,
  the partial turn is preserved, and an inline "Reconnect / retry" banner appears with retry-after
  guidance; the durable session means the user can also just reload and resume (no lost work). Past
  turns are not editable — "Skip" or answering again in a later turn is the correction path (called
  out so the boundary is explicit).
- **Completion:** success state with "Generate résumé PDF".

### 4.4 Jobs — "live discovery, ranked against my rubric"

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Jobs                                                     [ ⚙ Preferences ▾ ]  │
│  ▾ Preferences (rubric)                                                        │
│     Target roles ⃓ Nice to have ⃓ Dealbreakers   (three columns of chips+add)   │
│                                                    [ ▸ Find jobs ] (primary)   │
│                                                                                │
│  Ran 2 iterations · 3 strong · 5 for review · 11 filtered out                  │
│                                                                                │
│  ● Strong matches (3)                        ◑ For review (5)                   │
│  ┌────────────────────────────┐             ┌────────────────────────────┐    │
│  │ Staff Eng — Globex         │             │ Backend Eng — Initech      │    │
│  │ full-time · remote · EU    │             │ full-time · hybrid · Berlin│    │
│  │ Why it fits: strong match  │             │ Why it fits: partial …     │    │
│  │ on distributed systems…    │             │                            │    │
│  │ [ Tailor to this → ]       │             │ [ Tailor → ] [ 👍 Keep ]   │    │
│  │ [ 🚫 Not interested: Globex]│             │ [ 🚫 Not interested ]      │    │
│  └────────────────────────────┘             └────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Two-tier results** in side-by-side scrollable columns (stack on narrow screens): **Strong** vs
  **For review**, each card showing title — company, employment/work-model/location meta, and the
  **"why it fits" rationale** (the honest-signal requirement; sorted by rationale strength).
- **Card actions:** "Tailor to this →" (hands the JD to Tailor), "Not interested: {company}"
  (persisted hard-reject), and on for-review cards a "👍 Keep" promote.
- **Preferences** is a rubric editor (chip inputs for roles / nice-to-haves / dealbreakers), seeded
  from saved prefs or the user's 3 most recent job titles; persisted on run.
- **Location (inherited from Profile, planned).** When the Profile location/work-model setting ships
  (§4.2), Jobs shows it read-only at the top of Preferences — "Searching: Remote within Canada · GTA"
  — with an "Edit in Profile" link, rather than duplicating the control. Until then the meta line's
  location is display-only from each posting. No location control is duplicated in the rubric.
- **BYOK gate:** if no key, a calm inline banner "Add your key in Grill, then come back" — informs,
  doesn't block navigation.

### 4.5 Tailor — "JD in → ATS-safe résumé out"

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Tailor                                                                        │
│  ⓘ Tailoring to Staff Eng — Globex (from your Jobs matches). Edit JD if needed.│
│                                                                                │
│  ▾ Contact header   Jane Doe · jane@… · +1 … · Berlin · linkedin/github        │
│                                                                                │
│  Job posting URL (optional)  [ https://…/careers/123        ]                  │
│  …or paste the job description                                                 │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  We're hiring a Staff Engineer to …                                      │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│  Specific instructions (optional)  [ Emphasise cloud. Omit side projects. ]    │
│                                                    [ ✦ Tailor my résumé ] (1°) │
│                                                                                │
│  ┌── Preview ────────────────────────────┐   Export:  [PDF] [Word] [Markdown] │
│  │  JANE DOE                              │                                    │
│  │  Summary · Skills (JD-aligned) ·       │   Track as application             │
│  │  Experience grouped by role · Edu      │   [ ✦ Extract from JD ]            │
│  │                                        │   Company [ Globex ]  Role [Staff] │
│  └────────────────────────────────────────┘   [ Save as tracked application ] │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Two-pane on desktop:** inputs left, **live résumé preview** right; single-column on mobile.
- **One model call** ("Tailor my résumé", primary) does JD-aware selection + summary + skills; a
  URL is scraped best-effort (SSRF-guarded, per current behaviour) with a fallback-to-paste warning.
- **Export** row (PDF / Word / Markdown) uses the existing renderers behind the API; bytes cached so
  re-download is instant.
- **Specific instructions** textarea (≤500 chars) — placed in the *user* prompt (prompt-injection
  safety) with the "not persisted to your profile" note.
- **Track as application:** optional "Extract from JD" (model fills company + role) → Save → the app
  appears on Dashboard and enters the 14-day follow-up sweep.
- **Pinned portfolio entries** are always included even if the model doesn't pick them.

### 4.6 Settings — "keys, theme, connections, data"

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Settings                                                                      │
│                                                                                │
│  ▾ API key (BYOK)                                                              │
│     🔑 Using your saved Gemini key   [ Change key ]  [ Remove key ]            │
│     Stored encrypted in Secret Manager · never in our database or logs.        │
│                                                                                │
│  ▾ Appearance                                                                  │
│     Theme:  ( ) Light   ( ) Dark   (•) System                                  │
│                                                                                │
│  ▾ Connected accounts & consents                                              │
│     No accounts connected yet.                                                 │
│     (When Outreach launches, email-send consents + a send log appear here.)    │
│                                                                                │
│  ▾ Data & privacy                                                             │
│     • Grill transcripts + portfolio — kept until you delete them.              │
│     • Tailored résumé previews — cached transiently.                           │
│     • Your Gemini key — Secret Manager only, revocable above.                  │
│     [ Export my data ]   [ Delete my account & data ]                          │
│                                                                                │
│  [ Sign out ]                                                                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Introduced in Phase 10 even though its live contents are just the BYOK key + theme** — so the
  future consent-gated features (§9) have an obvious, consistent home rather than bolting on a
  Settings area later.
- **API key** mirrors today's Grill key management (change / remove; Secret-Manager-only messaging).
- **Appearance** hosts the Light · Dark · System theme control (also reachable from the identity
  menu, §3).
- **Connected accounts & consents** is a Phase-10 placeholder that becomes the emailer's consent +
  send-log home (§9); shown empty now so the pattern is visible.
- **Data & privacy** makes retention legible (the privacy-first promise) with export + delete
  affordances; delete is a destructive action behind an explicit confirm.

---

## 5. Cross-cutting states

| State | Treatment |
|-------|-----------|
| **Loading (reads)** | Skeleton cards, not spinners; screen frame stays stable. |
| **Streaming (grill)** | Appended tokens + typing caret; composer disabled until turn ends. |
| **Empty** | Friendly one-liner + the relevant primary CTA (e.g. Portfolio empty → "Start a Grill"). |
| **Load failure** | Typed empty payload + **Save disabled** (never overwrite unknown state); a toast "Couldn't reach your workspace — try again". |
| **Model / rate-limit error** | Non-blocking inline banner with retry-after guidance; form stays filled. |
| **Pro / BYOK gate** | Calm inline banner that informs and links to the key panel; never a hard modal. |
| **Auth expiry** | Silent token refresh; on hard failure, route to login preserving the intended deep link. |

**Empty-state copy (locked so tone is consistent):**

| Screen | First-run / empty copy | Primary CTA |
|--------|------------------------|-------------|
| Dashboard (no key) | "Set up your Gemini key (≈30s) to start." | Save & use this key |
| Dashboard (day 1) | "Portfolio progress — not started · grill your first experience to begin." | Start grilling |
| Portfolio | "Nothing recorded yet — start a Grill to capture your achievements." | Start a Grill |
| Grill (no history) | "Drop your résumé or paste your career history, then start." | Start grilling |
| Jobs (no key) | "Add your Gemini key first, then search live postings." | Add key |
| Jobs (no run yet) | "Set your target roles and hit Find jobs." | Find jobs |
| Tailor (no portfolio) | "Nothing to tailor yet — grill a few experiences first." (never blocks) | Start a Grill |
| Tailor (ready) | "Paste a job description or URL to tailor your résumé." | Tailor my résumé |

---

## 6. Accessibility & responsive

- **WCAG AA contrast** on text + status colors; status is never encoded by color alone (dot **plus**
  label: "● DOCUMENTED").
- **Keyboard-first:** Radix/shadcn primitives ship focus management; the grill composer, checkpoint
  confirm, and all dialogs are fully keyboard-operable; visible focus rings.
- **Screen-reader:** streamed grill turns use an `aria-live="polite"` region that announces the
  settled turn (batched, not per-token, to avoid chatter); a "CareerEngine is typing…" status is
  announced once when a turn starts; status chips have `aria-label`s; icon-only buttons have text
  labels.
- **Reduced motion:** honor `prefers-reduced-motion` (drop fades + the animated caret, keep instant
  text append).

### 6.1 Mobile spec (from design review — was missing)

```
  Mobile shell (≤ md)                 Grill on mobile                Tailor on mobile
 ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
 │  CareerEngine  🔑 ● │   │ 📌 Acme — Sr Eng   │   │ [ Inputs | Preview ]│ ← segmented toggle
 │                   │   │ ┌───transcript───┐ │   │  Job URL / paste JD │
 │  « screen »       │   │ │ 🤖 …            │ │   │  …                  │
 │                   │   │ │ 🙂 …            │ │   │  [ ✦ Tailor ] (1°)  │
 │                   │   │ └────────────────┘ │   │  ── Preview tab ──  │
 │                   │   │ [Skip →]            │   │  rendered résumé +  │
 │ ┌───────────────┐ │   │ ┌──sticky composer┐│   │  [PDF][Word][MD]    │
 │ │⌂  ▤  ◎  ⚑  ✦  ⚙│ │   │ │ Your answer…  ▸ ││   │                     │
 │ └───────────────┘ │   │ └────────────────┘ │   │                     │
 └───────────────────┘   └───────────────────┘   └───────────────────┘
   bottom tab bar          keyboard-aware,          one pane at a time,
   (icons only)            sticky, auto-scroll      no side-by-side
```

- **Bottom tab bar** replaces the sidebar under `md`: 5 icon tabs — **Dashboard ⌂ · Portfolio ▤ ·
  Grill ◎ · Jobs ⚑ · Tailor ✦** — with **Settings ⚙** reached from the top-bar identity menu (not a
  6th tab, to keep targets ≥44px). Journey-group labels (BUILD/APPLY/PREPARE) are desktop-only; on
  mobile the flat 5-icon bar is clearer. Future features appear as a "More" overflow, not new tabs.
- **Grill composer** is a **sticky bottom bar** that sits above the tab bar; it grows to multi-line
  (max ~4 lines, then scrolls) as the answer lengthens; the transcript **auto-scrolls to the latest
  turn** when the keyboard opens; Enter inserts a newline, an explicit **▸ Send** submits (avoids
  accidental sends on mobile keyboards). The tab bar hides while the keyboard is up.
- **Dashboard** stacks: progress → primary CTA (or the pre-flight key card) → Pending actions →
  Tracked applications (single column, no side-by-side).
- **Tailor** uses a **segmented Inputs | Preview toggle** (one pane at a time) rather than a cramped
  two-pane; export buttons live under the Preview pane.
- **Jobs** stacks the two tiers vertically with a sticky "Strong / For review" segmented control to
  jump between them.
- **Touch targets ≥44px** on all tabs, cards, chips, and composer controls; validated on a 375px
  frame in the 10.5 build.

---

## 7. Traceability — every element maps to a shipped feature

| Screen | Backed by (existing `web/`) | API slice |
|--------|-----------------------------|-----------|
| Login / landing | `auth/firebase_auth.py` (verified token → `user_id`) | `GET /api/me` (10.1) |
| Dashboard | `web/dashboard.py`, workspace pending-actions + applications | `GET /api/dashboard` (10.2) |
| Portfolio | `web/portfolio.py`, `portfolio_store.py`, `profile_store.py`, `resume_builder/render` | `GET /api/portfolio` (10.2); `POST /api/profile` / `experience` (10.3) |
| Grill | `web/grill_ui.py`, `workflows.nodes`, `DiscoverySession`, `_effective_frontier_label` | `POST /api/grill` + `GET /api/grill/stream` (10.4) |
| Jobs | `web/jobs.py`, `jobs_runner.py`, `preferences_store.py`, discovery ledger | `GET /api/jobs` (10.2); `PUT /api/preferences` (10.3) |
| Tailor | `web/resume_builder.py`, `resume_render.py`, `jd_utils.py`, `application_store.py` | `POST /api/tailor`, `GET /api/resume/{fmt}`, `POST /api/applications` (10.3/10.6) |
| Settings | `auth/key_vault.py` (BYOK); theme is a client-only preference (localStorage, no store) | key management endpoints (10.3) |

No screen introduces a new domain concept or a `CONTRACT_VERSION` change — this is presentation +
transport only (AD-16.2 / AD-16.7).

---

## 8. Open design questions (decide during 10.5/10.6 build)

**Resolved by the independent design review (now folded into this doc):** first-run key setup on
Dashboard (§4.1) · explicit mobile spec (§6.1) · light/dark theme + toggle (§2/§3) · grill-component
reuse boundary as `StreamingTranscript` (§9) · concrete color/type/focus tokens (§2) · locked
empty-state copy (§5) · **foundational component inventory** (§2) · **client data layer** = TanStack
Query with optimistic writes ([ARCHITECTURE.md §16 AD-16.8](ARCHITECTURE.md)) · **frontend test stack** =
Vitest + React Testing Library + MSW + Playwright ([ARCHITECTURE.md §16 AD-16.9](ARCHITECTURE.md)).

**Still open (decide during build):**
1. **Jobs layout** — side-by-side tiers vs a single ranked list with a "for review" filter toggle.
2. **Résumé preview fidelity** — render the real WeasyPrint HTML in an iframe vs a lighter React
   approximation (exact bytes still come from the server renderer).
3. **Component lib** — shadcn/ui is the proposal; confirm via a 10.5 spike against bundle-size / SSR
   constraints (the same spike checks the AD-16.8 data-layer bundle budget), and validate the palette
   (dark-mode contrast + colorblind) before freezing tokens.
4. **Sidebar grouping labels** — `BUILD / APPLY / PREPARE` wording; confirm `Dashboard`/`Settings`
   sit outside the groups.

*(These are UI-only and do not affect the API slices 10.1–10.4.)*

---

## 9. Forward compatibility — designing for known future features

Phase 10 ships the 5 current screens, but the roadmap already names more: an **emailer / outreach**
suite (recruiter follow-ups, thank-you notes) that **requires consent pages**, plus **interview prep**
and a **salary negotiator**. The shell above is deliberately built to absorb these *without a
redesign* — a good design is judged partly on how gracefully it grows.

**How each future feature slots in (no new IA needed):**

| Future feature | Nav home | Journey group | New UI patterns it introduces |
|----------------|----------|---------------|-------------------------------|
| **Outreach / Emailers** | `/outreach` | APPLY | **Consent flow** (below) · connected email account · templated draft → review-before-send · send log |
| **Interview prep** | `/interview` | PREPARE | Practice Q&A (reuses the **grill streaming pattern** from 10.4/§4.3) · per-application prep notes |
| **Salary negotiator** | `/salary` | PREPARE | Offer/comp inputs · scripted guidance (streamed) · scenario compare cards |

**The consent-page pattern (first-class, because emailers need it):**

Any feature that acts *on the user's behalf toward third parties* (sending email, connecting an
account) is **gated behind an explicit, revocable consent screen** — never a buried checkbox. This is
introduced now, at the shell level, so it is consistent when the emailer lands.

```
┌── Before CareerEngine can send email on your behalf ───────────────────────┐
│  We will:                                                                   │
│   • Send messages only when you click Send (never automatically)            │
│   • Connect: your Gmail account  ·  scope: send-only                        │
│   • Show you every draft to review + edit before anything goes out          │
│  We will NOT:                                                               │
│   • Read your inbox  ·  Store message bodies beyond your send log           │
│                                                                             │
│  [ Connect account & agree ] (primary)     [ Not now ]                      │
│  You can revoke this any time in Settings → Connected accounts & consents.  │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Explicit scope + plain-language do/don't**, an affirmative primary action, and an easy decline.
- **Revocable** from **Settings → Connected accounts & consents** (the reason Settings is introduced
  in Phase 10 even though its current contents are just the BYOK key).
- **Consent is recorded** (who/what/when/scope) as a durable, `user_id`-scoped record surfaced under
  **Settings → Connected accounts & consents** as a viewable list (grant + revoke history), with each
  send appended to a **send log** (recipient, subject, timestamp — not full body). This is the
  concrete home for the "auditable" promise; a placeholder "Consents & activity" panel exists in
  Phase 10 Settings so the emailer has somewhere to write to.
- **Two-tier consent:** a **one-time account/scope grant** (the screen above) *plus* a mandatory
  **per-message "Send this?" confirmation** on every draft — consent to connect is never consent to
  auto-send. Revoking the grant mid-flow immediately disables Send.
- **Draft-review-before-send** is mandatory for the emailer: the agent drafts, the human edits and
  presses Send. No silent sending — the same "explicit human confirmation" ethos as grill checkpoints.
- **Data-retention transparency:** Settings surfaces, in plain language, what is kept and for how long
  (grill transcripts + portfolio = retained until you delete; tailor previews = cached transiently;
  email bodies = not stored beyond the send-log metadata). A privacy-first BYOK app should show where
  data lives — this is the UI home for it.

**Design implications acted on now (so nothing needs re-architecting later):**
- Sidebar is **grouped** (`BUILD / APPLY / PREPARE`), not a flat list (§3).
- A **Settings** destination + a reusable **ConsentDialog** pattern (one-time grant) and a
  **per-send confirm** pattern exist from Phase 10.
- The grill's streaming turn UI is factored as a reusable **`StreamingTranscript`** component
  (transcript render + SSE token streaming + composer), **not** a claim that the whole grill flow is
  reused. Interview prep and the negotiator reuse `StreamingTranscript`; their *turn logic differs*
  (interview prep is closer to one-way prompt → recorded answer; the negotiator is scripted guidance),
  so each supplies its own turn controller over the shared streaming surface. This boundary is
  validated with a design spike before those features build (§8).
- Route namespace reserves `/outreach`, `/interview`, `/salary`; their nav rows stay **hidden until
  live** (feature-flagged), not shown as dead "coming soon" clicks (§3).
- **Light + dark themes** and a persisted theme toggle ship in the shell (§2/§3), so every future
  screen inherits theming for free.

*None of these future features are in Phase 10 scope or affect API slices 10.1–10.4; they are captured
here only so the Phase 10 shell is built forward-compatibly.*
