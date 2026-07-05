"""Unit tests for discovery/cli.py — run_discover orchestration (offline).

Uses a fake Scout (canned batches) + the heuristic evaluator + InMemoryLedgerStore,
so the full loop → print → persist path is exercised without auth or network.
(Named ``_loop_cli`` to avoid colliding with the older progressive-discovery
``test_discovery_cli.py``, which covers the unrelated grill nudge/meter.)
"""

from __future__ import annotations

from discovery.cli import run_discover
from discovery.primary import PrimaryAgent
from discovery.scout import Scout
from discovery.store import InMemoryLedgerStore
from schema import (
    InteractionLedger,
    JobMetadata,
    JobOpportunity,
    ScoutDirective,
    SessionPreferences,
    make_job_id,
)

_PREFS = SessionPreferences(target_roles=["Fractional CTO"], nice_to_haves=["AWS", "MCP"])


def _job(ext: str, *, title: str = "Engineer", company: str = "Acme", desc: str = "") -> JobOpportunity:
    return JobOpportunity(
        job_id=make_job_id("remotive", ext),
        metadata=JobMetadata(title=title, company=company),
        raw_description=desc,
    )


class _ScriptedTools:
    def __init__(self, batches: list[list[JobOpportunity]]) -> None:
        self._batches = batches
        self.calls = 0

    async def search_jobs(self, directive: ScoutDirective) -> list[JobOpportunity]:
        idx = min(self.calls, len(self._batches) - 1)
        self.calls += 1
        return self._batches[idx]

    async def fetch_jd(self, url: str) -> str:
        return ""


def _primary(tools: _ScriptedTools, ledger: InteractionLedger | None = None) -> PrimaryAgent:
    return PrimaryAgent(
        prefs=_PREFS,
        ledger=ledger or InteractionLedger(),
        scout=Scout(tools=tools),
        desired_total=2,
        max_iterations=3,
    )


async def test_run_discover_prints_and_persists() -> None:
    lines: list[str] = []
    tools = _ScriptedTools([[_job("1", desc="AWS"), _job("2", desc="MCP")]])
    store = InMemoryLedgerStore()
    result = await run_discover(
        user_id="u1", primary=_primary(tools), store=store, out=lines.append
    )
    assert len(result.accepted) == 2
    joined = "\n".join(lines)
    assert "ACCEPTED" in joined and "Persisted 2" in joined
    assert len(store.load_ledger("u1").already_applied_ids) == 2


async def test_run_discover_is_idempotent_across_runs() -> None:
    batch = [_job("1", desc="AWS"), _job("2", desc="MCP")]
    store = InMemoryLedgerStore()
    await run_discover(
        user_id="u1", primary=_primary(_ScriptedTools([batch])), store=store, out=lambda _s: None
    )
    # Second run: reload the ledger so already-seen jobs hard-reject.
    ledger = store.load_ledger("u1")
    lines: list[str] = []
    result = await run_discover(
        user_id="u1",
        primary=_primary(_ScriptedTools([batch]), ledger=ledger),
        store=store,
        out=lines.append,
    )
    assert result.accepted == []
    assert result.hard_rejected_count == 2
    assert "No new opportunities" in "\n".join(lines)


async def test_run_discover_handles_empty_source() -> None:
    lines: list[str] = []
    result = await run_discover(
        user_id="u1",
        primary=_primary(_ScriptedTools([[]])),
        store=InMemoryLedgerStore(),
        out=lines.append,
    )
    assert result.accepted == [] and result.soft_rejected == []
    assert "No new opportunities" in "\n".join(lines)
