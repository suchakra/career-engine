"""CLI orchestration for the two-agent discovery loop.

Split so the loop is testable without auth/network:

- :func:`run_discover` — the pure-ish orchestrator: runs a pre-built
  :class:`PrimaryAgent`, prints the classified results, and persists accepted jobs
  to an injected :class:`LedgerStore`. Fully exercisable offline with a fake Scout.
- :func:`discover_command` — the thin CLI entrypoint: resolves auth + model client,
  hydrates the ledger from the store, wires the Scout + Primary, and drives
  :func:`run_discover`. This is where the untestable IO lives.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from discovery.preferences import default_session_preferences
from discovery.primary import DiscoveryResult, ModelEvaluator, PrimaryAgent
from discovery.scout import Scout
from discovery.store import InMemoryLedgerStore, LedgerStore
from schema import JobOpportunity, SessionPreferences


def _format_job(job: JobOpportunity, index: int) -> str:
    """Render one classified job for the terminal."""
    meta = job.metadata
    status = job.match_status.value if job.match_status else "unknown"
    return (
        f"  {index}. [{status.upper()}] {meta.title} — {meta.company}\n"
        f"     {meta.employment_type.value} · {meta.work_model.value} · {meta.location or 'n/a'}\n"
        f"     {meta.url}\n"
        f"     → {job.ai_rationale}"
    )


def _print_result(result: DiscoveryResult, out: Callable[[str], None]) -> None:
    """Print the accepted / soft-rejected batches and loop stats."""
    out(
        f"\nDiscovery finished in {result.iterations} iteration(s): "
        f"{len(result.accepted)} accepted · {len(result.soft_rejected)} for review · "
        f"{result.hard_rejected_count} hard-rejected."
    )
    if result.accepted:
        out("\n✅ ACCEPTED (strong matches):")
        for i, job in enumerate(result.accepted, 1):
            out(_format_job(job, i))
    if result.soft_rejected:
        out("\n🟡 FOR REVIEW (soft matches):")
        for i, job in enumerate(result.soft_rejected, 1):
            out(_format_job(job, i))
    if not result.accepted and not result.soft_rejected:
        out("\nNo new opportunities this run (all hard-rejected or already seen).")


async def run_discover(
    *,
    user_id: str,
    primary: PrimaryAgent,
    store: LedgerStore,
    out: Callable[[str], None] = print,
) -> DiscoveryResult:
    """Run the discovery loop, print results, and persist accepted jobs.

    Args:
        user_id: Owner of the ledger the accepted jobs are recorded against.
        primary: A pre-wired Primary agent (holds prefs, ledger, Scout, evaluator).
        store: Where accepted jobs are persisted (idempotent by job_id).
        out: Output sink (injectable for tests).

    Returns:
        The accumulated :class:`DiscoveryResult`.
    """
    result = await primary.discover()
    _print_result(result, out)
    if result.accepted:
        written = store.record_accepted(user_id, result.accepted)
        out(f"\nPersisted {written} new accepted job(s) to your ledger (idempotent).")
    return result


def discover_command(
    *,
    use_firestore: bool = False,
    desired_total: int = 5,
    max_iterations: int = 3,
    prefs: SessionPreferences | None = None,
    out: Callable[[str], None] = print,
) -> DiscoveryResult:
    """Resolve dependencies and run one discovery session (CLI entrypoint).

    Always uses the agentic :class:`ModelEvaluator`; with no usable key its per-batch
    model call fails and it falls back to the deterministic heuristic, so the demo
    runs live when a key is present and still works offline.
    """
    from cli.app import resolve_auth_and_client

    user_id, access_mode, client = resolve_auth_and_client()
    session_prefs = prefs or default_session_preferences()

    store: LedgerStore
    if use_firestore:
        try:
            from discovery.store import FirestoreLedgerStore

            store = FirestoreLedgerStore()
        except Exception as exc:  # surface the downgrade loudly, don't crash
            out(f"⚠  Firestore unavailable ({type(exc).__name__}); using in-memory store.")
            store = InMemoryLedgerStore()
    else:
        store = InMemoryLedgerStore()

    ledger = store.load_ledger(user_id)
    evaluator = ModelEvaluator(client, access_mode=access_mode)
    primary = PrimaryAgent(
        prefs=session_prefs,
        ledger=ledger,
        scout=Scout(),
        evaluator=evaluator,
        desired_total=desired_total,
        max_iterations=max_iterations,
    )
    out(f"\nCareerEngine — job discovery ({access_mode.value} mode) for {user_id}")
    out(f"Targets: {', '.join(session_prefs.target_roles) or '(none)'}")
    out("=" * 60)
    return asyncio.run(run_discover(user_id=user_id, primary=primary, store=store, out=out))
