# CareerEngine — Grooming Tracker

> Turns roadmap items ([REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)) into **sonnet-launchable**
> build specs, and tracks how far each is groomed so we can resume mid-stream.
> A workstream is **Ready** when it has: scope (files), acceptance criteria (named tests), and points at
> the **Shared preamble** + **Definition of Done** in [AGENT_EXECUTION_PROMPT.md](AGENT_EXECUTION_PROMPT.md)
> and the spec in [ARCHITECTURE.md](ARCHITECTURE.md). Builders run on **Sonnet**, `isolation: worktree`;
> **Opus** reviews + merges (no self-declared done). master stays green per merge.
>
> Grooming legend: ✅ **Ready** (launchable) · ◐ **Draft** (outline, needs detail) · ⬜ **To groom**.

## Phase 1.5 — grooming status (contract v2.0.0)
| WS | Scope | Depends on | Grooming |
|----|-------|-----------|----------|
| **1.5-CONTRACT** | schema v2.0.0: Entry timeline, replace pillar fields, version bump, golden test | — (blocking) | ✅✅ **BUILT & MERGED** (tag `contract-v2.0.0`) |
| **1.5-GRILL** | entry-based grill loop, discovery turn, `grill_frontier`, skip-quantified | built WITH CONTRACT (1 merge unit) | ✅✅ **BUILT & MERGED** |
| **1.5-METRICS** | extend `_contains_real_metric` for early-career/non-eng metrics | folded into GRILL | ✅✅ **BUILT & MERGED** (in GRILL) |
| **1.5-INGEST** | vision resume parser + multimodal client + `ingest_node` upgrade | after CORE merged (touches `nodes.py`) | ✅✅ **BUILT** (Opus-built, Sonnet-reviewed PASS) |
| **1.5-DISCOVERY** | `discovery_completeness` nudge, progress meter, return loop, never-block tailoring | after CORE (CLI-only) | ✅✅ **BUILT** (Opus-built, Sonnet-reviewed PASS) |

**🎉 Phase 1.5 COMPLETE — all five pieces built (contract v2.0.0, 317 tests).** CORE was Sonnet-built/
Opus-reviewed/merged; INGEST + DISCOVERY were Opus-built + Sonnet-reviewed this session. Deferred
integration items (resume-file CLI wiring, full session-resume, `discovery_turn_node` graph edge) are
tracked in [HANDOFF.md](HANDOFF.md). Next: Phase 2.

**Sequencing:** `[CONTRACT + GRILL + METRICS]` = one worktree / one Opus review / one merge (CORE; master
stays green) → then `INGEST` ∥ `DISCOVERY` (disjoint files: INGEST=`nodes.py`/`tools`, DISCOVERY=`cli/` —
safe to fan out). CONTRACT+GRILL is the only coupled bit; the rest is straightforward.
**To build now:** run the 1.5-CONTRACT prompt then the 1.5-GRILL prompt in ONE Sonnet worktree → Opus-review
the combined diff → merge → fan out INGEST + DISCOVERY (Sonnet worktrees) → Opus-review + merge each.

---

## ✅ 1.5-CONTRACT — schema v2.0.0 (BLOCKING; build solo, freeze before fan-out)
Read first: [ARCHITECTURE.md §12.5](ARCHITECTURE.md) + AGENT_EXECUTION_PROMPT.md Definition of Done.

