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

### ✅ CQ-1 — Bullet identity (`list[str]` → `list[Bullet]`), contract **v2.9.0**  *(Ready · do FIRST)*
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

### ⬜ CQ-2 — Résumé upload MERGES instead of clobbering  *(DATA LOSS — ship right after CQ-1)*
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

### ⬜ CQ-3 — Delete a bullet / delete an entry
The store can replace (`update_entry_bullet`) and append (`add_entry_bullet`) but not remove. Edit-only is
half a tool, and it matters more once CQ-2 can merge in a role the user doesn't want.
**Scope:** `delete_entry_bullet` (by `bullet_id`) + `delete_entry` seams, `DELETE
/api/experience/{entry_id}/bullet/{bullet_id}` + `DELETE /api/experience/{entry_id}`, Portfolio UI.
**Acceptance:** deleting an entry also drops its orphaned STAR stories (no dangling `entry_id`s).

### ⬜ CQ-4 — Copywriter in the grill (AD-18.1/18.2)
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

### ⬜ CQ-5 — Grill BETTER: cover what the user actually gave us
A first-class concern, not a side effect of CQ-4. Today the grill picks a frontier entry and drills for a
metric — it will happily interrogate a "favourite project" while a dozen strong bullets from the uploaded
résumé are never touched. If a user hands us rich source material, **coverage is the product**: every
supplied bullet should end in one of three terminal states — *quantified* (a metric was extracted),
*strengthened* (reworded and accepted), or *explicitly skipped* (the user said it doesn't matter).

**Scope:** the grill router / frontier selection (`workflows/`) + a coverage view the user can see.
**Acceptance:** given an entry with N parsed bullets, the grill does not declare the entry done while any
bullet is in none of the three terminal states; the Portfolio shows per-entry coverage (e.g. "7 of 12
covered"), so the user knows what is left rather than guessing.

### ⬜ CQ-6 — Post-tailor, pre-render editing — and the choice to PERSIST it
Let the user edit bullets after tailoring but before export, and decide what that edit *means*. This is the
step where people actually notice the wording is wrong — the JD is in front of them.

The subtlety that must not be fudged: a tailored résumé is a **rendering** of the portfolio, not a copy of
it. So an edit made here has three legitimate destinations, and the user picks:
1. **This résumé only** — a JD-specific rewording that should NOT pollute the master (e.g. echoing that
   company's vocabulary). Lives in the exported document, nowhere else.
2. **Persist as a new variant** — a genuinely better phrasing; stored as a `Bullet` with `source="user"`,
   available to every future résumé, original kept.
3. **Overwrite the original** — the old line was simply worse; stored with `supersedes` set (CQ-1), so the
   superseded bullet stops appearing (and the master-résumé dedup handles it by id, not by guessing at text).

Without CQ-1's bullet identity, only option 1 is expressible — which is exactly why the current UI can edit
a bullet but cannot tell you what happened to it.

**Scope:** Tailor preview becomes editable; a per-edit destination control; reuse the CQ-1 store seams.
**Acceptance:** an edit marked "this résumé only" never changes `work_timeline`; an edit marked "overwrite"
sets `supersedes` and the superseded line disappears from the master résumé; an edit marked "new variant"
leaves the original in place and both are available to the tailor.

## Cleanups (non-blocking, do when convenient)

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
