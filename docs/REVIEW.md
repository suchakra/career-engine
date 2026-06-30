# CareerEngine Review

Date: 2026-06-29
Scope: review of the last five commits and the current Phase 1.5 implementation state.

## Executive Summary

The last five commits materially improved the codebase. The earlier highest-risk issue, the upgrade-required path from workflow to CLI, is now handled end-to-end and covered by an integration test. The model client no longer collapses failures into an empty string, Firestore fallback is loud instead of silent, and resume ingest now supports PDFs and images through a multimodal adapter. Phase 1.5 is legitimately complete at the core-contract level.

What is still open is narrower and mostly intentional: the CLI resume-file path is not yet wired, true session reload for the return loop is still deferred, and `discovery_turn_node` exists but is not yet surfaced as a main-graph edge. Those are real integration gaps, but they are now documented as deferred work rather than mistaken for shipped behavior.

## What The Last Five Commits Landed

1. `dc07f98` and `f3ba142` completed the contract v2.0.0 merge and the entry-based grill loop foundation.
2. `82a2f82` added the vision resume parser and multimodal model client support.
3. `986c7c8` added the CLI progress meter, nudge logic, and return-loop flow.
4. `ec7022e` reconciled the docs to say Phase 1.5 is complete and to list the remaining integration seams explicitly.

The important part is that these commits do not just add features; they also close most of the earlier review concerns at the right layer.

## Findings

### 1. The earlier upgrade-required bug is fixed and now tested

This was the most important concern in the original review. It is no longer a live blocker. The CLI now reads the actual `_upgrade_required` signal from session state in [cli/app.py](../cli/app.py#L382-L396), and the integration test in [tests/test_integration.py](../tests/test_integration.py#L598-L701) asserts that the real signal produces `upgrade_required=True` and surfaces the user message.

That closes the gap between the workflow signal and the user-facing result. It also removes the old string-match failure mode from the review history.

### 2. Resume ingest is now meaningfully safer and more capable, but only for the parser path

The ingest path now accepts PDFs and common image formats in [tools/resume_parser.py](../tools/resume_parser.py#L35-L187) and sends them through a multimodal client instead of rasterizing or silently dropping content. The adapter in [integration/model_client.py](../integration/model_client.py#L78-L200) now has a dedicated multimodal entry point.

The remaining gap is not the parser itself; it is the CLI wiring. [docs/HANDOFF.md](../docs/HANDOFF.md#L11-L19) correctly says the file-upload seam is still missing from `grill`, even though `ingest_node` already accepts a pre-seeded `work_timeline`. That means the code path is solid, but the user-facing entry point is still incomplete.

### 3. Firestore fallback is no longer silent, but it still downgrades

The warning in [cli/app.py](../cli/app.py#L77-L104) is a real improvement over the earlier behavior. The operator now sees that the app is falling back to in-memory storage instead of being tricked into thinking persistence is active.

That said, the behavior is still a downgrade rather than a hard failure. For local development that is acceptable, and the docs now frame it that way. For a production posture, the fallback still deserves a Phase 2 policy decision because it can hide persistence failures if the warning is missed.

### 4. The model-client failure handling is materially better

The old empty-string failure mode is gone from [integration/model_client.py](../integration/model_client.py#L78-L200). That matters because empty strings blur actual model output with infrastructure failure. The client now exposes multimodal generation directly and does not pretend failure is a valid response.

This is a good repair. It makes debugging the ingest and discovery paths much more honest.

### 5. Phase 1.5 is complete in the core graph, but one workflow edge is still intentionally missing

`discovery_turn_node` exists in [workflows/nodes.py](../workflows/nodes.py#L460-L460) and the graph file explicitly says it is not yet part of the main workflow in [workflows/discovery_graph.py](../workflows/discovery_graph.py#L18-L19). The handoff repeats that same point in [docs/HANDOFF.md](../docs/HANDOFF.md#L11-L19).

This is not a hidden bug anymore; it is a documented deferred integration item. I still consider it the main remaining surface gap because it is the difference between "the node exists and is tested" and "the CLI actually surfaces the return-loop experience end-to-end."

## Strengths

The repository is now in a much healthier place than it was before these commits. The contract boundaries are typed, the new phase-specific behavior is covered by tests, the docs finally match the shipped state, and the deferred work is called out plainly instead of being implied.

The strongest change in this round is not any single function. It is that the repo now has a cleaner contract between "built and tested" and "surfaced in the CLI," which makes the remaining roadmap much easier to trust.

## Residual Risks

1. The Firestore fallback still relies on the operator noticing a warning, so it remains a durability risk until Phase 2 policy hardens it.
2. The resume-file path is still only half-done from a user perspective because the parser exists but the CLI upload is not wired.
3. The discovery return loop is implemented, but the missing main-graph edge means the feature is not yet fully discoverable from the normal path.

## Recommendation

Treat Phase 1.5 as complete and move on to the small integration pass before broadening scope. The next best work is to wire the resume-file upload into `grill`, decide whether the Firestore fallback should become a hard stop in the hosted path, and connect `discovery_turn_node` to the main graph when you are ready to surface the return-loop experience publicly.

If you want the next review to be stricter, the best target is not the core Phase 1.5 code anymore; it is the remaining CLI and persistence seams.