```
You are amending CareerEngine's FROZEN contract to v2.0.0 (a BREAKING change — user-approved, no
migration burden as there's no production data). Do ONLY the contract; an Opus reviewer freezes it
before any Phase-1.5 fan-out. Stay in schema.py, config.py, tests/.

Changes:
- config.py: CONTRACT_VERSION "1.1.0" -> "2.0.0".
- schema.py: add `class Entry(BaseModel)`: entry_id: UUID (default factory), type: ExperienceType enum
  {full_time, internship, project, research, open_source, leadership, part_time, education, other},
  title: str, org: str = "", start_date: str = "", end_date: str = "" (""=present allowed),
  source: Literal["resume","discovered","manual"] = "manual", bullets: list[str] = [],
  status: EntryStatus enum {documented, needs_quantifying, grilled, summarized, skipped} = needs_quantifying.
- schema.py CareerEngineState: ADD `work_timeline: list[Entry] = []`, `coverage_through: str = ""`,
  `reference_date: str = ""` (ISO date; the injected clock — nodes never call datetime.now()),
  `grill_frontier: str = ""` (entry_id we're grilling / last grilled). REMOVE the pillar fields
  `target_competencies`, `active_gaps`, `current_pillar`. Keep question_count, checkpoint_* , the v1.1.0
  conversational/output fields, contract_version.
- schema.py StarStory: ADD `entry_id: str = ""` (links a story to its Entry); keep `pillar` as a
  competency tag.
- Derived pure helpers in schema.py (NOT stored): `discovery_completeness(state) -> float` (fraction of
  trailing-5-year-window entries that are grilled/summarized, using state.reference_date — NOT now()),
  and `recent_window_complete(state) -> bool` (>=1 validated entry AND no needs_quantifying entries in
  the window). These drive the nudge/meter; they do NOT gate anything.
- tests/test_contract_roundtrip.py: extend the golden round-trip for Entry, the new CareerEngineState
  fields, StarStory.entry_id; assert CONTRACT_VERSION=="2.0.0"; assert the removed pillar fields are
  GONE (model has no such fields). Add tests for discovery_completeness / recent_window_complete with a
  fixed reference_date (deterministic).

DoD: `make check` green; round-trip covers every new/changed model; no datetime.now() in schema/helpers.
Report READY FOR REVIEW (don't commit). NOTE: this BREAKS workflows/nodes.py & discovery_graph.py
(they use the removed pillar fields) — that's expected; 1.5-GRILL fixes them next. If breaking other
modules makes `make test` fail on THOSE files, report which (do not fix them here).
```
> Reviewer note: because this intentionally breaks the grill loop, CONTRACT may merge with WS-A tests
> temporarily red — OR sequence CONTRACT+GRILL as one freeze. Decide at launch (see GRILL draft).

---

## ✅ 1.5-INGEST — vision resume parser (after CONTRACT frozen)
Read first: [ARCHITECTURE.md §12.2 & §12.6](ARCHITECTURE.md) + Shared preamble + DoD.

```
You are WS 1.5-INGEST for CareerEngine. Build vision-based resume ingestion against the FROZEN v2.0.0
contract. Stay in: tools/resume_parser.py (new), the model-client adapter (add a multimodal method),
workflows/nodes.py (ONLY ingest_node), workflows/prompts.py (ingest prompt), and your tests.

Scope:
- Model-client adapter (integration/model_client.py): add a multimodal entry point, e.g.
  `.generate_multimodal(model_id, system, parts)` where parts carry image/PDF bytes + a text prompt,
  built on google.genai (Gemini is natively multimodal). Capability = SPEED_FAST (gemini-2.5-flash,
  multimodal, free-tier). Injectable/mockable like the existing text path.
- tools/resume_parser.py: `parse_resume(file_bytes, mime_type, *, client=None) -> list[Entry]`.
  Accept PDF and images (png/jpg) first (rasterize PDF pages to images if needed). Send pages to the
  multimodal model with a prompt that returns STRUCTURED JSON -> validate into list[Entry]
  (type/title/org/dates/bullets, source="resume", status=documented or needs_quantifying). Raise a
  typed ParseError on failure/empty. Treat the image as PII: do not persist it; return only Entries.
- ingest_node rework: if a parsed timeline is provided, seed state.work_timeline from it and set
  coverage_through from the latest end_date; set current_phase=GRILLING. Keep ingest idempotent
  (runs once). Use a capability via the registry; NO hardcoded model names.
- ingest prompt: capture ALL entry types (jobs, internships, projects, research, leadership,
  education) — esp. for education-heavy early-career resumes (§12.6).

Acceptance criteria (named tests; mock the multimodal client; deterministic fixtures):
- A fixture "resume" (mocked model returns structured JSON) parses into >=2 Entries with correct
  type/dates; multi-column / table-ish layout note in the prompt is exercised.
- An image input (png bytes) and a PDF input both route through the multimodal path (mock asserts the
  parts include the binary + prompt).
- coverage_through is set to the latest end_date; entries with ""(present) handled.
- Early-career fixture (education + 1 internship + 2 projects) yields entries of those types.
- ParseError on empty/garbage model output; raw bytes never stored on state.
- No hardcoded "gemini-" in tools/ or the adapter.

DoD: `make check` green; report READY FOR REVIEW; don't commit. If you need a PDF->image dep
(e.g. pdf2image/pypdfium2), pin it in pyproject.toml and say so.
```

