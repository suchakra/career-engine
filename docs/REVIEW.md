# CareerEngine Review

Date: 2026-06-29
Scope: Plan and status review across docs, then delivered code review across the repository.

## 1. Executive Summary

The project has a strong contract-first architecture and good test depth, but there are several high-impact risks to address before Phase 1.5 build execution:

1. Upgrade-required signaling path is inconsistent across workflow to CLI.
2. URL scraping flow has SSRF exposure risk.
3. Firestore fallback can silently degrade to in-memory persistence.
4. Exception handling is too broad in several boundary modules.
5. Docs have status and sequencing drift that can mislead execution planning.

## 2. Findings (Ordered by Severity)

### Critical

1. Upgrade-required signal is effectively lost before CLI handling
Evidence:
- [workflows/discovery_graph.py](workflows/discovery_graph.py#L209) stores upgrade data in an internal state key.
- [cli/app.py](cli/app.py#L397) detects upgrade by searching text in current_question, not by reading the internal signal.
- [cli/app.py](cli/app.py#L514) depends on that boolean to display upgrade messaging.
Impact:
- Capability shortfall may not produce the intended user guidance path.
- Revenue/upgrade UX path can fail silently.

2. SSRF risk in job-description URL ingestion
Evidence:
- [tools/web_scraper.py](tools/web_scraper.py#L138) accepts arbitrary URLs.
- [tools/web_scraper.py](tools/web_scraper.py#L155) fetches directly without private-network safeguards.
- [cli/app.py](cli/app.py#L561) forwards user URL input into scraper flow.
Impact:
- In hosted environments, attacker-controlled URLs can probe internal services.

3. Firestore requested mode can silently downgrade to in-memory
Evidence:
- [cli/app.py](cli/app.py#L83) catches all exceptions while creating Firestore service.
- [cli/app.py](cli/app.py#L86) falls back to in-memory service without explicit user confirmation.
Impact:
- Persistence expectations can be violated without visibility.
- Data durability and trust risk for end users.

4. Node model-client interface swallows failures
Evidence:
- [integration/model_client.py](integration/model_client.py#L87) catches all exceptions.
- [integration/model_client.py](integration/model_client.py#L88) returns empty string on error.
Impact:
- Hard failures appear as weak model output.
- Diagnostics and operational visibility are reduced.

### High

5. Exception policy is inconsistent and broad in auth/network boundaries
Evidence:
- [auth/firebase_auth.py](auth/firebase_auth.py#L59)
- [auth/cli_auth.py](auth/cli_auth.py#L208)
- [tools/web_scraper.py](tools/web_scraper.py#L109)
Impact:
- Expected user errors, transient network faults, and infra errors are not cleanly separated.

6. Test fake lives in production persistence module
Evidence:
- [database/firestore_session.py](database/firestore_session.py#L252) defines FakeFirestoreClient in production module.
Impact:
- Increases coupling and maintainability burden.
- Blurs production versus test boundaries.

### Medium

7. Documentation status drift on implementation state
Evidence:
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#L3) still says pre-implementation.
- [docs/HANDOFF.md](docs/HANDOFF.md#L4) states Phase 0 and 1 are built and merged.
- [docs/PROGRESS.md](docs/PROGRESS.md#L6) last-updated banner is stale relative to handoff.
Impact:
- New contributors and agents can start with conflicting assumptions.

8. Grooming sequencing inconsistency for Phase 1.5
Evidence:
- [docs/GROOMING.md](docs/GROOMING.md#L23) says INGEST and DISCOVERY can fan out in parallel.
- [docs/GROOMING.md](docs/GROOMING.md#L114) says run serially after core merge.
- [docs/GROOMING.md](docs/GROOMING.md#L176) says DISCOVERY should not touch nodes.
Impact:
- Ambiguous execution plan for agent orchestration.

9. Stale behavior notes in CLI module docs
Evidence:
- [cli/app.py](cli/app.py#L21) says ingest re-runs each turn.
- [workflows/discovery_graph.py](workflows/discovery_graph.py#L159) gates ingest by phase.
Impact:
- Misleading maintenance guidance.

10. Key existence check suppresses non-NotFound cloud errors
Evidence:
- [auth/key_vault.py](auth/key_vault.py#L145)
- [auth/key_vault.py](auth/key_vault.py#L162)
- [auth/key_vault.py](auth/key_vault.py#L165)
Impact:
- Transient or permission failures can be interpreted as no-key state.

11. Upgrade-required integration coverage gap
Evidence:
- Node-level coverage exists in [tests/test_nodes.py](tests/test_nodes.py#L333).
- No clear end-to-end assertion of CLI detection path in [tests/test_integration.py](tests/test_integration.py).
Impact:
- Regressions in the escalation path may pass test gates.

## 3. Strengths

1. Strong typed contract and schema discipline in [schema.py](schema.py).
2. Clean capability abstraction and routing in [models/registry.py](models/registry.py).
3. Good workflow decomposition in [workflows/nodes.py](workflows/nodes.py) and [workflows/discovery_graph.py](workflows/discovery_graph.py).
4. Broad test suite coverage across core paths in [tests](tests).
5. Good separation of identity and secrets responsibilities in [auth/provider.py](auth/provider.py), [auth/cli_auth.py](auth/cli_auth.py), and [auth/key_vault.py](auth/key_vault.py).

## 4. Recommended Priority Plan

### P0 Immediate

1. Fix end-to-end upgrade-required signaling from workflow to CLI result handling.
2. Add SSRF safeguards for URL ingestion and fetch execution.
3. Replace silent Firestore fallback with explicit failure signaling and mode confirmation.

### P1 Next

1. Standardize exception handling policy by layer and error class.
2. Move FakeFirestoreClient into test-only location.
3. Add integration tests for upgrade-required user path.

### P2 Hardening

1. Align docs status headers to one source of truth.
2. Resolve Phase 1.5 grooming sequencing contradictions.
3. Remove stale inline comments/docstrings that no longer match behavior.

## 5. Open Questions — RESOLVED 2026-06-29

1. **Firestore failure policy → DECIDED: environment-aware + loud.**
   An explicit `use_firestore` request (or `ENV=prod`) hard-stops on failure — never silently
   downgrades. In-memory is allowed only as the dev *default*, and must announce itself loudly
   ("⚠ in-memory — nothing persists"). Implement at **Phase 2** (gates #3).
2. **Scraper URL policy → DECIDED: deny private ranges + audit, not an allowlist.**
   Block RFC-1918 / link-local / cloud-metadata IPs, re-validate the host after *each* redirect
   hop, and audit-log every fetch. No domain allowlist (job URLs are open-world); revisit only if
   abuse appears. Implement in **1.5-INGEST** (gates #2).
3. **Upgrade-required representation → DECIDED: first-class typed event/field.**
   Add to the **v2.0.0** contract as a typed state field/event; retire the `ctx.state`
   side-channel. This fixes #1 at the root and makes the #11 E2E test meaningful. Implement in
   **1.5-CONTRACT** (gates #1b). A cheap band-aid (read the real key) still goes in **1.3** to
   stop the silent revenue-path failure on the current v1.1.x foundation.

## 6. Review Constraints

1. This review is based on repository docs and source/tests inspection.
2. Runtime gate execution results are recorded separately after gate run.

---

## 7. Triage & Sequencing (Opus, 2026-06-29)

> Author's note: validated the load-bearing findings against source before triaging.
> Buckets are **1.3** (new hardening micro-phase), **1.5** (fold into the groomed build),
> and **Beyond** (Phase 2/3). No code written yet — this is the execution plan.

### 7.1 Validation notes (what the code actually shows)
- **#1 is real and likely dead today.** The signal is written to `ctx.state["_upgrade_required"]`
  as typed JSON ([discovery_graph.py:209](../workflows/discovery_graph.py#L209)), but the CLI
  detects it by string-searching `current_question` for `"_upgrade_required"`
  ([cli/app.py:397](../cli/app.py#L397)). Two different channels — the boolean at
  [cli/app.py:514](../cli/app.py#L514) will basically never fire unless the literal token leaks
  into question text. The revenue/upgrade UX path is effectively silent.
- **#2 (SSRF) is real but not yet exposed.** [fetch_raw_html](../tools/web_scraper.py#L138)
  follows redirects with zero host validation — but Phase 1 is local CLI. Exposure lands at
  **Phase 2** (Cloud Run hosting).
- **#5 is partly overstated.** `web_scraper` already separates `TimeoutException`/`RequestError`
  and wraps in `ScraperError`. The genuine cross-cutting offenders are #3, #4, #10.
- **#9 confirmed.** [discovery_graph.py:155](../workflows/discovery_graph.py#L155) gates ingest by
  phase, so the "ingest re-runs each turn" docstring at [cli/app.py:21](../cli/app.py#L21) is stale.

### 7.2 Organizing principle
Phases are contract-versioned: Phase 1 = contract **v1.1.0**, Phase 1.5 = **v2.0.0**. That gives
the cut line:
- **1.3** = hardening that does **not** change the public contract (stays v1.1.x). Correctness/
  hygiene on the foundation 1.5 builds on. Do before launching 1.5 builders.
- **1.5** = anything that **needs** the v2.0.0 contract rework, or lives in files 1.5 already
  touches (CONTRACT / INGEST / DISCOVERY). Fold in — don't touch those files twice.
- **Beyond (Phase 2/3)** = exposure-gated by hosting (SSRF, Firestore durability, Secret Manager)
  or systematic cleanup ranked P2/P3 here.

### 7.3 Bucket assignments

| # | Finding | Bucket | Rationale |
|---|---------|--------|-----------|
| 7 | Docs status drift (ARCHITECTURE says pre-impl) | **1.3 — now** | Three AI tools now treat `docs/` as source of truth; stale headers actively mislead them. ~10 min. |
| 8 | Grooming sequencing contradiction (parallel vs serial) | **1.3 — now** | Decides *how* 1.5 builders launch. Must resolve before the build. Doc-only. |
| 1 | Upgrade signal lost — band-aid | **1.3** | Cheap correctness fix: read the real `ctx.state` signal, not string-match. Revenue path is silently dead today. |
| 11 | Upgrade-required E2E test gap | **1.3** | Pairs with #1 — lock the path with an integration test so 1.5 can't regress it. |
| 4 | model_client swallows errors → `""` | **1.3** | Hard failures masquerading as weak output will make debugging the 1.5 build itself miserable. Foundation hygiene. |
| 3 | Firestore silent fallback | **1.3 (make it loud)** → policy at Phase 2 | Cheap: stop catching-all, log/announce the downgrade. Prod-vs-dev *policy* (OQ1) is a Phase-2 decision. |
| 6 | FakeFirestoreClient in prod module | **1.3 optional** | Trivial move, reduces confusion for all tools. Low value now; fine to defer to next Firestore touch. |
| 1b | Upgrade-required as first-class typed state/event | **1.5 (CONTRACT)** | This *is* a contract change → belongs in the v2.0.0 rework, not a v1.1.x patch. Band-aid in 1.3, do it right here. |
| 9 | Stale "ingest re-runs each turn" docstring | **1.5 (DISCOVERY)** | DISCOVERY already edits `cli/app.py` — fix in passing, don't touch the file twice. |
| 2 | SSRF in URL ingestion | **1.5 (INGEST) build; hard-gate before Phase 2** | INGEST expands the scraper surface; add allowlist / private-range deny while in that code. Must ship before hosting. |
| 10 | key_vault suppresses non-NotFound errors | **Phase 2** | Only load-bearing once Secret Manager / BYOK is hosted. Bundle with cloud-auth work. |
| 5 | Systematic exception-policy standardization | **Phase 3 hardening** | Review's own P1/P2. High-value slices (#3,#4,#10) pulled forward; don't gold-plate the rest now. |

### 7.4 Suggested Phase 1.3 scope (tight, non-contract-breaking, stays v1.1.x)
A "stabilize the foundation" pass before launching 1.5:
**#7, #8** (doc truth — also unblocks the cross-tool setup), **#1 band-aid + #11 test**, **#4**,
**#3 make-it-loud**, optionally **#6**. Everything stays at contract v1.1.x, so it will not collide
with the groomed 1.5 prompts.

### 7.5 Open questions → phase gates
Each Open Question (§5) maps to one Critical and gates a specific phase; decide before that phase:
1. **Firestore failure policy** (OQ1) → gates **Phase 2** (#3).
2. **Scraper URL policy** (OQ2) → gates **1.5-INGEST** (#2).
3. **Upgrade-required representation** (OQ3) → gates **1.5-CONTRACT** (#1b). Lean: typed event,
   since the contract is already breaking to v2.0.0.

> Status: all three open questions RESOLVED 2026-06-29 — see §5 for decisions (all gates confirmed).
