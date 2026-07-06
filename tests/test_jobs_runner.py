"""Tests for web/jobs_runner.py — run_web_discovery (Phase 7B).

Exercises the run_async bridge + run_discover + persist offline: a fake Scout
(canned batches) + the default heuristic evaluator + in-memory store. No key, no
network.
"""

from __future__ import annotations

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
from web.jobs_runner import run_web_discovery

_PREFS = SessionPreferences(target_roles=["Fractional CTO"], nice_to_haves=["AWS", "MCP"])


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


def _job(ext: str, desc: str) -> JobOpportunity:
    return JobOpportunity(
        job_id=make_job_id("remotive", ext),
        metadata=JobMetadata(title="Fractional CTO", company="Acme"),
        raw_description=desc,
    )


def _primary(tools: _ScriptedTools) -> PrimaryAgent:
    return PrimaryAgent(
        prefs=_PREFS,
        ledger=InteractionLedger(),
        scout=Scout(tools=tools),
        desired_total=2,
        max_iterations=3,
    )


def test_run_web_discovery_runs_and_persists() -> None:
    store = InMemoryLedgerStore()
    tools = _ScriptedTools([[_job("1", "AWS"), _job("2", "MCP")]])
    result = run_web_discovery(user_id="u1", primary=_primary(tools), store=store)
    assert len(result.accepted) == 2
    # Accepted jobs were persisted and are retrievable for display on entry.
    assert {j.job_id for j in store.list_accepted("u1")} == {
        make_job_id("remotive", "1"),
        make_job_id("remotive", "2"),
    }


def test_run_web_discovery_empty_source_is_safe() -> None:
    store = InMemoryLedgerStore()
    result = run_web_discovery(user_id="u1", primary=_primary(_ScriptedTools([[]])), store=store)
    assert result.accepted == []
    assert store.list_accepted("u1") == []