---

## ✅ 1.5-GRILL — entry-based grill loop (built WITH CONTRACT + METRICS as one merge unit)
> **Coupling decision (resolved):** CONTRACT removes the pillar fields, which breaks `workflows/nodes.py`
> & `discovery_graph.py` at import/type-check. To keep master green, **1.5-CONTRACT + 1.5-GRILL +
> 1.5-METRICS are built in ONE worktree by one Sonnet agent and merged together** (CONTRACT first, then
> this). Run the CONTRACT prompt above first in the same session, then this, then one Opus review of the
> combined diff.
> **After this CORE unit merges, INGEST and DISCOVERY fan out in PARALLEL** — they touch disjoint files
> (INGEST = `workflows/nodes.py` + `tools/`; DISCOVERY = `cli/` only, must NOT touch `nodes.py`). Only the
> CORE unit is serial; the two follow-ups are not. (Sequencing canonical here in §"Sequencing" above and
> in [HANDOFF.md](HANDOFF.md).)

Read first: [ARCHITECTURE.md §12.3–12.4](ARCHITECTURE.md) + Shared preamble + DoD.

```
You are 1.5-GRILL for CareerEngine, continuing in the SAME worktree right after 1.5-CONTRACT (schema is
now v2.0.0: Entry timeline, grill_frontier, reference_date; pillar fields removed). Rework the grill
loop from pillar-based to ENTRY-based so the whole suite is green again. Also fold in 1.5-METRICS.
Stay in: workflows/nodes.py, workflows/discovery_graph.py, workflows/prompts.py, and the existing tests
(tests/test_nodes.py, tests/test_workflow.py, tests/test_integration.py) — update them to the new contract.

Scope:
- ENTRY-based grilling: grill the Entry at state.grill_frontier. On a validated answer, attach a
  StarStory with entry_id == that entry; set the entry status=grilled; advance grill_frontier to the
  next entry needing work, BACKWARD-chronological (most-recent ungrilled first). Frontier is JUMPABLE:
  if grill_frontier already points at a specific entry_id, grill that one.
- DISCOVERY turn: a node/step that confirms coverage_through conversationally and, given the user's
  reply naming new roles/projects, appends Entry(source="discovered", status=needs_quantifying) to
  work_timeline (then they grill like any other).
- SKIP already-quantified: an entry that is status=documented AND already has a metric-bearing bullet
  is marked grilled (or summarized) and NOT re-asked.
- SOFT HORIZON: entries whose end_date is older than ~15 years before state.reference_date default to
  status=summarized (light touch), not deep-grilled. Use reference_date — NEVER datetime.now().
- Minimal entry-based ingest_node: make it seed/keep work_timeline from text input and set
  current_phase=GRILLING (1.5-INGEST later upgrades it with the vision parser — keep the seam clean).
- Keep the 5-turn checkpoint brake (port the existing behavior), HITL semantics, and pure
  (CareerEngineState)->CareerEngineState nodes. Models via registry capability; no hardcoded names.
- METRICS (folded in): extend workflows/nodes._contains_real_metric with early-career / non-eng
  patterns — users/downloads/stars, team size, competition rank, dataset scale, citations, GPA — while
  keeping the existing latency/%/$ patterns.
- discovery_graph.py: keep the turn-based topology (one node per run_async) and the ctx.route shim;
  adapt the router/shims to entry-based state. Router brake semantics unchanged.

Acceptance criteria (named tests; mock the model client; deterministic with a fixed reference_date):
- Vague answer for the frontier entry → REJECTED: current_question set, NO StarStory, entry not grilled.
- Specific answer → StarStory(metrics_validated=True, entry_id==frontier); entry status=grilled.
- Backward frontier: with 3 entries (2024/2021/2018), frontier advances newest-first as each is grilled;
  setting grill_frontier to the 2018 entry_id makes the next grill target 2018 (jumpable).
- Discovery turn appends a discovered Entry from a user reply naming a new role.
- Already-quantified entry is skipped (not re-asked).
- Soft horizon: an entry ending >15y before reference_date is marked summarized, not deep-grilled.
- 5-turn checkpoint brake still fires; checkpoint waits for checkpoint_verified.
- Node purity (deterministic, non-mutating, deps mocked, no datetime.now()).
- _contains_real_metric: a test per new pattern (users/stars/team/rank/citations/GPA) + eng patterns still pass.
- The existing integration e2e is updated to the entry-based flow and still drives the real Runner → PDF.

DoD: `make check` fully green (ALL suites updated to v2.0.0), no hardcoded "gemini-", report READY FOR
REVIEW (combined CONTRACT+GRILL+METRICS diff), do NOT commit.
```

