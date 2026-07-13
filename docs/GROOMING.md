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

## Phase 10 — Replace Streamlit with Next.js + FastAPI  *(✅ COMPLETE — retired to archive)*

**All slices shipped: 10.0–10.7b (PR #63–#72 + Streamlit-removal PR).** The Streamlit surface is gone; the
product runs on a **Next.js (App Router) frontend over a FastAPI JSON API**, deployed as **one container**
(Next.js static export served by FastAPI, AD-16.10). Design is canonical in
[ARCHITECTURE.md §16](ARCHITECTURE.md); status in [PROGRESS.md](PROGRESS.md); full build specs + the
standing 10.x build rules are retired to
[history/GROOMING_ARCHIVE.md §Phase 10](history/GROOMING_ARCHIVE.md).

**Next phase (11 — stabilization) is NOT yet groomed into build tickets.** Groom it (WARM docs → tickets)
before building; scope is in [REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md) Phase 11. The immediate
first slice is **11.A — stand up a new-GCP-project `qa` env** and deploy the 10.7 image to it.

---


## Copy quality — bullet identity, résumé merge, delete, copywriter-in-the-grill

> Design + rationale: [ARCHITECTURE.md §18](ARCHITECTURE.md) (AD-18.1/18.2/18.3). Status:
> [PROGRESS.md](PROGRESS.md). These are **ordered** — CQ-1 unblocks CQ-2/3/4.
>
> Why this exists: a résumé bullet is `story.result` verbatim. There is **no copywriting stage**, and we
> throw away S/T/A at render time keeping only R. Separately, a second résumé upload **destroys** the
> first (`create_session` is last-write-wins) — CQ-2 is a live data-loss bug.

### ✅ CQ-1 — Bullet identity (`list[str]` → `list[Bullet]`), contract **v2.9.0**  *(SHIPPED — PR #87)*
**Scope:** `schema.py` (new `Bullet` model + `Entry.bullets` shape + `CONTRACT_VERSION` → 2.9.0),
a migration for persisted sessions, `web/portfolio_store.py` (address bullets by `bullet_id`, not index),
`api/routes_portfolio.py` + `api/schemas.py` (PATCH takes `bullet_id`), `web/resume_builder.py`
(`_merge_entry_bullets` dedups on `supersedes`, not text containment), `web/portfolio.py` (view carries ids).

`Bullet`: `bullet_id: UUID`, `text: str`, `source: Literal["parsed","user","grilled"]`,
`supersedes: UUID | None`.

**Acceptance:**
- A v2.8.0 session with `bullets: list[str]` loads and migrates to `list[Bullet]` (`source="parsed"`,
  fresh ids) — a round-trip test over a real persisted document, not a synthetic one.
- Editing/deleting a bullet by id is stable under a concurrent insert (the index-based API was not).
- An unknown MAJOR contract version is still refused (existing guard must not regress).
- `_merge_entry_bullets` drops a bullet whose id is `supersedes`-linked, instead of guessing by text.

### ✅ CQ-2 — Résumé upload MERGES instead of clobbering  *(SHIPPED — PR #90)*
**Today:** `POST /api/grill/resume` → `session.create` → `cli.session.create_session`, which is
**last-write-wins** (its own docstring says so). A second upload destroys every entry, every STAR story,
every hour of grilling. **Decision (Sumanta, 2026-07-12): merge + dedup, never destroy.**

**Scope:** a new `web/portfolio_store.amerge_parsed_entries` (load-then-merge, NOT create), called by
`api/routes_grill.seed_from_resume` when a session already exists.
Match entries on (normalised `title`, `org`, overlapping date range) → **keep the existing entry**
(preserving `entry_id`, its STAR stories and its GRILLED status), union its bullets by `bullet_id`/text;
append genuinely-new entries as ungrilled; move the grill frontier to the new entries.

**Acceptance:** upload #2 containing one matching role + one new role → the matched role keeps its
`entry_id`, stories and status; the new role is appended `UNGRILLED`; **no story is ever lost** (assert
`extracted_star_stories` is a superset of the pre-upload set).

### ✅ CQ-3 — Delete a bullet / delete an entry  *(SHIPPED — PR #91)*
The store can replace (`update_entry_bullet`) and append (`add_entry_bullet`) but not remove. Edit-only is
half a tool, and it matters more once CQ-2 can merge in a role the user doesn't want.
**Scope:** `delete_entry_bullet` (by `bullet_id`) + `delete_entry` seams, `DELETE
/api/experience/{entry_id}/bullet/{bullet_id}` + `DELETE /api/experience/{entry_id}`, Portfolio UI.
**Acceptance:** deleting an entry also drops its orphaned STAR stories (no dangling `entry_id`s).

### ✅ CQ-4 — Copywriter in the grill (AD-18.1/18.2)  *(SHIPPED — PR #93)*
A workflow **node + system prompt** — *not* an agent (no tools, no memory, no loop). Given an entry's full
S/T/A/R stories **and** its original bullets, propose polished replacements; the user accepts / edits /
rejects each; the accepted text persists as a `Bullet` with `source="grilled"` and `supersedes` set when it
replaces a line. Export then needs **no model call** (AD-18.2).

**Hard constraints:**
- **Batch per entry, one turn.** One turn per bullet makes the grill interminable — the obvious failure
  mode of this design.
- **Never invent.** May re-word, re-order, promote, trim. May NOT add a number, tool, employer or claim
  absent from the source. (Content rules worth lifting from `demo_output/joy-resumeskill.md`; do NOT adopt
  its one-shot chat shape.)
- **Coverage:** if a résumé supplied a dozen bullets, every one is walked — strengthened, quantified, or
  explicitly skipped. Today the grill drills a "favourite project" and never covers the rest.
- Master-résumé `skills` (currently always `[]`) and `summary` can come from the same pass — no JD needed.

**Acceptance:** a reworded bullet the user ACCEPTS appears on the master résumé and its superseded original
does NOT; a bullet the user REJECTS leaves the original untouched; a model failure or a missing BYOK key
degrades to today's raw bullets (never a crash, never an empty résumé).

### 🟡 CQ-5 — Grill BETTER: cover what the user actually gave us  *(HALF SHIPPED — PR #94)*
> **Shipped:** coverage is now VISIBLE (the model, the "7 of 12 covered" label, per-bullet state,
> Skip/Unskip, `Bullet.skipped` — contract v2.10.0). **NOT shipped:** the `QUANTIFIED` state (built,
> then DELETED — text matching cannot decide it and a false positive silently buries the user's
> outstanding work) and coverage STEERING the grill. Both land in **CQ-5b** below. Original spec:
A first-class concern, not a side effect of CQ-4. Today the grill picks a frontier entry and drills for a
metric — it will happily interrogate a "favourite project" while a dozen strong bullets from the uploaded
résumé are never touched. If a user hands us rich source material, **coverage is the product**: every
supplied bullet should end in one of three terminal states — *quantified* (a metric was extracted),
*strengthened* (reworded and accepted), or *explicitly skipped* (the user said it doesn't matter).

**Scope:** the grill router / frontier selection (`workflows/`) + a coverage view the user can see.
**Acceptance:** given an entry with N parsed bullets, the grill does not declare the entry done while any
bullet is in none of the three terminal states; the Portfolio shows per-entry coverage (e.g. "7 of 12
covered"), so the user knows what is left rather than guessing.

### ✅ CQ-5b — Make coverage STEER the grill  *(SHIPPED — PR #97/#98, contract v2.11.0)*
> **Shipped:** the grill AIMS at a specific uncovered bullet (the vague "describe a project"
> opener was the origin of the bug), `grill_bullet_frontier` records which bullet is being asked
> about, and `StarStory.answers_bullet_id` records which bullet the answer ANSWERS. Coverage's
> QUANTIFIED is decided by that LINK — no text matching anywhere. Every gate (the router,
> `_get_frontier_entry`, `_next_frontier`) now shares ONE predicate, `entry_still_needs_grilling`.
> **Legacy grandfather:** an entry with no linked story predates v2.11.0 and is left alone by the
> automatic gates (an explicit "Grill me about this" still overrides) — without it, coverage
> steering would have re-opened every returning user's finished portfolio. Original spec:
CQ-5 made coverage **visible** (the model, the "7 of 12 covered" label, per-bullet state, and
the Skip escape hatch) but did **not** wire it into frontier selection. That was not an
oversight — the obvious wiring is unsafe:

> `_next_frontier` re-selecting an entry while it has uncovered bullets can trap the grill in
> an **INFINITE LOOP**. Coverage is detected by TEXT CONTAINMENT (`web.coverage._covers`). A
> grilled story worded differently enough to match no bullet leaves coverage unchanged, so the
> frontier stays put, the grill asks again, produces another non-matching story, and repeats.
> The user's only exit would be skipping every line by hand.

**The fix must make progress monotonic BY CONSTRUCTION, not by string matching.** The grill has
to record WHICH bullet a story answers.

**Scope:** the grill targets a specific uncovered bullet (put its `bullet_id` in the question
context), and on a validated answer the resulting `StarStory` records the `bullet_id` it
answered (additive contract field, e.g. `StarStory.answers_bullet_id: UUID | None`). Coverage
then reads that link instead of guessing at text. Only then can `_next_frontier` keep an entry
while `entry_needs_work(...)` — because every successful turn is guaranteed to retire exactly
one bullet.

**Acceptance:** a grilled story whose wording matches NO bullet still advances coverage (the
link, not the text, decides); an entry with N uncovered bullets is retired after at most N
successful turns; the existing `test_a_grilled_entry_is_still_left_behind_today` in
`tests/test_coverage.py` is inverted to assert the entry is KEPT.

### ✅ CQ-6a — Every résumé line carries its identity (contract v2.12.0) — SHIPPED (PR #100)
The prerequisite CQ-6 turned out to need, and it fixed **three bugs that were already live**. A résumé line
was a bare `str` (`RoleBlock.bullets: list[str]`), so the preview could not say which portfolio object a
line came from — which is precisely why "overwrite the original" was not expressible. All three reproduced
by running the real code *before* planning:

- The **master résumé listed one achievement three times** (raw grill text + the original parsed line + the
  copywriter rewrite the user approved). A story-derived accepted proposal recorded nothing about its story,
  and text dedup can never catch this: *the better the copywriter does its job, the less the rewrite
  resembles the line it replaced.*
- **Tailor ignored the uploaded résumé** — catalog was validated STAR stories only, so upload-then-tailor
  returned an EMPTY document. Same bug as "master resume ignores all original resume"; fixed there, still
  live here.
- **Tailor shipped raw grill text** even when the user had approved better prose — making CQ-4's "no
  unreviewed prose reaches a PDF" false for the actual product.

`ResumeLine(text, bullet_id, story_id)` + `Bullet.derived_from_story_id` (*this bullet IS that story's
résumé line*). The tailor's catalog is now **defined as "the lines the master would render"**, so it cannot
drift from the document. See ARCHITECTURE §18 (AD-18.6).

### ✅ CQ-6b — Post-tailor, pre-render editing + the persist choice — SHIPPED (PR #101)
The Tailor preview is editable; each edit carries a destination (below). Two adversarial reviews
independently found the same showstopper: **the undo didn't restore, it FABRICATED.** `previous` was
read off the *preview* line, which a "this résumé only" edit has already changed — so rewording for a
JD, then later overwriting, then undoing, would **write the JD-specific wording into the master
résumé** while the true original was lost. Undo left the user worse off than not undoing. Fixed by
snapshotting the server's text at tailor time, keying lines **positionally** (an identity-derived key
changes the moment a line adopts a new bullet id, which silently broke the rollback *and* left the line
pointing at a deleted bullet, making every later overwrite a no-op that reported success), and keeping
an undo **per line** rather than one page-level slot.

### (spec, as built) — CQ-6b
Let the user edit bullets after tailoring but before export, and decide what that edit *means*. This is the
step where people actually notice the wording is wrong — the JD is in front of them.

A tailored résumé is a **rendering** of the portfolio, not a copy of it, so an edit here needs a destination:
1. **This résumé only** — a JD-specific rewording that must NOT pollute the master. Client-side: export
   already POSTs the résumé body, so nothing touches `work_timeline`. Also the only meaningful destination
   for the model-written **summary** and **skills**, which have no portfolio object behind them.
2. **Overwrite the original** —
   - line has a `bullet_id` → **in-place** `PATCH /api/experience/{id}/bullet`.
   - line has only a `story_id` → POST a `Bullet(source=user, derived_from_story_id=story_id)`, which the
     CQ-6a assembler renders *in place of* `story.result`.

**Use in-place update, NOT `supersedes`** (this ticket originally said `supersedes` — that was wrong).
A `supersedes` overwrite mints a new `source=USER` bullet, which coverage reads as UNCOVERED → the entry
**re-opens and the grill marches the user back to put a number on the line they just polished**. That is the
CQ-5b failure. In-place keeps `bullet_id` stable, so `answers_bullet_id`, coverage and the ID-dedup all keep
pointing at the right thing. (Worse: the `accept_bullets` seam *permanently deletes* the superseded original.)

**Acceptance:** "this résumé only" makes **zero** store writes; after "overwrite" the master renders the new
text and nothing renders the old, `bullet_id` is unchanged, and the coverage label is unchanged; **each
destination, applied to a fully-covered entry, leaves `entry_still_needs_grilling` AND `_has_pending_work`
False** (drive the ROUTER, not just the pure helper — the CQ-5b lesson); `Track as application` serializes
the EDITED résumé, not the pre-edit one.

### ⬜ CQ-7 — Bullet VARIANTS (alternate phrasings) — needs a product decision first
CQ-6 originally had a third destination: *"persist as a new variant — original kept, both available to the
tailor."* **Deliberately not built**, because as written it is a button that makes the master résumé list the
same achievement twice — i.e. the exact bug CQ-6a just fixed — and re-opens the entry in the grill.

A variant is an **alternate phrasing of a line that already exists**, and there is no model for alternates.
Making it coherent needs answers the code cannot invent:
- **Which phrasing does the MASTER show?** (Both = redundant. One = which, and how does the user change it?)
- How does the tailor **choose among alternates** for a given JD? (This is the actual value: let the
  JD-aware model pick the phrasing that fits *this* posting.)
- How does **coverage inherit** through the variant link, so adding a variant of a covered line doesn't
  re-open the entry?

Needs `Bullet.variant_of` (or a variant-group id), a render rule, a tailor-selection rule, and a coverage
rule. **Ask the operator before building** — the master-résumé question is a product call.

### ⬜ UX-2 — CI cannot verify ANY breakpoint behaviour (needs an authenticated mobile e2e lane)
**Operator decision required — this asks for an auth bypass in the e2e build.**

UX-1 shipped a mobile nav, but **nothing in CI proves it works on a phone**, and it is important to
say so rather than let a green suite imply otherwise:
- **jsdom has no viewport and does not evaluate CSS.** `md:hidden` / `hidden md:flex` are inert class
  strings there, so *both* navs are in the test DOM at once. The Vitest suite proves the drawer is
  WIRED (opens, holds the links, Escape closes, focus returns) and that the breakpoint classes are
  still present — a token check. It cannot prove what a 360px screen actually renders.
- **The Playwright lane cannot reach any page that has a nav.** Its fake Firebase config resolves to a
  signed-out session (by design), so every authed route redirects to `/login`, which has no nav. And
  its only project is `Desktop Chrome` — there is no mobile viewport anywhere in the repo.

**Change:** add a mobile Playwright project (`devices["Pixel 5"]`) and an **e2e-only auth bypass** so a
test can actually render `AppShell` at 390×844: assert the sidebar is not visible, the hamburger is,
tapping it reveals the links, and `document.documentElement.scrollWidth <= clientWidth` on every route.

**Why it needs a decision, not just a build:** an auth bypass flag is a security-relevant seam. It must
be impossible to enable in a production build (the e2e build already uses its own fake Firebase config,
so the precedent exists), and the deploy workflow must pin it off. **Ask before building.** The
alternative is to accept that breakpoints are verified by hand, and record that honestly.

### ✅ UX-1 — The app had NO navigation on mobile — SHIPPED (PR #102)
Hamburger → slide-over drawer rendering the **same** `SidebarNav` (one component, so the desktop nav and
the mobile nav — including the flagged PREPARE group, §17 — cannot drift). Radix Dialog rather than a
hand-rolled trap: focus trapping, focus restore, Escape and body-scroll lock are each easy to get subtly
wrong, and this component stands between a phone user and the entire product.

Review found three more things that broke at 360px **independently of the nav**, all fixed:
- **The Toast overflowed the viewport.** `w-full` on a `fixed` element is 100vw; with `right-4` its left
  edge landed at −16px → a horizontal scrollbar on every route that toasts.
- **The header row could not fit** — title + key chip + identity menu, no wrapping, no `min-w-0` (flex
  will not shrink a text node below its min-content without it), and now a hamburger too.
- **There was no `not-found.tsx`**, so a mistyped URL rendered outside the app chrome with no navigation
  at all — the same "no way back" bug in a different place.

### (superseded spec) — UX-1 — The app has NO navigation on mobile (+ a responsive audit)
**Not polish — the app is unusable on a phone.** `AppShell` renders the nav in an
`<aside className="hidden … md:flex">` (`frontend/src/components/AppShell.tsx`), so below 768px the sidebar
is removed **and nothing replaces it**: no hamburger, no drawer, no bottom bar. The "CareerEngine" home link
lives *inside* that same hidden `<aside>`. A phone user cannot reach Dashboard, Portfolio, Grill, Jobs,
Tailor or Settings **at all** — only by typing a URL. Reported from the field: *"in mobile the left menu
never shows up."*

**Scope**
- A mobile nav that exists: hamburger in the header → slide-over drawer rendering the **same** `SidebarNav`
  (ONE nav component — a second copy will drift), or a bottom tab bar. Closes on route change and Escape;
  focus trapped while open; trigger has an accessible name + `aria-expanded`.
- The header must survive 360px — today the page title, `KeyChip` and `IdentityMenu` share one flex row with
  no wrapping.
- **Then audit every route at 360 / 768 / 1280.** Known-suspect surfaces, being the ones built widest: the
  Tailor two-pane (JD textarea beside the preview), the résumé preview, the Portfolio entry cards with their
  inline edit/grill/pin/delete action rows, and the Jobs list.
- Tap targets: the `min-h-tap` utility already exists — apply it to the action rows that don't use it.

**Acceptance:** at 360px every route is reachable from the UI alone; no horizontal page scroll on any route;
the drawer traps focus and closes on Escape/navigation; a Vitest/RTL test asserts the mobile nav trigger
renders and opens the drawer — **a test that would FAIL today**, which is exactly how an app with no mobile
nav shipped past a green suite.

## Cleanups (non-blocking, do when convenient)

### ⬜ CLEAN-2 — `make check` does not lint `api/` AT ALL
`SRC_DIRS` in the Makefile omits `api/`, so **ruff never runs on the FastAPI layer** — every route
and every wire DTO, i.e. the files where the contract actually lives. (`mypy --strict` *does* cover
them and is clean; it is only the lint lane that is blind.)

**Why it happened:** 39 of the 44 findings in `api/` are `B008` *function-call-in-default-argument* —
which is FastAPI's `Depends()` idiom, a false positive. The whole directory was excluded to silence one
noisy rule, and lost lint coverage as collateral.

**Why it matters:** this is the layer where a stale generated contract shipped in #87 — `openapi.json`
and `types.gen.ts` disagreed with the deployed server, and `tsc` couldn't see it because `apiFetch`'s
body is typed `unknown`. A gate that skips the contract layer is a gate with a hole exactly where the
contract lives.

**Change:** add `api/` to `SRC_DIRS`, add a `per-file-ignores` entry for `B008` in `api/` (the idiom is
correct there), then fix the 5 genuine findings (2 × unused-noqa, 1 × unsorted-imports, 1 ×
ambiguous-unicode, 1 × unsorted-dunder-slots). Small, and it closes a real hole.

### ⬜ CLEAN-1 — Rename the async store functions: `a<name>` → `<name>_async`
The store's async functions are named by **prepending `a`**: `aadd_manual_entry`,
`aset_grill_frontier`, `aset_entry_highlight`, `adelete_star_story`, `aupdate_entry_bullet`,
`aadd_entry_bullet`, `amerge_parsed_entries`, `adelete_entry`, `adelete_entry_bullet`, plus
`atry_load_latest_discovery_state` in `web/session_loader.py` and the private `_a…` cores.

**Why it's a problem:** the prefix reads as part of the word. `amerge` looks like a verb in its
own right, and Sumanta had to ask what it meant — which is the tell. `aset`, `adelete` and
`aupdate` are equally opaque to anyone who hasn't been told the convention.

**Change:** rename to a **`_async` suffix** — `merge_parsed_entries_async`, `set_grill_frontier_async`,
`delete_star_story_async`, etc. Rename the private cores to match (`_merge_parsed_entries_async`).
Mechanical, no behaviour change, no contract change.

**Care required:**
- The sync bridges share the base name (`set_grill_frontier` sync vs `aset_grill_frontier` async).
  After the rename the pair becomes `set_grill_frontier` / `set_grill_frontier_async` — check no
  collision is introduced.
- `api/routes_portfolio.py` monkeypatches these by name in tests (`monkeypatch.setattr(routes_portfolio,
  "delete_star_story", ...)`) — the tests patch the SYNC names, so they should be unaffected, but verify.
- Run the full gate: `make check` (ruff + mypy --strict + pytest) **and** `make frontend-check`. Do not
  trust a find-and-replace; ruff's import sorting and unused-import rules will flag stragglers, and
  mypy --strict will catch a missed call site.
