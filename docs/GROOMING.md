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
| **1.5-CONTRACT** | schema v2.0.0: Entry timeline, replace pillar fields, version bump, golden test | — (blocking, solo, freeze first) | ✅ Ready |
| **1.5-INGEST** | vision resume parser + multimodal client + `ingest_node` → timeline | CONTRACT frozen | ✅ Ready |
| **1.5-GRILL** | entry-based grill loop, discovery turn, `grill_frontier`, skip-quantified | CONTRACT frozen | ◐ Draft |
| **1.5-DISCOVERY** | `discovery_completeness` signal, nudge, progress meter, never-block tailoring | CONTRACT, GRILL | ⬜ To groom |
| **1.5-METRICS** | extend `_contains_real_metric` for early-career/non-eng metrics | CONTRACT | ◐ Draft (small) |

**Sequencing:** CONTRACT (solo → freeze) → INGEST ∥ GRILL(+METRICS) → DISCOVERY.
**Groomed so far:** CONTRACT, INGEST. **Next to groom:** GRILL (then DISCOVERY, METRICS).

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

## ◐ 1.5-GRILL — entry-based grill loop (DRAFT — groom next)
Outline (needs full acceptance criteria before launch):
- Rework workflows/nodes.py + discovery_graph.py from pillar-based to **entry-based**: grill the entry
  at `grill_frontier`; on a validated answer, attach StarStory with `entry_id`, mark entry `grilled`,
  advance frontier to the next entry needing work (backward-chronological by default; jumpable).
- **Discovery turn**: confirm coverage_through conversationally, append discovered Entries
  (source="discovered") to work_timeline.
- Skip entries already `documented` with metrics (don't re-grill); soft horizon ~10–15 yrs → mark older
  `summarized`.
- Keep the 5-turn checkpoint brake; keep nodes pure; reference_date injected.
- Likely co-built or co-frozen with 1.5-CONTRACT (since CONTRACT removes the fields this uses).
- TODO when grooming: exact named tests (backward frontier advance, discovery append, skip-quantified,
  entry↔story linkage, purity).

## ⬜ 1.5-DISCOVERY — completeness nudge + progress meter (TO GROOM)
- Surface `discovery_completeness`/`recent_window_complete` as a **nudge** on each apply/tailor (CLI now,
  Streamlit Phase 2), snooze-able; tailoring NEVER blocked. Progress meter from the derived helpers.
- Depends on CONTRACT (helpers) + GRILL (frontier). Groom after GRILL.

## ◐ 1.5-METRICS — metric validator extension (DRAFT — small)
- Extend `workflows/nodes._contains_real_metric` patterns for early-career/non-eng wins: users/downloads/
  stars, team size, competition rank, dataset scale, citations, GPA-where-relevant. Add tests per pattern.
- Tiny; can fold into 1.5-GRILL or run standalone after CONTRACT.

---

## v2.0 (post-v1) — captured, NOT groomed
- **Interview preparedness** ([ARCHITECTURE.md §13](ARCHITECTURE.md)): research company+role interview
  shape → agent-driven mock interviews w/ feedback. Distant future; groom only when v1 ships.