## ✅ 1.5-DISCOVERY — completeness nudge + progress meter + return loop (after CORE)
> CLI-only (no `nodes.py`) → can run **in parallel with 1.5-INGEST** once CORE is merged. Consumes the
> derived helpers `discovery_completeness` / `recent_window_complete` (defined in CONTRACT) and the
> entry-based grill loop (GRILL). Read first: [ARCHITECTURE.md §12.4](ARCHITECTURE.md) + Shared preamble + DoD.

```
You are 1.5-DISCOVERY for CareerEngine. Surface progressive discovery in the CLI. Build against the
merged v2.0.0 contract + entry-based grill loop. Stay in: cli/app.py, cli/session.py, main.py, a new
cli/prefs.py (snooze), and your tests. Do NOT touch workflows/nodes.py, schema.py, or config.py.

Core principle: discovery is a NUDGE, never a gate. Applying/tailoring is NEVER blocked.

Scope:
- PROGRESS METER: a `status`/start surface that renders from schema.discovery_completeness(state) and
  recent_window_complete(state) — e.g. "Recent 5-yr window: 80% documented · portfolio depth: 12 yrs".
  Pure read of the derived helpers; pass reference_date in (no datetime.now() in logic).
- NUDGE on apply/tailor AND on launch: if recent_window_complete is False (and not snoozed), print the
  consent-respecting message ("tailored resumes are stronger with the rest of your recent history filled
  in — continue now / remind me later"). The action ALWAYS proceeds regardless of the user's choice.
- TAILORING NEVER GATED: verify the tailor/apply path has no readiness check that blocks; it only emits
  the nudge.
- RETURN LOOP: on launch, if work_timeline has entries needing work older than grill_frontier, offer
  "continue working on your resume?" → if yes, drive grilling BACKWARD from the frontier via the Runner
  (reuse the CORE grill loop / turn-based CLI driver); if no, proceed without grilling.
- SNOOZE (cli/prefs.py): persist a `snooze_until` date in a small local JSON under a user-config path
  (NOT in CareerEngineState — that carries no UI state). The nudge respects it; "today" is injected for
  determinism (read now() only at the CLI boundary, like reference_date). NOTE in a docstring: Phase 2
  migrates snooze to the cross-device workspace doc (§8 dashboard).

Acceptance criteria (named tests; deterministic with fixed reference_date / injected "today"):
- Progress meter renders correct % + depth from a fixture state via the helpers.
- Nudge IS shown when recent_window_complete is False; NOT shown when True; NOT shown when snoozed.
- Apply/tailor with an incomplete window STILL proceeds (returns a result) — only the nudge is emitted.
- Snooze suppresses the nudge until snooze_until, then it returns once "today" passes it.
- Return-loop: launch with older ungrilled entries shows the "continue?" offer; declining proceeds
  cleanly; accepting drives one backward grill turn (mock the runner/grill).
- No CareerEngineState mutation for UI/snooze state.

DoD: `make check` green; no hardcoded "gemini-"; report READY FOR REVIEW; do NOT commit.
```

## ✅ 1.5-METRICS — metric validator extension (FOLDED INTO 1.5-GRILL)
Groomed inside the 1.5-GRILL prompt (same file, `workflows/nodes._contains_real_metric` + per-pattern
tests). Not a separate workstream.

---

## v2.0 (post-v1) — captured, NOT groomed
- **Interview preparedness** ([ARCHITECTURE.md §13](ARCHITECTURE.md)): research company+role interview
  shape → agent-driven mock interviews w/ feedback. Distant future; groom only when v1 ships.
