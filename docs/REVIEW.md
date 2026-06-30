# CareerEngine Review — Phase 1.7

Date: 2026-06-30
Scope: diff ec7022e..HEAD (Phase 1.7 — four workstreams: session resume, resume-file CLI upload, discovery-turn graph wiring, FakeFirestore relocation).
Gate result at review time: **339 tests, make check green** (ruff + mypy --strict + pytest).

## Verdict

**PASS — ready to push.** No must-fix items. Three optional improvements noted below.

---

## What landed

| Commit | Summary |
|--------|---------|
| `7b86bb8` | 1.7-B: `get_session_state_if_exists` + load-before-create resume path in CLI |
| `e032092` | docs: Phase 1.7 grooming (Copilot) |
| `7c43714` | 1.7-A: `--resume-file` flag, `guess_resume_mime`, `parse_resume_file` |
| `c39ce72` | 1.7-D: `FakeFirestoreClient` + `_Fake*` hierarchy moved to `tests/fakes.py` |
| `6cc736c` | 1.7-C: `discovery_turn_node` wired into graph; `coverage_confirmed` field; CONTRACT_VERSION 2.1.0 |
| `2d1a939` | docs: reconcile |
| `67ca0ec` | Sonnet review nits (PASS, 0 must-fix) |
| `614e25a` | docs: record Sonnet PASS |

---

## Finding-by-finding

### 1.7-B — session resume (PASS)

`get_session_state_if_exists` in [cli/session.py](../cli/session.py) is the right primitive: thin, clearly docstringed, returns `None` for a missing session rather than raising. The CLI in [cli/app.py](../cli/app.py) uses it to gate the resume path correctly — a missing session id prints a user-safe error and returns cleanly instead of clobbering or crashing.

The `is None` guard also correctly distinguishes in-memory vs. Firestore by telling the user they need Firestore to resume cross-run when not using `--firestore`. That is the right user-facing message.

Test coverage in [tests/test_session_resume.py](../tests/test_session_resume.py) is complete: existing session loads without clobber (frontier and question_count preserved), missing session returns None, fresh session starts as INGESTING, and the CLI error path is asserted on stderr without raising. All four pass.

**No issues.**

### 1.7-A — resume-file CLI upload (PASS)

`guess_resume_mime` in [cli/app.py](../cli/app.py) is correct: extension-first lookup with `mimetypes` fallback and safe default (`application/octet-stream`) that `parse_resume` will reject with a clear `ParseError`. Raw bytes never touch `CareerEngineState` — the helper reads, parses, and discards them at the CLI boundary.

The `main.py` option wiring is clean: `--resume-file` accepts an existing readable path, text history becomes optional when a file is given, and the empty-input guard was correctly updated to only fail when neither source is present.

Test coverage in [tests/test_resume_file_cli.py](../tests/test_resume_file_cli.py) covers MIME detection (parametrized), PDF + image parse-and-seed, unsupported extension raises `ParseError`, and empty file raises `ParseError`. All pass.

**Optional (non-blocking).** `guess_resume_mime` does case-folding with `.suffix.lower()` but does not give an explicit early message for files with no extension. An extensionless file gets `application/octet-stream` and then a generic `ParseError` from the downstream parser. The behavior is correct but the user message could be friendlier. A one-liner guard could be added later with no contract impact.

### 1.7-C — discovery-turn graph wiring (PASS)

The router change in [workflows/discovery_graph.py](../workflows/discovery_graph.py) is well-structured: `COMPLETE` is now its own early return, and the discovery-turn branch fires only when `coverage_through` is set, `coverage_confirmed` is False, and the phase is not `CHECKPOINT`. Those three guards prevent the turn from running on text-only sessions, from re-running after the user answers, and from interrupting a checkpoint-in-progress. All three conditions have dedicated router tests in [tests/test_workflow.py](../tests/test_workflow.py).

The `_discovery_shim` and `FunctionNode` addition are correctly wired as terminal-per-turn, consistent with the grill and checkpoint shims. The `discovery_turn_node` changes in [workflows/nodes.py](../workflows/nodes.py) correctly set `coverage_confirmed=True` and clear `current_question` on the PROCESS pass, and provide a non-empty defensive fallback question on the ASK pass.

The contract bump to `v2.1.0` for the `coverage_confirmed` field is correct: backward-compatible MINOR addition (new optional field, default False), properly stamped in `config.py`, round-trip test updated.

The end-to-end integration test `TestDiscoveryTurnInGraph` in [tests/test_integration.py](../tests/test_integration.py) exercises both turns through the real ADK runner — ASK (question surfaced, `coverage_confirmed` still False) then PROCESS (entry appended, `coverage_confirmed` True). This is the strongest possible coverage short of a live network call.

**Optional (non-blocking).** The routing invariant relies on `coverage_through` only being set by `ingest_node`. If a future flow sets it manually without going through vision ingest, the discovery turn would fire unexpectedly. This is not a present bug. Worth adding a sentence to the `coverage_through` field description in `schema.py` noting that only `ingest_node` should write it, to protect the invariant for future contributors.

### 1.7-D — FakeFirestore relocation (PASS)

The move from [database/firestore_session.py](../database/firestore_session.py) to [tests/fakes.py](../tests/fakes.py) is complete and correct. The production module docstring for `FirestoreSessionService` was updated to drop the `FakeFirestoreClient` mention and replace it with "any object with the async Firestore client surface," which is the right abstraction. The `test_firestore_session.py` import was updated. No logic changed.

**No issues.**

---

## Security checklist

- No secrets written to Firestore or logged.
- Raw resume bytes are read at the CLI boundary and passed straight to the parser; not stored on `CareerEngineState`, not logged anywhere.
- No hardcoded model IDs in any new or changed file.
- `CONTRACT_VERSION` bumped and stamped correctly (2.0.0 → 2.1.0, MINOR).
- No new broad exception catches; `ParseError` and `OSError` are the specific catch sites in the resume-file path, both handled gracefully with user-facing messages.

---

## Strengths of this diff

The four workstreams were merged in dependency order (B → A → D → C), which is the right sequencing. Test files are well-scoped and named to match the workstreams. The `coverage_confirmed` field is the minimal possible contract addition — no new enums, no breaking changes. The `_discovery_shim` follows the exact pattern of `_grill_shim` and `_checkpoint_shim`, keeping the graph code uniform.

---

## Optional improvements (non-blocking, all low priority)

1. Add an early guard or clearer error in `guess_resume_mime` for files with no extension, so users get a friendlier message than a generic `ParseError`.
2. Add a note to the `coverage_through` field description in `schema.py` that only `ingest_node` should write it, to protect the routing invariant.
3. The `test_missing_session_id_prints_safe_message_no_raise` test monkeypatches `resolve_auth_and_client` by name; a future rename would silently break the test. A named fixture or interface extraction would make it more resilient.
